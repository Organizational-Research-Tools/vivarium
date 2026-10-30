"""Stage containers, execute tools, capture files, and remove completed containers.

Staging checks the requested policy, image digest, mounts, and environment. Capture
stops the container before scanning and copying host-backed files, then removes it
after capture.succeeded. A detected escape or copy failure raises and preserves
the container for inspection. Cleanup callers must handle that failure explicitly;
this module does not guarantee removal on every error path."""

from __future__ import annotations

from oaos2.docker.backend import ContainerBackend, ContainerHandle, ExecResult
from oaos2.docker.capture import copy_artifacts
from oaos2.docker.isolation import (
    IsolationViolation,
    assert_backend_satisfies_policy,
    assert_no_credentials,
    assert_no_hidden_paths,
    assert_no_named_volumes_for_writable,
    assert_no_symlink_escape,
    assert_policy_isolatable,
    check_disk_within_limit,
)
from oaos2.docker.mounts import build_mounts
from oaos2.docker.policy import DockerPolicy
from oaos2.kernel.run_dir import RunDir
from oaos2.trace.spine import RunSpine


async def stage_agent_in_docker(
    spine: RunSpine,
    backend: ContainerBackend,
    run_dir: RunDir,
    agent_id: str,
    policy: DockerPolicy,
    extra_ro_mounts: list | None = None,
    omit_mounts: tuple = (),
) -> ContainerHandle:
    """Launch one agent's tool-execution sandbox (M2 §2). Fail closed + traced.

    ``extra_ro_mounts`` lets a pack mount fixed read-only assets (e.g. data CSVs)
    directly from the pack instead of copying them into every run dir.
    """
    assert_policy_isolatable(policy)

    # 0. CAPABILITY GATE — refuse (don't silently weaken) a cell whose isolation
    #    this backend cannot provide (M2 §7).
    try:
        assert_backend_satisfies_policy(backend.capabilities, policy)
    except IsolationViolation as exc:
        await spine.emit_event(
            "docker.capability_gap", agent_id=agent_id,
            payload={"reason": "backend_capability_gap", "detail": str(exc)},
        )
        raise

    # 1. IMAGE DIGEST VERIFY — fail closed (DESIGN §7.2, §22 gate).
    digest = backend.inspect_digest(policy.image_ref)
    if digest != policy.image_digest_pinned:
        await spine.emit_event(
            "docker.launch_failed",
            agent_id=agent_id,
            payload={
                "reason": "image_digest_mismatch",
                "expected": policy.image_digest_pinned,
                "actual": digest,
            },
        )
        raise IsolationViolation("image digest mismatch")

    # 2. ASSEMBLE MOUNTS — workspace writes use host mounts; hidden paths absent (§4 launch).
    mounts = build_mounts(run_dir, agent_id, omit=tuple(omit_mounts)) + list(extra_ro_mounts or [])
    try:
        assert_no_hidden_paths(mounts, policy.hidden_host_paths)
        assert_no_named_volumes_for_writable(mounts)
        # 3. ENV ALLOWLIST — credentials NEVER enter the container (§8.1).
        env = dict(policy.env_allowlist)
        assert_no_credentials(env)
    except IsolationViolation as exc:
        await spine.emit_event(
            "docker.launch_failed", agent_id=agent_id,
            payload={"reason": "isolation_precheck", "detail": str(exc)},
        )
        raise

    # 4. LAUNCH with resource/user/network policy.
    try:
        handle = await backend.run(
            image=policy.image_ref,
            digest=digest,
            mounts=mounts,
            env=env,
            network=policy.network_policy,
            memory=policy.mem_limit,
            cpus=policy.cpu_limit,
            pids=policy.pid_limit,
            disk=policy.disk_limit,
            wall_clock=policy.wall_clock_limit,
            user=policy.user_policy,
            agent_id=agent_id,
            mount_root=run_dir.container_mount,
            tmpfs_tmp=policy.tmpfs_tmp,
        )
    except Exception as exc:
        await spine.emit_event(
            "docker.launch_failed", agent_id=agent_id,
            payload={"reason": "launch_error", "detail": str(exc)},
        )
        raise

    eid = await spine.emit_event(
        "docker.launched",
        agent_id=agent_id,
        payload={
            "image_digest": digest,
            "policy_hash": policy.hash(),
            "network": policy.network_policy,
            "container_id": handle.container_id,
        },
    )
    handle.started_at_event_id = eid
    return handle


async def run_tool_in_container(
    spine: RunSpine,
    backend: ContainerBackend,
    handle: ContainerHandle,
    tool_call_id: str,
    argv: list[str],
    wall_clock_cap: int,
    caused_by: str | None = None,
    disk_limit: str | None = None,
) -> ExecResult:
    """Execute a tool in its container and record its result and limit violations.

    disk_limit checks the host-backed writable tree after execution. This is
    breach detection, not an operating-system disk quota: it cannot prevent
    the tool from filling the disk while running."""
    try:
        res = await backend.exec(handle, argv, timeout=wall_clock_cap)
    except IsolationViolation as exc:
        await spine.emit_event(
            "isolation.violation", agent_id=handle.agent_id, caused_by=caused_by,
            payload={"tool_call_id": tool_call_id, "reason": "execution_failed",
                     "detail": str(exc)},
        )
        raise
    if res.oom_killed:
        await spine.emit_event(
            "docker.oom", agent_id=handle.agent_id,
            payload={"tool_call_id": tool_call_id}, caused_by=caused_by,
        )
    await spine.emit_event(
        "docker.exec",
        agent_id=handle.agent_id,
        caused_by=caused_by,
        payload={
            "tool_call_id": tool_call_id,
            "exit_code": res.exit_code,
            "signal": res.signal,
            "duration_s": res.duration_s,
            "timed_out": res.timed_out,
        },
    )

    # HOST-SIDE DISK QUOTA (M2 §8.3) — fail the run on breach. Measure THIS agent's
    # own writable scratch (container_mount/agents/<id>), not the shared run root:
    # the container only writes its own scratch (shared/submitted are ro), and in a
    # multi-agent run every agent shares mount_root, so checking the whole tree would
    # bill one agent for the others' bytes.
    if disk_limit is not None:
        from pathlib import Path

        scratch = Path(handle.mount_root) / "agents" / handle.agent_id
        try:
            check_disk_within_limit(scratch, disk_limit)
        except IsolationViolation as exc:
            await spine.emit_event(
                "docker.disk_exceeded", agent_id=handle.agent_id, caused_by=caused_by,
                payload={"tool_call_id": tool_call_id, "detail": str(exc)},
            )
            raise
    return res


async def capture_and_teardown(
    spine: RunSpine,
    backend: ContainerBackend,
    run_dir: RunDir,
    handle: ContainerHandle,
    policy: DockerPolicy,
    reason: str,
) -> list[str]:
    """Stop the container, check paths, copy artifacts, then remove the container.

    Capture reads host-backed files even if the container has already stopped.
    An escape or copy failure prevents removal and raises for the caller to
    handle. Preserve the stopped container and files for inspection on failure."""
    try:
        await backend.stop(handle)  # quiesce: no in-container process can mutate now
        assert_no_symlink_escape(run_dir.container_mount, policy.hidden_host_paths)
    except IsolationViolation as exc:
        await spine.emit_event(
            "isolation.violation", agent_id=handle.agent_id,
            payload={"reason": "symlink_escape", "detail": str(exc)},
        )
        raise  # do NOT copy, do NOT tear down

    try:
        captured = copy_artifacts(run_dir.container_mount, run_dir.captured, policy.capture_globs)
    except Exception as exc:
        await spine.emit_event(
            "capture.failed", agent_id=handle.agent_id,
            payload={"reason": str(exc)},
        )
        raise  # do NOT tear down on capture failure — preserve for forensics

    await spine.emit_event(
        "capture.succeeded", agent_id=handle.agent_id,
        payload={"reason": reason, "files": len(captured)},
    )
    await backend.remove(handle)  # erase ephemeral layer only now
    return captured
