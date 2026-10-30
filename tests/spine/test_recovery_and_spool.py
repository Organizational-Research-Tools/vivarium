"""Recovery + durable-spool replay + index rebuild (M1 §4, §6, §8 Q2).

Covers the archive-validity / fault-tolerance surface:
- torn-line recovery (truncate unparseable tail, rebuild index, run.recovered)
- runner-crash spool replay (enqueued-but-unappended events survive, no drops)
- index rebuild is *logically* equivalent (canonical-SELECT hash matches)
"""

from __future__ import annotations

import json

from oaos2.trace.emit import make_event
from oaos2.trace.index_db import rebuild
from oaos2.trace.invariants import (
    check_no_drops_via_spool,
    index_fingerprint,
    InvariantReport,
    load_all_events,
)
from oaos2.trace.spine import RunSpine
from oaos2.trace.spool import DurableEventQueue
from oaos2.trace.writer import TraceWriter


async def _clean_run(tmp_path) -> None:
    spine = RunSpine(tmp_path, run_id="run1")
    await spine.start()
    prev = await spine.emit_event("run.started")
    for _ in range(5):
        prev = await spine.emit_event("model.invoked", caused_by=prev, agent_id="a1")
    report = await spine.finalize("completed")
    assert report.ok, report.failures


async def test_index_rebuild_is_logically_equivalent(tmp_path) -> None:
    await _clean_run(tmp_path)
    original = index_fingerprint(tmp_path / "trace" / "index.sqlite")
    rebuilt_path = tmp_path / "trace" / "index_rebuilt.sqlite"
    rebuild(tmp_path, rebuilt_path)
    assert index_fingerprint(rebuilt_path) == original


async def test_torn_line_recovery(tmp_path) -> None:
    await _clean_run(tmp_path)
    events_file = tmp_path / "trace" / "events.jsonl"

    # Simulate a crash mid-write: append a torn (truncated) JSON line.
    with open(events_file, "a") as f:
        f.write('{"event_id": "01TORNTORNTORNTORNTORNTOR", "event_class": "mod')

    # A fresh writer recovers: truncate torn tail, rebuild index, emit run.recovered.
    queue = DurableEventQueue(tmp_path)
    writer = TraceWriter(tmp_path, run_id="run1")
    writer.open_and_recover(queue)
    writer.close()

    assert writer.recovery_tail_count == 1
    infra = [
        json.loads(l)
        for l in (tmp_path / "trace" / "infra.jsonl").read_text().splitlines()
        if l.strip()
    ]
    infra_classes = {e["event_class"] for e in infra}
    assert "run.recovered" in infra_classes
    assert "writer.restarted" in infra_classes
    # The torn line is gone; every remaining line parses.
    for line in events_file.read_text().splitlines():
        if line.strip():
            json.loads(line)


async def test_runner_crash_spool_replay_no_drops(tmp_path) -> None:
    # Simulate: events were enqueued (write-ahead spooled) but the runner crashed
    # before the writer appended them. A fresh writer must replay them with zero loss.
    (tmp_path / "trace").mkdir(parents=True, exist_ok=True)
    queue = DurableEventQueue(tmp_path)
    e0 = make_event("run.started", "run1")
    e1 = make_event("model.invoked", "run1", caused_by=e0.event_id, agent_id="a1")
    e2 = make_event("model.responded", "run1", caused_by=e1.event_id, agent_id="a1")
    for e in (e0, e1, e2):
        queue._spool(e)  # write-ahead spool ONLY — never reached the writer

    # New process recovers: nothing on disk, but the spool replays the 3 events.
    writer = TraceWriter(tmp_path, run_id="run1")
    writer.open_and_recover(queue)
    writer.close()

    appended = {e["event_id"] for e in load_all_events(tmp_path)}
    assert {e0.event_id, e1.event_id, e2.event_id} <= appended  # no drops

    # The cross-crash no-drop check passes, and INV-4 balances post-recovery.
    report = InvariantReport()
    check_no_drops_via_spool(tmp_path, queue, report)
    assert report.ok, report.failures

    from oaos2.trace.invariants import check_inv4

    inv4 = InvariantReport()
    check_inv4(tmp_path, queue, writer, inv4)
    assert inv4.ok, inv4.failures


async def test_unclean_restart_without_torn_line_still_rebuilds(tmp_path) -> None:
    # A clean-tail crash: every line parses but no terminal record was written.
    # Recovery must still rebuild the index (gated on missing-terminal, not torn).
    (tmp_path / "trace").mkdir(parents=True, exist_ok=True)
    queue = DurableEventQueue(tmp_path)
    writer = TraceWriter(tmp_path, run_id="run1")
    writer.open_files()
    e0 = make_event("run.started", "run1")
    e1 = make_event("model.invoked", "run1", caused_by=e0.event_id, agent_id="a1")
    writer.ingest(e0)
    writer.ingest(e1)
    writer.close()  # NO terminal record written → unclean

    writer2 = TraceWriter(tmp_path, run_id="run1")
    writer2.open_and_recover(DurableEventQueue(tmp_path))
    writer2.close()
    infra_classes = {
        json.loads(l)["event_class"]
        for l in (tmp_path / "trace" / "infra.jsonl").read_text().splitlines()
        if l.strip()
    }
    assert "run.recovered" in infra_classes  # rebuilt despite no torn line
