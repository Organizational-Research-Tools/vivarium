"""End-to-end spine tests (M1): INV-1/INV-4, two-stream routing, backpressure.

These drive the full ``RunSpine`` (durable queue + single writer) the way a run
does, then assert the archive-validity invariants over the produced archive.
"""

from __future__ import annotations

import json

import pytest

from oaos2.trace.invariants import load_all_events, run_invariants
from oaos2.trace.routing import Stream, assert_routing_guardrail, route
from oaos2.trace.schema import Event
from oaos2.trace.spine import RunSpine


async def test_clean_run_all_invariants_hold(tmp_path) -> None:
    spine = RunSpine(tmp_path, run_id="run1")
    await spine.start()
    id0 = await spine.emit_event("run.started")
    id1 = await spine.emit_event("agent.launched", caused_by=id0, agent_id="a1")
    id2 = await spine.emit_event("model.invoked", caused_by=id1, agent_id="a1")
    await spine.emit_event("model.responded", caused_by=id2, agent_id="a1")
    report = await spine.finalize("completed")
    assert report.ok, report.failures

    # The terminal record is the last spine line (DESIGN §6.4).
    events = [
        json.loads(line)
        for line in (tmp_path / "trace" / "events.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert events[-1]["event_class"] == "run.completed"
    # Spool reclaimed on a clean finalize.
    assert not (tmp_path / "trace" / "spool" / "spool.log").exists()


async def test_inv1_gapfree_over_union_of_both_streams(tmp_path) -> None:
    spine = RunSpine(tmp_path, run_id="run1")
    await spine.start()
    # Mix spine (researcher/formal) and infra (cost is researcher/formal but
    # spine.backpressure-style infra) events; the union must be gap-free.
    prev = await spine.emit_event("run.started")
    for _ in range(20):
        prev = await spine.emit_event("model.invoked", caused_by=prev, agent_id="a1")
    # An explicitly infra-routed event consumes a sequence number on infra.jsonl.
    await spine.emit(
        Event(event_class="spine.queue_depth", run_id="run1", payload={"depth": 1})
    )
    report = await spine.finalize("completed")
    assert report.ok, report.failures

    events = load_all_events(tmp_path)
    seqs = [e["sequence_number"] for e in events]
    assert seqs == list(range(len(events)))  # gap-free union

    # events.jsonl alone is intentionally gappy (infra consumes seq numbers).
    spine_only = [
        json.loads(line)
        for line in (tmp_path / "trace" / "events.jsonl").read_text().splitlines()
        if line.strip()
    ]
    infra_only = [
        json.loads(line)
        for line in (tmp_path / "trace" / "infra.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert infra_only, "infra stream should hold the queue_depth event"
    # No infra event leaked onto the spine and vice-versa (M0 §5.1 guardrail).
    for e in spine_only:
        assert_routing_guardrail(Event.from_dict(e), Stream.EVENTS)
    for e in infra_only:
        assert_routing_guardrail(Event.from_dict(e), Stream.INFRA)


async def test_backpressure_blocks_without_dropping(tmp_path) -> None:
    # Tiny queue forces backpressure; nothing is dropped (blocking enqueue).
    spine = RunSpine(tmp_path, run_id="run1", max_depth=2)
    await spine.start()
    prev = await spine.emit_event("run.started")
    for _ in range(50):
        prev = await spine.emit_event("model.invoked", caused_by=prev, agent_id="a1")
    report = await spine.finalize("completed")
    assert report.ok, report.failures
    # Backpressure events were synthesized and routed to infra.
    infra_lines = (tmp_path / "trace" / "infra.jsonl").read_text().splitlines()
    classes = {json.loads(l)["event_class"] for l in infra_lines if l.strip()}
    # (May or may not trigger depending on scheduling, but the run must stay valid.)
    assert "spine.backpressure" in classes or spine.queue.backpressure_event_count == 0


async def test_emit_unknown_class_is_rejected(tmp_path) -> None:
    from oaos2.trace.emit import ProtocolViolation

    spine = RunSpine(tmp_path, run_id="run1")
    await spine.start()
    with pytest.raises(ProtocolViolation):
        await spine.emit_event("not.a.real.class")
    await spine.finalize("completed")
