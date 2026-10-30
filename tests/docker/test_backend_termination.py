"""Inspect backend command handling without contacting Docker."""
import asyncio

import pytest

from oaos2.docker.backend import ContainerHandle, LocalDockerBackend
from oaos2.docker.isolation import IsolationViolation
from oaos2.docker.runner import run_tool_in_container
from oaos2.trace.invariants import load_all_events
from oaos2.trace.spine import RunSpine


class Process:
    def __init__(self, output=b"", rc=0, blocks=False):
        self.output, self.returncode, self.blocks = output, rc, blocks
        self.killed = False

    async def communicate(self):
        if self.blocks:
            await asyncio.Future()
        return self.output, b""

    def kill(self):
        self.killed = True

    async def wait(self):
        return self.returncode


async def test_start_preserves_container_until_explicit_removal(tmp_path, monkeypatch):
    commands = []

    async def create(*argv, **kwargs):
        commands.append(argv)
        return Process(b"container-id\n")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    await LocalDockerBackend().run(image="synthetic", digest="sha256:fake", mounts=[], env={},
                                  network="disabled", memory="1g", cpus=1, pids=32,
                                  disk="1g", wall_clock=60, user="nonroot_ro_rootfs",
                                  agent_id="a", mount_root=tmp_path)
    assert commands[0][:3] == ("docker", "run", "-d")
    assert "--rm" not in commands[0]


@pytest.mark.parametrize("stopped", [True, False])
async def test_timeout_stops_and_checks_container_before_failing_run(tmp_path, monkeypatch, stopped):
    commands = []
    client = Process(blocks=True)

    async def create(*argv, **kwargs):
        commands.append(argv)
        if argv[1] == "exec":
            return client
        if argv[1] == "stop":
            return Process()
        assert argv[1] == "inspect"
        return Process(b"false\n" if stopped else b"true\n")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    spine = RunSpine(tmp_path, "r")
    await spine.start()
    with pytest.raises(IsolationViolation, match="container stopped" if stopped else "not be verified"):
        await run_tool_in_container(spine, LocalDockerBackend(),
                                    ContainerHandle("a", "fake", "sha256:fake", tmp_path),
                                    "tool", ["python", "example.py"], wall_clock_cap=0.001)
    assert client.killed
    assert [c[1] for c in commands] == ["exec", "stop", "inspect"]
    await spine.finalize("failed")
    assert any(e["event_class"] == "isolation.violation" for e in load_all_events(tmp_path))


class _Inspect:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


@pytest.mark.parametrize("inspect,lost", [
    (_Inspect(0, "true false\n"), False),
    (_Inspect(0, "false false\n"), True),  # stopped from outside
    (_Inspect(1, stderr="Error: no such object: c1"), True),  # removed from outside (October 12, 2026)
    (_Inspect(1, stderr="Cannot connect to the Docker daemon"), False),  # unknown is not taken as lost
])
async def test_a_container_removed_or_stopped_from_outside_ends_the_run(tmp_path, monkeypatch, inspect, lost):
    from oaos2.docker.isolation import ContainerLost

    async def create(*argv, **kwargs):
        return Process(b"", rc=1)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    monkeypatch.setattr("oaos2.docker.backend.subprocess.run", lambda *a, **k: inspect)
    handle = ContainerHandle(agent_id="firm_e", container_id="c1" * 32, image_digest="sha256:fake",
                             mount_root=tmp_path)
    if lost:
        with pytest.raises(ContainerLost):
            await LocalDockerBackend().exec(handle, ["python", "x.py"], timeout=5)
        assert issubclass(ContainerLost, IsolationViolation)  # run-fatal like any isolation breach
    else:
        assert (await LocalDockerBackend().exec(handle, ["python", "x.py"], timeout=5)).exit_code == 1


async def test_containers_carry_owner_labels(tmp_path, monkeypatch):
    commands = []

    async def create(*argv, **kwargs):
        commands.append(argv)
        return Process(b"container-id\n")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    await LocalDockerBackend().run(image="synthetic", digest="sha256:fake", mounts=[], env={},
                                  network="disabled", memory="1g", cpus=1, pids=32,
                                  disk="1g", wall_clock=60, user="nonroot_ro_rootfs",
                                  agent_id="firm_a", mount_root=tmp_path)
    argv = list(commands[0])
    labels = [argv[i + 1] for i, a in enumerate(argv) if a == "--label"]
    assert "oaos2=1" in labels and "oaos2.agent=firm_a" in labels
    assert f"oaos2.mount_root={tmp_path.resolve()}" in labels
