"""Archive schema migration (DESIGN §6.6): forward-migrate is identity today (no
registered migrations), and the framework chains + applies steps when one exists."""

from __future__ import annotations

import json

import pytest

from oaos2.kernel.run_dir import RunDir
from oaos2.trace import migrate as mig
from oaos2.trace.schema import SCHEMA_VERSION
from oaos2.trace.spine import RunSpine


@pytest.fixture
def _clean_registry():
    saved = dict(mig._MIGRATIONS)
    yield
    mig._MIGRATIONS.clear()
    mig._MIGRATIONS.update(saved)


async def _archive(tmp_path) -> RunDir:
    rd = RunDir.create(tmp_path, "e", "p", "r")
    rd.manifest_path.write_text(json.dumps({"run_id": "r", "schema_version": SCHEMA_VERSION}))
    spine = RunSpine(rd.root, run_id="r")
    await spine.start()
    c = await spine.emit_event("run.started", payload={"run_id": "r"})
    await spine.emit_event("turn.completed", agent_id="A", turn_id="A.t1", caused_by=c,
                           payload={"result": "finish_turn"})
    await spine.finalize("completed")
    return rd


async def test_migrate_is_noop_when_current(tmp_path) -> None:
    rd = await _archive(tmp_path)
    result = mig.migrate_archive(rd.root)
    assert result["migrated"] is False and result["from_version"] == SCHEMA_VERSION


async def test_registered_migration_applies_and_rewrites(tmp_path, _clean_registry) -> None:
    rd = await _archive(tmp_path)
    future = "2099-01-01.v2"

    def _bump(events):  # pure transform: stamp a migration marker into each payload
        for e in events:
            e.setdefault("payload", {})["_migrated"] = True
        return events

    mig.register_migration(SCHEMA_VERSION, future, _bump)
    result = mig.migrate_archive(rd.root, to_version=future)
    assert result["migrated"] is True and result["steps"] == [f"{SCHEMA_VERSION}->{future}"]

    events = [json.loads(line) for line in
              (rd.root / "trace" / "events.jsonl").read_text().splitlines() if line.strip()]
    assert events and all(e["schema_version"] == future for e in events)
    assert all(e["payload"].get("_migrated") for e in events)
    assert json.loads(rd.manifest_path.read_text())["schema_version"] == future


def test_migration_path_raises_without_route(_clean_registry) -> None:
    with pytest.raises(mig.MigrationError):
        mig.migration_path("1999-01-01.v0", SCHEMA_VERSION)


def test_migration_path_detects_cycle(_clean_registry) -> None:
    # A cyclic registry (A->B, B->A) must raise, not loop/OOM, when the target is unreachable.
    mig.register_migration("a.v1", "b.v1", lambda evs: evs)
    mig.register_migration("b.v1", "a.v1", lambda evs: evs)
    with pytest.raises(mig.MigrationError, match="cyclic"):
        mig.migration_path("a.v1", "c.v1")
