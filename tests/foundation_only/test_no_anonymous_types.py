"""No-anonymous-types gate (M0 §1, DESIGN §17.1).

> Every *record-typed field* anywhere in the system must reference a canonical
> record by name; this check fails if a record-typed field points at a type with
> no schema.

We enforce this over the canonical records themselves: any field of a canonical
record whose annotation is (or contains) a ``CanonicalRecord`` subclass must be
one of the schematized canonical records. As later milestones add record-typed
fields elsewhere, they are caught here too because every record-typed field must
ultimately resolve to a member of ``CANONICAL_RECORDS``.
"""

from __future__ import annotations

import importlib
import pkgutil
import typing

import oaos2
from oaos2.trace.records import CANONICAL_RECORDS, CanonicalRecord


def _import_all_oaos2_modules() -> None:
    """Import every ``oaos2`` submodule so all ``CanonicalRecord`` subclasses are
    loaded — the gate must see record types defined *anywhere in the system*
    (M0 §1), not only those reachable from ``records.py`` at import time."""
    for mod in pkgutil.walk_packages(oaos2.__path__, prefix="oaos2."):
        try:
            importlib.import_module(mod.name)
        except Exception:  # pragma: no cover - optional deps (e.g. docker) may be absent
            pass


def _all_record_subclasses() -> set[type]:
    """Every concrete ``CanonicalRecord`` subclass currently loaded (recursive)."""
    seen: set[type] = set()
    frontier = [CanonicalRecord]
    while frontier:
        cls = frontier.pop()
        for sub in cls.__subclasses__():
            if sub not in seen:
                seen.add(sub)
                frontier.append(sub)
    return seen


def _referenced_types(annotation: object) -> list[type]:
    """Flatten an annotation into the concrete types it mentions."""
    found: list[type] = []
    if isinstance(annotation, type):
        found.append(annotation)
        return found
    for arg in typing.get_args(annotation):
        found.extend(_referenced_types(arg))
    return found


def test_no_record_type_is_defined_outside_the_registry() -> None:
    """An "anonymous" record — a ``CanonicalRecord`` subclass that exists but is
    not registered in ``CANONICAL_RECORDS`` — is exactly what the gate forbids.
    Without this, the field scan below is vacuous (records cross-link by string
    id, so they declare no record-typed fields), so this is the load-bearing half.
    """
    _import_all_oaos2_modules()
    unregistered = [
        cls.__name__
        for cls in _all_record_subclasses()
        if CANONICAL_RECORDS.get(cls.__name__) is not cls
    ]
    assert not unregistered, (
        "CanonicalRecord subclasses defined outside CANONICAL_RECORDS:\n"
        + "\n".join(sorted(unregistered))
    )


def test_every_record_typed_field_references_a_canonical_record() -> None:
    _import_all_oaos2_modules()
    offenders: list[str] = []
    record_classes = {cls.__name__: cls for cls in _all_record_subclasses()}
    for record_name, record_cls in record_classes.items():
        hints = typing.get_type_hints(record_cls)
        for field_name, annotation in hints.items():
            for tp in _referenced_types(annotation):
                if isinstance(tp, type) and issubclass(tp, CanonicalRecord):
                    if tp.__name__ not in CANONICAL_RECORDS:
                        offenders.append(
                            f"{record_name}.{field_name} -> {tp.__name__} "
                            f"(record type with no schema)"
                        )
    assert not offenders, "anonymous record-typed fields found:\n" + "\n".join(offenders)


def test_canonical_record_registry_is_self_consistent() -> None:
    # Every entry is keyed by its own class name and is a CanonicalRecord.
    for name, cls in CANONICAL_RECORDS.items():
        assert cls.__name__ == name
        assert issubclass(cls, CanonicalRecord)
