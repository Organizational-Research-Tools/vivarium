"""DockerPolicy (M2 §5, DESIGN §7.2) — declarative isolation, resolved by precedence.

A ``DockerPolicy`` declares everything about the sandbox: the pinned image +
digest (verified fail-closed at launch), the visible/writable/hidden zones, the
env allowlist (no credentials), network policy (``disabled`` by default — the
container needs no network because model calls are host-side, M2 §0), resource
limits, user policy, and the capture policy.

Precedence is **Organization > Role > Agent** (DESIGN §4.9): a tighter scope may
only *narrow*. The resolved policy's ``hash()`` enters the run manifest.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from oaos2.workspace.zones import MountMode


@dataclass(frozen=True)
class Mount:
    """One bind/ro mount the container sees (M2 §3)."""

    host_path: Path
    container_path: str
    mode: MountMode
    is_named_volume: bool = False  # forbidden for writable zones (M2 §1 decision 2)


@dataclass
class DockerPolicy:
    image_ref: str
    image_digest_pinned: str  # sha256:… — verified at launch, fail-closed
    visible_mounts: list[Mount] = field(default_factory=list)  # ro task materials
    writable_zones: list[str] = field(default_factory=list)  # → bind mounts under container_mount/
    hidden_host_paths: list[Path] = field(default_factory=list)  # never mounted; checked launch+capture
    env_allowlist: dict[str, str] = field(default_factory=dict)  # NO credentials (boundary-tested)
    network_policy: str = "disabled"  # disabled | model_api_only | allowlist | unrestricted
    mem_limit: str = "2g"
    cpu_limit: float = 2.0
    pid_limit: int = 512
    disk_limit: str = "4g"
    wall_clock_limit: int = 1800  # seconds; per-container hard cap
    user_policy: str = "nonroot_ro_rootfs"
    tmpfs_tmp: bool = True  # writable /tmp via tmpfs (ephemeral, never captured) — M2 §8.6
    capture_globs: list[str] = field(default_factory=lambda: ["**/*"])
    capture_on: tuple[str, ...] = ("success", "failure", "interrupt")

    def hash(self) -> str:
        """Stable hash of the resolved policy (enters the manifest)."""
        payload = asdict(self)
        payload["visible_mounts"] = [
            {"host_path": str(m.host_path), "container_path": m.container_path, "mode": m.mode.value}
            for m in self.visible_mounts
        ]
        payload["hidden_host_paths"] = [str(p) for p in self.hidden_host_paths]
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


# Network policies ordered from strongest (most isolated) to weakest.
_NETWORK_RANK = {"disabled": 0, "model_api_only": 1, "allowlist": 2, "unrestricted": 3}


def resolve_docker_policy(
    *,
    org_policy: DockerPolicy | None,
    role_policy: DockerPolicy | None,
    agent_policy: DockerPolicy,
) -> DockerPolicy:
    """Resolve with Organization > Role > Agent precedence; a tighter scope may
    only *narrow*, never broaden (DESIGN §4.9; validators reject broadening at load).

    The outermost present scope sets the network grant (the ceiling). Each tighter
    scope's ``network_policy`` must be no more permissive than its enclosing scope;
    a broadening override raises ``ValueError`` (the load-time rejection). A valid
    chain narrows monotonically, so the resolved policy takes the agent's concrete
    sandbox config (image, zones, limits) with the innermost (most restrictive)
    network grant. The full multi-field precedence engine lands with the
    organization spec (M5); M2 enforces the network dimension that gates isolation.
    """
    chain = [p for p in (org_policy, role_policy, agent_policy) if p is not None]
    effective_net = chain[0].network_policy
    for inner in chain[1:]:
        if _NETWORK_RANK[inner.network_policy] > _NETWORK_RANK[effective_net]:
            raise ValueError(
                f"scope precedence: network_policy {inner.network_policy!r} broadens "
                f"enclosing grant {effective_net!r} (a tighter scope may only narrow)"
            )
        effective_net = inner.network_policy
    return _with_network(agent_policy, effective_net)


def _with_network(policy: DockerPolicy, network_policy: str) -> DockerPolicy:
    from dataclasses import replace

    return replace(policy, network_policy=network_policy)
