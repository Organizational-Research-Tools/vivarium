"""Archive schema migration (DESIGN §6.6: "Migration is tooling").

Archive-level ``schema_version`` is primary. Default policy is **forward-migrate old
archives**: a versioned registry maps ``from_version -> to_version`` to a pure
event-transform; ``migrate_archive`` chains the registered steps from an archive's
recorded version up to the current ``SCHEMA_VERSION`` and rewrites ``trace/*.jsonl``
(+ the manifest's ``schema_version``). The foundation ships **zero** migrations — the
schema has not bumped — so ``migrate_archive`` is an identity that reports
``migrated=False``; the framework exists so the **first** major bump ships its forward
migration under the CI gate (§6.6) without reshaping anything.

A migration step is ``(events: list[dict]) -> list[dict]``: a pure function over the
event dicts (it may add/rename/default fields, never drop the envelope or its causal
links — INV-1…4 must still hold afterward, which the migration test asserts).
"""

from __future__ import annotations

import json
from pathlib import Path

from oaos2.trace.schema import SCHEMA_VERSION

# Registry: from_version -> (to_version, transform). One entry per single-step bump;
# multi-step upgrades chain through intermediate versions deterministically.
_MIGRATIONS: dict[str, tuple[str, object]] = {}


class MigrationError(Exception):
    """No registered path from an archive's schema_version to the current one (§6.6)."""


def register_migration(from_version: str, to_version: str, transform) -> None:
    """Register a single-step forward migration. Re-registering a from_version is an error."""
    if from_version in _MIGRATIONS:
        raise MigrationError(f"a migration from {from_version!r} is already registered")
    _MIGRATIONS[from_version] = (to_version, transform)


def migration_path(from_version: str, to_version: str = SCHEMA_VERSION) -> list[str]:
    """The chain of versions from ``from_version`` to ``to_version`` (inclusive), or raise."""
    chain = [from_version]
    cur = from_version
    seen = {from_version}
    while cur != to_version:
        step = _MIGRATIONS.get(cur)
        if step is None:
            raise MigrationError(
                f"no registered migration from {cur!r} toward {to_version!r} "
                f"(have steps from: {sorted(_MIGRATIONS)})"
            )
        cur = step[0]
        if cur in seen:  # a cyclic registry (e.g. A->B, B->A) would loop/OOM forever
            raise MigrationError(f"cyclic migration path revisits {cur!r}: {chain + [cur]}")
        seen.add(cur)
        chain.append(cur)
    return chain


def _read_version(run_dir: Path) -> str:
    mp = run_dir / "manifest.json"
    if mp.exists():
        try:
            v = json.loads(mp.read_text()).get("schema_version")
            if v:
                return v
        except (ValueError, OSError):
            pass
    # Fall back to the first event's schema_version.
    ev = run_dir / "trace" / "events.jsonl"
    if ev.exists():
        for line in ev.read_text().splitlines():
            if line.strip():
                return json.loads(line).get("schema_version", SCHEMA_VERSION)
    return SCHEMA_VERSION


def migrate_archive(run_dir: Path, *, to_version: str = SCHEMA_VERSION) -> dict:
    """Forward-migrate an archive in place to ``to_version`` (default: current).

    Returns ``{from_version, to_version, migrated, steps}``. A no-op (``migrated=False``)
    when the archive is already current — which is always true today (no migrations
    registered). Rewrites ``trace/events.jsonl`` + ``trace/infra.jsonl`` and the
    manifest's ``schema_version`` only when steps actually run.
    """
    run_dir = Path(run_dir)
    frm = _read_version(run_dir)
    if frm == to_version:
        return {"from_version": frm, "to_version": to_version, "migrated": False, "steps": []}

    chain = migration_path(frm, to_version)
    steps = list(zip(chain, chain[1:]))
    for stream in ("events.jsonl", "infra.jsonl"):
        path = run_dir / "trace" / stream
        if not path.exists():
            continue
        events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        for src, _dst in steps:
            transform = _MIGRATIONS[src][1]
            events = transform(events)
        for e in events:
            e["schema_version"] = to_version
        path.write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in events))

    mp = run_dir / "manifest.json"
    if mp.exists():
        try:
            m = json.loads(mp.read_text())
            m["schema_version"] = to_version
            mp.write_text(json.dumps(m, indent=2, sort_keys=True))
        except (ValueError, OSError):
            pass
    return {"from_version": frm, "to_version": to_version, "migrated": True,
            "steps": [f"{a}->{b}" for a, b in steps]}
