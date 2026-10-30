"""Lifecycle + event-emission tests with the in-process FakeContainerBackend (M2 §2).

Exercises stage → exec → capture → teardown and the M0 events each step emits,
plus the fail-closed paths (digest mismatch, symlink-escape isolation violation),
without needing a Docker daemon.
"""

from __future__ import annotations

import pytest

from oaos2.docker.backend import ExecResult, FakeContainerBackend
from oaos2.docker.isolation import IsolationViolation
from oaos2.docker.policy import DockerPolicy
from oaos2.docker.runner import (
    capture_and_teardown,
    run_tool_in_container,
    stage_agent_in_docker,
)
from oaos2.kernel.run_dir import RunDir
from oaos2.trace.invariants import load_all_events
from oaos2.trace.spine import RunSpine


def _policy(digest="sha256:fake") -> DockerPolicy:
    return DockerPolicy(image_ref="img:test", image_digest_pinned=digest)


async def _spine(run_dir: RunDir) -> RunSpine:
    spine = RunSpine(run_dir.root, run_id="run1")
    await spine.start()
    return spine


def _classes(run_dir: RunDir) -> set[str]:
    return {e["event_class"] for e in load_all_events(run_dir.root)}


async def test_happy_path_emits_launch_exec_capture(tmp_path) -> None:
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = await _spine(rd)
    backend = FakeContainerBackend(digest="sha256:fake")

    handle = await stage_agent_in_docker(spine, backend, rd, "a1", _policy())
    await run_tool_in_container(spine, backend, handle, "tc1", ["echo", "hi"], 30)
    (rd.ensure_agent_scratch("a1") / "out.txt").write_text("result")
    captured = await capture_and_teardown(spine, backend, rd, handle, _policy(), "success")

    report = await spine.finalize("completed")
    assert report.ok, report.failures
    cls = _classes(rd)
    assert {"docker.launched", "docker.exec", "capture.succeeded"} <= cls
    assert "agents/a1/out.txt" in captured
    # stop precedes remove (quiesce-before-teardown).
    assert backend.calls[-2:] == [("stop", "a1"), ("remove", "a1")]


async def test_digest_mismatch_fails_closed(tmp_path) -> None:
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = await _spine(rd)
    backend = FakeContainerBackend(digest="sha256:WRONG")  # != pinned sha256:fake
    with pytest.raises(IsolationViolation):
        await stage_agent_in_docker(spine, backend, rd, "a1", _policy("sha256:fake"))
    await spine.finalize("completed")
    cls = _classes(rd)
    assert "docker.launch_failed" in cls
    assert "docker.launched" not in cls  # never launched an unpinned image


async def test_symlink_escape_is_isolation_violation(tmp_path) -> None:
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = await _spine(rd)
    backend = FakeContainerBackend(digest="sha256:fake")
    secret = tmp_path / "secret"
    secret.mkdir()
    (secret / "key").write_text("KEY")
    policy = DockerPolicy(
        image_ref="img:test", image_digest_pinned="sha256:fake", hidden_host_paths=[secret]
    )
    handle = await stage_agent_in_docker(spine, backend, rd, "a1", policy)
    # Simulate an execute'd subprocess having created a leaking symlink.
    (rd.ensure_agent_scratch("a1") / "leak").symlink_to(secret / "key")
    with pytest.raises(IsolationViolation):
        await capture_and_teardown(spine, backend, rd, handle, policy, "success")
    await spine.finalize("failed")
    assert "isolation.violation" in _classes(rd)
    # Container preserved for forensics — not removed.
    assert ("remove", "a1") not in backend.calls


async def test_credential_in_env_fails_closed(tmp_path) -> None:
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = await _spine(rd)
    backend = FakeContainerBackend(digest="sha256:fake")
    policy = DockerPolicy(
        image_ref="img:test",
        image_digest_pinned="sha256:fake",
        env_allowlist={"ANTHROPIC_API_KEY": "sk-ant-leak"},
    )
    with pytest.raises(IsolationViolation):
        await stage_agent_in_docker(spine, backend, rd, "a1", policy)
    await spine.finalize("failed")
    assert "docker.launch_failed" in _classes(rd)


async def test_oom_emits_docker_oom(tmp_path) -> None:
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = await _spine(rd)
    backend = FakeContainerBackend(
        digest="sha256:fake",
        exec_fn=lambda h, argv: ExecResult(exit_code=137, oom_killed=True),
    )
    handle = await stage_agent_in_docker(spine, backend, rd, "a1", _policy())
    res = await run_tool_in_container(spine, backend, handle, "tc1", ["stress"], 30)
    assert res.oom_killed
    await spine.finalize("completed")
    assert "docker.oom" in _classes(rd)
