"""Register accepted names and their definitions for an extensible component.

Registries let tasks add vocabulary while sharing common record shapes and
interfaces. Examples include event classes, message kinds, scheduling policies,
and annotation labels. Callers validate names against the active registry;
registration alone does not implement or enforce a new behavior."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, Iterable, Iterator, Mapping, TypeVar

V = TypeVar("V")


class RegistryError(Exception):
    """Raised on an illegal registry composition (DESIGN §5.4)."""


@dataclass(frozen=True)
class RegistrySpec(Generic[V]):
    """A declarative, composable registry description.

    ``entries`` are this layer's own entries. ``inherits_from`` lists parent
    specs composed *before* this layer (left-to-right precedence: later parents
    and then this layer's own entries win on conflict only via ``override``).
    ``removes`` deletes inherited entry ids. ``overrides`` names the entry ids in
    ``entries`` that are permitted to redefine an inherited entry.
    """

    registry_id: str
    entries: Mapping[str, V] = field(default_factory=dict)
    inherits_from: tuple["RegistrySpec[V]", ...] = ()
    removes: tuple[str, ...] = ()
    overrides: frozenset[str] = frozenset()

    def resolve(self) -> "Registry[V]":
        """Compose this spec (and its ancestors) into a resolved ``Registry``.

        Linearization is a deterministic depth-first, left-to-right walk of the
        inheritance DAG with **last-occurrence** ordering (C3-style): a spec that
        appears via multiple paths in a diamond contributes once, at the latest
        position consistent with every path. Identical resolution across loads is
        asserted by the synthetic-registry diamond gate (§22).
        """
        order = _linearize(self)
        resolved: dict[str, V] = {}
        provenance: dict[str, str] = {}
        for spec in order:
            for entry_id in spec.removes:
                resolved.pop(entry_id, None)
                provenance.pop(entry_id, None)
            for entry_id, value in spec.entries.items():
                if entry_id in resolved and entry_id not in spec.overrides:
                    raise RegistryError(
                        f"registry {spec.registry_id!r} redefines inherited entry "
                        f"{entry_id!r} (from {provenance.get(entry_id)!r}) without "
                        f"override: true"
                    )
                resolved[entry_id] = value
                provenance[entry_id] = spec.registry_id
        return Registry(registry_id=self.registry_id, _entries=resolved)


def _linearize(spec: RegistrySpec[V]) -> list[RegistrySpec[V]]:
    """Deterministic left-to-right DFS linearization with last-occurrence order.

    Parents are emitted before children; when a spec is reachable by several
    paths (a diamond), only its last occurrence is kept, so the entry that "wins"
    is path-independent and stable across loads.
    """
    order: list[RegistrySpec[V]] = []

    def visit(node: RegistrySpec[V]) -> None:
        for parent in node.inherits_from:
            visit(parent)
        order.append(node)

    visit(spec)

    # Keep only the last occurrence of each spec (by identity), preserving order.
    seen: set[int] = set()
    deduped: list[RegistrySpec[V]] = []
    for node in reversed(order):
        if id(node) in seen:
            continue
        seen.add(id(node))
        deduped.append(node)
    deduped.reverse()
    return deduped


@dataclass(frozen=True)
class Registry(Generic[V]):
    """A resolved, active vocabulary. Core validates membership against this."""

    registry_id: str
    _entries: Mapping[str, V]

    def __contains__(self, entry_id: object) -> bool:
        return entry_id in self._entries

    def __getitem__(self, entry_id: str) -> V:
        try:
            return self._entries[entry_id]
        except KeyError:
            raise RegistryError(
                f"{entry_id!r} is not registered in {self.registry_id!r}"
            ) from None

    def get(self, entry_id: str, default: V | None = None) -> V | None:
        return self._entries.get(entry_id, default)

    def validate(self, entry_id: str) -> None:
        """Raise ``RegistryError`` if ``entry_id`` is not in the active registry."""
        if entry_id not in self._entries:
            raise RegistryError(
                f"{entry_id!r} is not registered in {self.registry_id!r}"
            )

    def ids(self) -> frozenset[str]:
        return frozenset(self._entries)

    def items(self) -> Iterable[tuple[str, V]]:
        return self._entries.items()

    def __iter__(self) -> Iterator[str]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)
