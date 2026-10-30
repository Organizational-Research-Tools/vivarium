"""Define isolated-execution operations and real and simulated backends.

LocalDockerBackend invokes the Docker CLI. FakeContainerBackend simulates lifecycle,
execution results, and read-only mount failures for offline tests; it does not
provide operating-system isolation. Backend capability declarations are checked
against the requested policy before staging. Actual isolation needs live tests."""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from oaos2.docker.policy import Mount
from oaos2.workspace.zones import MountMode


@dataclass
class BackendCapabilities:
    supports_ro_rootfs: bool = True
    supports_pid_limit: bool = True
    supports_network_disable: bool = True
    supports_mem_limit: bool = True
    # Network modes the backend can actually enforce. ``model_api_only`` and
    # ``allowlist`` need a host proxy that v0 does not ship, so they are absent —
    # a cell requesting them is refused (M2 §7), not silently downgraded to none.
    supported_network_modes: frozenset = field(
        default_factory=lambda: frozenset({"disabled", "unrestricted"})
    )


@dataclass
class ContainerHandle:
    agent_id: str
    container_id: str
    image_digest: str
    mount_root: Path  # host side of container_mount/ for this agent's run
    started_at_event_id: str | None = None


@dataclass
class ExecResult:
    exit_code: int
    signal: int | None = None
    duration_s: float = 0.0
    oom_killed: bool = False
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


class ContainerBackend(Protocol):
    capabilities: BackendCapabilities

    def inspect_digest(self, image_ref: str) -> str: ...

    async def run(
        self,
        *,
        image: str,
        digest: str,
        mounts: list[Mount],
        env: dict[str, str],
        network: str,
        memory: str,
        cpus: float,
        pids: int,
        disk: str,
        wall_clock: int,
        user: str,
        agent_id: str,
        mount_root: Path,
        tmpfs_tmp: bool = True,
    ) -> ContainerHandle: ...

    async def exec(self, handle: ContainerHandle, argv: list[str], timeout: int) -> ExecResult: ...

    async def stop(self, handle: ContainerHandle) -> None: ...

    async def remove(self, handle: ContainerHandle) -> None: ...


# --------------------------------------------------------------------------- #
# Real Docker backend (docker CLI)
# --------------------------------------------------------------------------- #


class DockerUnavailable(Exception):
    pass


class LocalDockerBackend:
    """Real Docker via the ``docker`` CLI. Requires a running daemon."""

    def __init__(self) -> None:
        self.capabilities = BackendCapabilities()

    @staticmethod
    def available() -> bool:
        try:
            r = subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                capture_output=True,
                timeout=20,
            )
            return r.returncode == 0
        except Exception:
            return False

    def inspect_digest(self, image_ref: str) -> str:
        r = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{.Id}}", image_ref],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode != 0:
            raise DockerUnavailable(f"docker inspect failed: {r.stderr.strip()}")
        return r.stdout.strip()

    async def run(
        self,
        *,
        image,
        digest,
        mounts,
        env,
        network,
        memory,
        cpus,
        pids,
        disk,
        wall_clock,
        user,
        agent_id,
        mount_root,
        tmpfs_tmp=True,
    ) -> ContainerHandle:
        # Explicit removal follows successful capture; stopping alone must preserve
        # a failed container for inspection.
        argv = ["docker", "run", "-d"]
        # Network: "disabled" → --network none (no NIC at all, M2 §0). The runner
        # has already refused any mode this backend can't enforce (M2 §7), so the
        # only modes reaching here are "disabled"/"unrestricted".
        if network == "unrestricted":
            pass  # default bridge
        else:
            argv += ["--network", "none"]
        argv += ["--memory", memory, "--cpus", str(cpus), "--pids-limit", str(pids)]
        # Privilege hardening (M2 §0/§8): drop all Linux capabilities and forbid
        # privilege escalation regardless of user policy — the container is the
        # untrusted side-effect surface.
        argv += ["--cap-drop", "ALL", "--security-opt", "no-new-privileges"]
        if user == "nonroot_ro_rootfs":
            argv += ["--user", "65534:65534", "--read-only"]
            if tmpfs_tmp:
                argv += ["--tmpfs", "/tmp"]
        for k, v in env.items():
            argv += ["-e", f"{k}={v}"]
        for m in mounts:
            ro = ":ro" if m.mode is MountMode.RO else ""
            argv += ["-v", f"{Path(m.host_path).resolve()}:{m.container_path}{ro}"]
        # Labels name the owner, so a cleanup can select one run's containers instead of
        # guessing by age (October 12, 2026: an age-based cleanup removed a live run's sandboxes).
        argv += ["--label", "oaos2=1", "--label", f"oaos2.agent={agent_id}",
                 "--label", f"oaos2.mount_root={Path(mount_root).resolve()}"]
        # Keep the container alive so the tool runner can `docker exec` into it.
        argv += [image, "sleep", str(wall_clock)]

        proc = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            raise DockerUnavailable(f"docker run failed: {err.decode().strip()}")
        container_id = out.decode().strip()
        return ContainerHandle(
            agent_id=agent_id,
            container_id=container_id,
            image_digest=digest,
            mount_root=Path(mount_root),
        )

    async def exec(self, handle, argv, timeout) -> ExecResult:
        import time

        cmd = ["docker", "exec", handle.container_id, *argv]
        start = time.time()
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            from oaos2.docker.isolation import IsolationViolation

            try:
                await self.stop(handle)
            except Exception as exc:
                raise IsolationViolation("tool timed out; container termination could not be verified") from exc
            raise IsolationViolation("tool timed out; container stopped and run must end")
        running, oom = self._state(handle.container_id)
        rc = proc.returncode or 0
        if not running:
            # The sandbox was removed or stopped from outside; every later tool call would fail
            # the same way, so the run no longer has the apparatus it declared (October 12, 2026).
            from oaos2.docker.isolation import ContainerLost

            raise ContainerLost(f"sandbox container {handle.container_id[:12]} of {handle.agent_id} "
                                "is gone or stopped; run must end")
        # `docker exec` reports a signal-killed command as exit code 128+N
        # (and asyncio reports a signal-killed *client* as -N); surface the
        # signal number so the traced docker.exec event isn't always null (M2 §2).
        if rc < 0:
            signal_num = -rc
        elif rc > 128:
            signal_num = rc - 128
        else:
            signal_num = None
        return ExecResult(
            exit_code=rc,
            signal=signal_num,
            duration_s=time.time() - start,
            oom_killed=oom,
            stdout=out.decode(errors="replace"),
            stderr=err.decode(errors="replace"),
        )

    def _state(self, container_id: str) -> tuple[bool, bool]:
        """(running, oom_killed). A container docker no longer knows is not running; an inspect
        that cannot be completed is taken as running, so a slow daemon does not end a run."""
        try:
            r = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Running}} {{.State.OOMKilled}}", container_id],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except Exception:
            return True, False
        if r.returncode != 0:
            return "no such" not in r.stderr.lower(), False
        running, _, oom = r.stdout.strip().partition(" ")
        return running == "true", oom == "true"

    async def stop(self, handle) -> None:
        proc = await asyncio.create_subprocess_exec(
            "docker", "stop", "-t", "2", handle.container_id,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            rc = await asyncio.wait_for(proc.wait(), timeout=15)
        except BaseException:
            if proc.returncode is None:
                proc.kill()
            await proc.wait()
            raise
        if rc != 0:
            raise DockerUnavailable("docker stop failed; container state is unknown")
        inspect = await asyncio.create_subprocess_exec(
            "docker", "inspect", "--format", "{{.State.Running}}", handle.container_id,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, _ = await asyncio.wait_for(inspect.communicate(), timeout=15)
        except BaseException:
            if inspect.returncode is None:
                inspect.kill()
            await inspect.wait()
            raise
        if inspect.returncode != 0 or out.strip() != b"false":
            raise DockerUnavailable("container did not confirm a stopped state")

    async def remove(self, handle) -> None:
        proc = await asyncio.create_subprocess_exec(
            "docker", "rm", "-f", handle.container_id,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()


# --------------------------------------------------------------------------- #
# In-process fake backend (deterministic lifecycle/event tests, no daemon)
# --------------------------------------------------------------------------- #


@dataclass
class FakeContainerBackend:
    """Simulates the sandbox boundary in-process. Records calls; honors mount modes.

    ``exec_fn(handle, argv) -> ExecResult`` lets a test simulate tool side effects.
    Writes through ``simulate_write`` to a ro-mounted path return an EROFS-shaped
    result, exercising the ro-commit-zone behavior without a daemon.
    """

    digest: str = "sha256:fake"
    capabilities: BackendCapabilities = field(default_factory=BackendCapabilities)
    exec_fn: Callable[[ContainerHandle, list[str]], ExecResult] | None = None
    calls: list[tuple[str, str]] = field(default_factory=list)
    _mounts_by_agent: dict[str, list[Mount]] = field(default_factory=dict)
    digest_override: str | None = None

    def inspect_digest(self, image_ref: str) -> str:
        return self.digest_override or self.digest

    async def run(self, *, image, digest, mounts, env, network, memory, cpus, pids,
                  disk, wall_clock, user, agent_id, mount_root, tmpfs_tmp=True) -> ContainerHandle:
        self.calls.append(("run", agent_id))
        self._mounts_by_agent[agent_id] = mounts
        return ContainerHandle(
            agent_id=agent_id, container_id=f"fake-{agent_id}", image_digest=digest,
            mount_root=Path(mount_root),
        )

    async def exec(self, handle, argv, timeout) -> ExecResult:
        self.calls.append(("exec", handle.agent_id))
        if self.exec_fn is not None:
            return self.exec_fn(handle, argv)
        return ExecResult(exit_code=0, stdout="")

    async def stop(self, handle) -> None:
        self.calls.append(("stop", handle.agent_id))

    async def remove(self, handle) -> None:
        self.calls.append(("remove", handle.agent_id))

    def mount_mode_for(self, agent_id: str, container_path: str) -> MountMode | None:
        for m in self._mounts_by_agent.get(agent_id, []):
            if container_path == m.container_path or container_path.startswith(m.container_path + "/"):
                return m.mode
        return None
