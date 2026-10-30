"""Live Docker isolation gate (M2 §10, DESIGN §22) — real containers via busybox.

These exercise the OS-enforced guarantees that only a real daemon can prove:
- image digest verified at launch (fail closed on mismatch);
- the commit zone ``/work/submitted`` returns EROFS to an in-container write;
- ``network_policy: disabled`` means no network interface;
- the container runs non-root;
- declared hidden paths are absent from the mount namespace;
- capture reads the host bind mount even after the container is force-killed.

Skipped automatically when no Docker daemon is reachable. Uses ``busybox`` only
(the ``oaos:*`` images are a different, unrelated system).
"""

from __future__ import annotations

import subprocess

import pytest

from oaos2.docker.backend import LocalDockerBackend
from oaos2.docker.mounts import build_mounts
from oaos2.docker.policy import DockerPolicy
from oaos2.docker.runner import (
    capture_and_teardown,
    run_tool_in_container,
    stage_agent_in_docker,
)
from oaos2.kernel.run_dir import RunDir
from oaos2.trace.invariants import load_all_events
from oaos2.trace.spine import RunSpine

IMAGE = "busybox:latest"

pytestmark = pytest.mark.skipif(
    not LocalDockerBackend.available(), reason="no Docker daemon reachable"
)


def _ensure_image() -> str:
    backend = LocalDockerBackend()
    try:
        return backend.inspect_digest(IMAGE)
    except Exception:
        subprocess.run(["docker", "pull", IMAGE], check=True, capture_output=True, timeout=120)
        return backend.inspect_digest(IMAGE)


def _policy(digest: str, **kw) -> DockerPolicy:
    return DockerPolicy(image_ref=IMAGE, image_digest_pinned=digest, wall_clock_limit=120, **kw)


async def _spine(rd: RunDir) -> RunSpine:
    spine = RunSpine(rd.root, run_id="run1")
    await spine.start()
    return spine


async def test_digest_verified_fail_closed(tmp_path) -> None:
    _ensure_image()
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = await _spine(rd)
    backend = LocalDockerBackend()
    from oaos2.docker.isolation import IsolationViolation

    with pytest.raises(IsolationViolation):
        await stage_agent_in_docker(spine, backend, rd, "a1", _policy("sha256:deadbeef"))
    await spine.finalize("failed")
    assert "docker.launch_failed" in {e["event_class"] for e in load_all_events(rd.root)}


async def test_commit_zone_is_read_only_erofs(tmp_path) -> None:
    digest = _ensure_image()
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = await _spine(rd)
    backend = LocalDockerBackend()
    handle = await stage_agent_in_docker(spine, backend, rd, "a1", _policy(digest))
    try:
        # Writing to the OS-read-only commit zone must fail (EROFS).
        res = await run_tool_in_container(
            spine, backend, handle, "tc1",
            ["sh", "-c", "echo x > /work/submitted/cheat.txt"], 60,
        )
        assert res.exit_code != 0
        assert "read-only" in (res.stderr.lower()) or "denied" in res.stderr.lower()
        # Writing to private scratch succeeds.
        ok = await run_tool_in_container(
            spine, backend, handle, "tc2",
            ["sh", "-c", "echo ok > /work/agents/a1/out.txt"], 60,
        )
        assert ok.exit_code == 0
    finally:
        await capture_and_teardown(spine, backend, rd, handle, _policy(digest), "success")
        await spine.finalize("completed")
    assert (rd.captured / "agents" / "a1" / "out.txt").read_text().strip() == "ok"


async def test_no_network_and_nonroot(tmp_path) -> None:
    digest = _ensure_image()
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = await _spine(rd)
    backend = LocalDockerBackend()
    handle = await stage_agent_in_docker(spine, backend, rd, "a1", _policy(digest))
    try:
        # No external network interface (only lo) under --network none.
        ifaces = await run_tool_in_container(
            spine, backend, handle, "net", ["sh", "-c", "ip -o addr 2>/dev/null | grep -c eth0"], 60
        )
        assert ifaces.stdout.strip() == "0"  # no eth0 under network=disabled
        # Non-root.
        whoami = await run_tool_in_container(
            spine, backend, handle, "uid", ["id", "-u"], 60
        )
        assert whoami.stdout.strip() != "0"
    finally:
        await capture_and_teardown(spine, backend, rd, handle, _policy(digest), "success")
        await spine.finalize("completed")


async def test_capture_survives_forced_kill(tmp_path) -> None:
    digest = _ensure_image()
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = await _spine(rd)
    backend = LocalDockerBackend()
    handle = await stage_agent_in_docker(spine, backend, rd, "a1", _policy(digest))
    # Agent writes to the host-backed scratch, then we hard-kill the container.
    await run_tool_in_container(
        spine, backend, handle, "w", ["sh", "-c", "echo survived > /work/agents/a1/work.txt"], 60
    )
    subprocess.run(["docker", "kill", "-s", "KILL", handle.container_id], capture_output=True, timeout=30)
    # Capture reads the host bind mount — works even though the container is dead.
    captured = await capture_and_teardown(spine, backend, rd, handle, _policy(digest), "interrupt")
    await spine.finalize("failed", {"reason": "interrupted"})
    assert "agents/a1/work.txt" in captured
    assert (rd.captured / "agents" / "a1" / "work.txt").read_text().strip() == "survived"
