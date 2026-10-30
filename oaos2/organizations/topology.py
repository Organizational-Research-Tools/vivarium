"""Describe which role-to-role communication paths and kinds are allowed.

A topology is a graph of permitted connections. The default is complete: every
role can contact every other role. Explicit channels can narrow that permission.
allows() answers whether a connection is permitted; runtime callers record and
refuse disallowed messages or handoffs. The declaration alone does not deliver
messages or infer informal relationships."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Channel:
    """A directed edge: ``from_role`` may send these message ``kinds`` to ``to_role``.

    ``kinds`` containing ``"*"`` permits any kind on the edge.
    """

    from_role: str
    to_role: str
    kinds: frozenset[str] = field(default_factory=lambda: frozenset({"*"}))


@dataclass(frozen=True)
class Topology:
    """The role-to-role channel graph. Empty ``channels`` ⇒ complete graph (default)."""

    channels: tuple[Channel, ...] = ()

    def allows(self, from_role: str, to_role: str, kind: str) -> bool:
        """Whether ``from_role`` may send a ``kind`` message to ``to_role`` (DESIGN §18.1).

        With no declared channels the topology is complete (foundation default), so
        everything is allowed. Once any channel is declared the graph is a whitelist:
        only declared edges (matching kind, or a ``"*"`` edge) are admissible.
        """
        if not self.channels:
            return True  # complete topology — the foundation default
        return any(
            c.from_role == from_role and c.to_role == to_role
            and ("*" in c.kinds or kind in c.kinds)
            for c in self.channels
        )

    def reachable_targets(self, from_role: str, kind: str) -> set[str]:
        """The roles ``from_role`` may send ``kind`` to (for broadcast resolution)."""
        if not self.channels:
            return set()  # caller treats empty-with-complete-graph as "all others"
        return {c.to_role for c in self.channels
                if c.from_role == from_role and ("*" in c.kinds or kind in c.kinds)}
