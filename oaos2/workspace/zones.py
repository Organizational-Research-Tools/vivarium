"""Zone classes (DESIGN §9) — the closed set the foundation enforces.

Zone *names* are task-pack-declared strings (an open registry); the foundation
enforces a small closed set of zone **classes**, and those classes map directly
to container mount modes (M2 §3):

| zone_class      | container sees | enforced by                     |
|-----------------|----------------|---------------------------------|
| agent_writable  | rw (bind)      | per-agent bind mount            |
| task_visible    | ro             | Docker ro mount                 |
| hidden          | not mounted    | absence + symlink-escape scan   |
| temp            | rw (ephemeral) | tmpfs / scratch (not captured)  |
| infrastructure  | not mounted    | host-only                       |

The ``submitted`` commit zone is a *task_visible*-to-the-container zone in mount
terms (OS-read-only), even though the host ``commit()`` path writes it — that is
the whole point of the OS-enforced commit zone (§8.1).
"""

from __future__ import annotations

from enum import Enum


class ZoneClass(str, Enum):
    AGENT_WRITABLE = "agent_writable"
    TASK_VISIBLE = "task_visible"
    HIDDEN = "hidden"
    TEMP = "temp"
    INFRASTRUCTURE = "infrastructure"


ZONE_CLASSES: frozenset[str] = frozenset(z.value for z in ZoneClass)


class MountMode(str, Enum):
    RW = "rw"
    RO = "ro"
    NOT_MOUNTED = "not_mounted"


def zone_class_mount_mode(zone_class: str) -> MountMode:
    """The container mount mode a zone class resolves to (M2 §3)."""
    if zone_class == ZoneClass.AGENT_WRITABLE.value:
        return MountMode.RW
    if zone_class in (ZoneClass.TASK_VISIBLE.value, ZoneClass.TEMP.value):
        # temp is rw but ephemeral; task_visible is ro. temp is handled as tmpfs by
        # the backend, not a captured bind mount — see DockerPolicy. For mount-mode
        # purposes task_visible is the ro case we assert on.
        return MountMode.RO if zone_class == ZoneClass.TASK_VISIBLE.value else MountMode.RW
    # hidden + infrastructure are never mounted into the container.
    return MountMode.NOT_MOUNTED
