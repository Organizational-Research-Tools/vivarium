"""Pure isolation-control tests (M2 §3, §4) — no Docker daemon required.

These cover the load-bearing, host-side controls: the zone→mount-mode mapping,
hidden-path absence, credential rejection, named-volume rejection, the no-follow
capture, policy precedence, and the run-dir layout.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from oaos2.docker.backend import BackendCapabilities
from oaos2.docker.capture import copy_artifacts
from oaos2.docker.isolation import (
    IsolationViolation,
    assert_backend_satisfies_policy,
    assert_no_credentials,
    assert_no_hidden_paths,
    assert_no_named_volumes_for_writable,
    assert_no_symlink_escape,
    check_disk_within_limit,
    parse_size,
)
from oaos2.docker.mounts import build_mounts
from oaos2.docker.policy import DockerPolicy, Mount, resolve_docker_policy
from oaos2.kernel.run_dir import RunDir
from oaos2.workspace.zones import MountMode


def _rd(tmp_path) -> RunDir:
    return RunDir.create(tmp_path, "exp1", "pack1", "run1")


def test_mount_modes_match_design_table(tmp_path) -> None:
    rd = _rd(tmp_path)
    mounts = {m.container_path: m.mode for m in build_mounts(rd, "a1")}
    assert mounts["/visible"] is MountMode.RO
    assert mounts["/work/agents/a1"] is MountMode.RW
    assert mounts["/work/shared"] is MountMode.RO  # host writes it; container can't
    assert mounts["/work/submitted"] is MountMode.RO  # OS-enforced commit zone (§8)


def test_hidden_paths_never_mounted(tmp_path) -> None:
    rd = _rd(tmp_path)
    mounts = build_mounts(rd, "a1")
    # A hidden path that is NOT a parent of any mount: fine.
    assert_no_hidden_paths(mounts, [tmp_path / "totally" / "elsewhere"])
    # A hidden path that is the PARENT of the mount root: violation.
    with pytest.raises(IsolationViolation):
        assert_no_hidden_paths(mounts, [rd.container_mount])


def test_credentials_rejected_by_key_and_value() -> None:
    assert_no_credentials({"PATH": "/usr/bin", "LANG": "C"})  # ok
    with pytest.raises(IsolationViolation):
        assert_no_credentials({"ANTHROPIC_API_KEY": "x"})
    with pytest.raises(IsolationViolation):
        assert_no_credentials({"INNOCENT": "sk-ant-secret123"})


def test_named_volume_for_writable_rejected(tmp_path) -> None:
    bad = [Mount(tmp_path / "v", "/work/agents/a1", MountMode.RW, is_named_volume=True)]
    with pytest.raises(IsolationViolation):
        assert_no_named_volumes_for_writable(bad)


def test_symlink_escape_detected(tmp_path) -> None:
    rd = _rd(tmp_path)
    secret = tmp_path / "secret"
    secret.mkdir()
    (secret / "key.txt").write_text("ANSWER KEY")
    scratch = rd.ensure_agent_scratch("a1")
    (scratch / "leak").symlink_to(secret / "key.txt")
    with pytest.raises(IsolationViolation):
        assert_no_symlink_escape(rd.container_mount, [secret])


def test_capture_does_not_follow_symlinks(tmp_path) -> None:
    rd = _rd(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("ANSWER KEY")
    scratch = rd.ensure_agent_scratch("a1")
    (scratch / "real.txt").write_text("ok work")
    (scratch / "leak").symlink_to(secret)
    captured = copy_artifacts(rd.container_mount, rd.captured, ["**/*"])
    # The symlink is captured AS a symlink (not dereferenced into a copy of the secret).
    leak = rd.captured / "agents" / "a1" / "leak"
    assert leak.is_symlink()
    # The regular file is copied normally.
    assert (rd.captured / "agents" / "a1" / "real.txt").read_text() == "ok work"
    assert "agents/a1/real.txt" in captured


def test_policy_precedence_network_narrows_not_broadens() -> None:
    # Valid narrowing: org grants allowlist, the agent tightens to disabled.
    org = DockerPolicy(image_ref="img", image_digest_pinned="sha256:x", network_policy="allowlist")
    agent = DockerPolicy(image_ref="img", image_digest_pinned="sha256:x", network_policy="disabled")
    resolved = resolve_docker_policy(org_policy=org, role_policy=None, agent_policy=agent)
    assert resolved.network_policy == "disabled"

    # Broadening: org grants disabled, the agent tries unrestricted → rejected at load.
    org2 = DockerPolicy(image_ref="img", image_digest_pinned="sha256:x", network_policy="disabled")
    agent2 = DockerPolicy(image_ref="img", image_digest_pinned="sha256:x", network_policy="unrestricted")
    with pytest.raises(ValueError):
        resolve_docker_policy(org_policy=org2, role_policy=None, agent_policy=agent2)


def test_parse_size_units() -> None:
    assert parse_size("1024") == 1024
    assert parse_size("4g") == 4 * 1024**3
    assert parse_size("512m") == 512 * 1024**2
    assert parse_size("2k") == 2048


def test_disk_limit_breach_fails(tmp_path) -> None:
    rd = _rd(tmp_path)
    scratch = rd.ensure_agent_scratch("a1")
    (scratch / "big.bin").write_bytes(b"x" * 4096)
    # Within a generous limit: returns (used, limit).
    used, limit = check_disk_within_limit(rd.container_mount, "1m")
    assert used >= 4096 and limit == 1024**2
    # A tiny limit is breached and fails the run (M2 §8.3).
    with pytest.raises(IsolationViolation):
        check_disk_within_limit(rd.container_mount, "1k")


def test_backend_capability_gap_refuses_unsupported_network() -> None:
    policy = DockerPolicy(
        image_ref="img", image_digest_pinned="sha256:x", network_policy="allowlist"
    )
    caps = BackendCapabilities()  # v0 supports only disabled/unrestricted
    with pytest.raises(IsolationViolation):
        assert_backend_satisfies_policy(caps, policy)
    # A satisfiable policy passes.
    ok_policy = DockerPolicy(image_ref="img", image_digest_pinned="sha256:x")
    assert_backend_satisfies_policy(caps, ok_policy)


def test_run_dir_layout(tmp_path) -> None:
    rd = _rd(tmp_path)
    assert rd.trace.is_dir()
    assert rd.agents_root.is_dir()
    assert rd.shared.is_dir()
    assert rd.submitted.is_dir()
    assert rd.visible.is_dir()
    assert rd.captured.is_dir()
    assert rd.root == Path(tmp_path) / "exp1" / "pack1" / "run1"
