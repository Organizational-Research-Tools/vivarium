"""Connect host workspace directories to an agent's container.

visible maps to /visible read-only. The agent's private scratch maps to
/work/agents/{id} with read and write access. shared and submitted map under
/work read-only, so container tools cannot bypass their host-side write paths.
Hidden scoring paths are not mounted. These workspace mounts are part of the
container filesystem; temporary container storage is separate."""

from __future__ import annotations

from oaos2.docker.policy import Mount
from oaos2.kernel.run_dir import RunDir
from oaos2.workspace.zones import MountMode


OMITTABLE = frozenset({"submitted"})


def build_mounts(run_dir: RunDir, agent_id: str, omit: frozenset | set | tuple = ()) -> list[Mount]:
    """Produce the agent's container mount set (M2 §3). Writable = bind only.

    ``omit`` names read-only mounts a pack leaves out (manifest ``container_mounts_omit``);
    only a restriction, so only the read-only ``submitted`` mount can be named. The materials
    lab omits it: its file names and payloads carry the internal project ids and recipes the
    coded presentation hides (PC1 presentation revision, 2026-09-26)."""
    bad = set(omit) - OMITTABLE
    if bad:
        raise ValueError(f"cannot omit mounts {sorted(bad)}; omittable: {sorted(OMITTABLE)}")
    run_dir.ensure_agent_scratch(agent_id)
    mounts = [
        Mount(run_dir.visible, "/visible", MountMode.RO),
        Mount(run_dir.agent_scratch(agent_id), f"/work/agents/{agent_id}", MountMode.RW),
        Mount(run_dir.shared, "/work/shared", MountMode.RO),
    ]
    if "submitted" not in omit:
        mounts.append(Mount(run_dir.submitted, "/work/submitted", MountMode.RO))
    return mounts
