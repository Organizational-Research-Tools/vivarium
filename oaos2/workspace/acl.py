"""Zones + FileAccessPolicy (M4 §1, DESIGN §9).

Zone *names* are task-pack strings; the foundation enforces the closed zone
*classes* (``zones.py``). A ``Zone`` binds a name to its class, whether it is
*shared* (an ``agent_writable`` zone with more than one granted writer — the
per-file byte lock applies there), and its enforcement layer (``os`` vs
``software`` — the §8 integrity claim).

A ``FileAccessPolicy`` (per role/agent, precedence org > role > agent) declares
``zones_visible``/``zones_writable``/``zones_executable``, explicit ``forbidden``,
and ``fall_through: deny`` — anything not granted is denied. A denied tool call is
``tool.denied`` at the runner boundary (M5), never a silent drop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum



class Enforcement(str, Enum):
    OS = "os"  # the hard guarantee (mount mode / per-agent isolation)
    SOFTWARE = "software"  # per-role refinement, checked before dispatch


@dataclass(frozen=True)
class Zone:
    name: str  # task-pack-declared string
    zone_class: str  # one of ZoneClass
    is_shared: bool = False  # agent_writable with >1 granted writer
    enforcement: str = Enforcement.OS.value


class AccessDenied(Exception):
    """A FileAccessPolicy denial (→ tool.denied at the runner, M5 §10.3)."""


@dataclass
class FileAccessPolicy:
    # ``None`` means "this scope does not constrain the dimension" (inherit the
    # enclosing grant); an explicit ``frozenset`` — *including the empty set* —
    # is a constraint, so a scope can legitimately narrow a grant down to nothing
    # (DESIGN §4.9). Default-deny still holds: an unspecified/empty grant on a
    # *resolved* policy means nothing is granted.
    zones_visible: frozenset[str] | None = None
    zones_writable: frozenset[str] | None = None
    zones_executable: frozenset[str] | None = None
    forbidden: frozenset[str] = field(default_factory=frozenset)
    fall_through: str = "deny"  # the only foundation value (DESIGN §9)

    def may_read(self, zone_name: str) -> bool:
        return zone_name not in self.forbidden and zone_name in (self.zones_visible or frozenset())

    def may_write(self, zone_name: str) -> bool:
        return zone_name not in self.forbidden and zone_name in (self.zones_writable or frozenset())

    def may_execute(self, zone_name: str) -> bool:
        return zone_name not in self.forbidden and zone_name in (self.zones_executable or frozenset())

    def require_write(self, zone_name: str) -> None:
        if not self.may_write(zone_name):
            raise AccessDenied(f"write to zone {zone_name!r} denied (fall_through: {self.fall_through})")


def _narrow(outer: frozenset[str] | None, inner: frozenset[str] | None) -> frozenset[str] | None:
    """Intersect two grant sets under "tighter scope may only narrow" semantics.

    Delegates to the ONE shared primitive (``organizations.precedence.narrow_grant``) so
    the file-access channel and the other policy channels (tools/comm/model) can never
    drift on the rule. ``None`` inherits; two specified sets intersect (an explicit empty
    inner narrows to empty).
    """
    from oaos2.organizations.precedence import narrow_grant
    return narrow_grant(outer, inner)


def resolve_file_access_policy(
    *,
    org: FileAccessPolicy | None,
    role: FileAccessPolicy | None,
    agent: FileAccessPolicy,
) -> FileAccessPolicy:
    """Org > Role > Agent; a tighter scope may only *narrow* (DESIGN §4.9).

    Each grant set at a tighter scope is intersected with the enclosing grant
    (you cannot gain access an outer scope didn't give); ``forbidden`` is the
    union (a tighter scope may always forbid more).
    """
    scopes = [s for s in (org, role, agent) if s is not None]
    visible = scopes[0].zones_visible
    writable = scopes[0].zones_writable
    executable = scopes[0].zones_executable
    forbidden = set(scopes[0].forbidden)
    for inner in scopes[1:]:
        visible = _narrow(visible, inner.zones_visible)
        writable = _narrow(writable, inner.zones_writable)
        executable = _narrow(executable, inner.zones_executable)
        forbidden |= set(inner.forbidden)
    return FileAccessPolicy(
        zones_visible=frozenset(visible) if visible is not None else None,
        zones_writable=frozenset(writable) if writable is not None else None,
        zones_executable=frozenset(executable) if executable is not None else None,
        forbidden=frozenset(forbidden),
        fall_through="deny",
    )
