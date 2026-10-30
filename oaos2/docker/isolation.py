"""Check declared isolation requirements at launch and inspect files at capture.

Launch checks cover backend capabilities, hidden mount paths, environment
credentials, and writable storage. Capture checks detect symbolic links that
escape permitted directories; the copy routine separately avoids following links.
Violations raise IsolationViolation. These checks cover declared paths and
supported policies, not every conceivable information channel."""

from __future__ import annotations

import re
from pathlib import Path

from oaos2.docker.policy import DockerPolicy, Mount


class IsolationViolation(Exception):
    """An isolation guarantee was breached; the run is invalid (DESIGN §8)."""


class ContainerLost(IsolationViolation):
    """An agent's sandbox container disappeared or stopped during the run; the declared apparatus no
    longer exists, so the run ends as failed rather than continuing with a broken tool."""


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except ValueError:
        return False


def assert_no_hidden_paths(mounts: list[Mount], hidden_host_paths: list[Path]) -> None:
    """No hidden host path is mounted, directly or as a parent of a mount source (§4 launch)."""
    for hidden in hidden_host_paths:
        hidden = Path(hidden)
        for mount in mounts:
            src = Path(mount.host_path)
            # Violation if the mount source IS, is INSIDE, or CONTAINS a hidden path.
            if _is_within(src, hidden) or _is_within(hidden, src):
                raise IsolationViolation(
                    f"hidden path {hidden} is exposed by mount {src} -> {mount.container_path}"
                )


def assert_no_named_volumes_for_writable(mounts: list[Mount]) -> None:
    """Writable zones must be bind mounts, never named volumes/overlay (§7.1 decision 2)."""
    for mount in mounts:
        if mount.mode.value == "rw" and mount.is_named_volume:
            raise IsolationViolation(
                f"writable zone {mount.container_path} is backed by a named volume "
                "(forbidden — post-mortem capture from a dead container's layer is racy)"
            )


# Heuristic credential detectors for the env-allowlist boundary test (§8.1).
_CREDENTIAL_KEY = re.compile(
    r"(API[_-]?KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL|PRIVATE[_-]?KEY|"
    r"ANTHROPIC|OPENAI|AWS_|GCP_|AZURE_)",
    re.IGNORECASE,
)
_CREDENTIAL_VALUE = re.compile(r"^(sk-|sk-ant-|ghp_|AKIA|AIza|xox[baprs]-)")


def assert_no_credentials(env: dict[str, str]) -> None:
    """Credentials never enter the container (§8.1). Fail closed on key OR value match."""
    for key, value in env.items():
        if _CREDENTIAL_KEY.search(key) or _CREDENTIAL_VALUE.match(str(value)):
            raise IsolationViolation(
                f"credential-shaped env var {key!r} would enter the container "
                "(credentials must stay host-side, §8)"
            )


def assert_no_symlink_escape(container_mount: Path, hidden_host_paths: list[Path]) -> None:
    """No symlink in the writable tree resolves outside the sandbox (§4 capture).

    The container is quiesced before this scan (stop → scan → copy, M2 §2), so no
    in-container subprocess can create a symlink in the window between scanning and
    copying.
    """
    root = Path(container_mount)
    real_root = root.resolve(strict=False)
    hidden_resolved = [Path(h).resolve(strict=False) for h in hidden_host_paths]
    for p in root.rglob("*"):
        if p.is_symlink():
            target = p.resolve(strict=False)
            if not _is_within(target, real_root):
                raise IsolationViolation(f"symlink escape: {p} -> {target}")
            for hidden in hidden_resolved:
                if _is_within(target, hidden):
                    raise IsolationViolation(
                        f"symlink escape into hidden path: {p} -> {target}"
                    )


def assert_policy_isolatable(policy: DockerPolicy) -> None:
    """Cheap pre-launch sanity: the policy itself doesn't request weaker isolation
    than the foundation allows (e.g. an unpinned digest). Backends additionally
    declare capability gaps (M2 §7)."""
    if not policy.image_digest_pinned or not policy.image_digest_pinned.startswith("sha256:"):
        raise IsolationViolation(
            f"image_digest_pinned must be a sha256 digest, got {policy.image_digest_pinned!r}"
        )


def assert_backend_satisfies_policy(capabilities, policy: DockerPolicy) -> None:
    """Refuse a cell whose isolation the backend cannot provide (M2 §7).

    A backend declares its limits via ``capabilities``; rather than silently
    running with weaker isolation (e.g. downgrading an unimplemented network
    grant to ``none``), the runner refuses. The caller emits ``docker.capability_gap``
    and aborts.
    """
    gaps: list[str] = []
    if policy.network_policy not in capabilities.supported_network_modes:
        gaps.append(
            f"network_policy={policy.network_policy!r} not in backend-supported "
            f"{sorted(capabilities.supported_network_modes)}"
        )
    if policy.user_policy == "nonroot_ro_rootfs" and not capabilities.supports_ro_rootfs:
        gaps.append("user_policy=nonroot_ro_rootfs requires read-only rootfs support")
    if not capabilities.supports_pid_limit:
        gaps.append("pid_limit cannot be enforced by this backend")
    if not capabilities.supports_mem_limit:
        gaps.append("mem_limit cannot be enforced by this backend")
    if gaps:
        raise IsolationViolation("backend cannot satisfy policy: " + "; ".join(gaps))


# --------------------------------------------------------------------------- #
# Disk-quota enforcement (M2 §8.3) — bind mounts do NOT honor a Docker disk
# quota, so ``disk_limit`` needs a host-side monitor that fails the run on
# breach (a runaway fill would otherwise ENOSPC the M1 writer's fsync).
# --------------------------------------------------------------------------- #

_SIZE_UNITS = {"b": 1, "k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}


def parse_size(size: str) -> int:
    """Parse a Docker-style size (``"4g"``, ``"512m"``, ``"1024"``) to bytes."""
    s = str(size).strip().lower()
    if not s:
        raise ValueError("empty size")
    if s[-1] in _SIZE_UNITS:
        return int(float(s[:-1]) * _SIZE_UNITS[s[-1]])
    return int(s)


def dir_size_bytes(path: Path) -> int:
    """Total size of regular files under ``path`` (symlinks counted as their own
    link size, never followed — consistent with the no-follow capture)."""
    root = Path(path)
    total = 0
    if not root.exists():
        return 0
    for p in root.rglob("*"):
        try:
            if p.is_symlink() or p.is_file():
                total += p.lstat().st_size
        except OSError:
            continue
    return total


def check_disk_within_limit(mount_root: Path, disk_limit: str) -> tuple[int, int]:
    """Raise ``IsolationViolation`` if the writable tree exceeds ``disk_limit``.

    Returns ``(used_bytes, limit_bytes)`` when within the limit.
    """
    limit = parse_size(disk_limit)
    used = dir_size_bytes(mount_root)
    if used > limit:
        raise IsolationViolation(
            f"disk_limit breached: {used} bytes used > {limit} bytes ({disk_limit})"
        )
    return used, limit
