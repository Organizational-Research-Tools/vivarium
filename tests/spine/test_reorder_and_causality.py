"""INV-2/INV-3 via the reorder buffer (M1 §4, §5) — synchronous writer core.

(a) Prevention: an effect ingested *before* its cause is held in the reorder
    buffer and the cause is appended first, so the archive is already correct.
(b) Backstop: a genuine A↔B cycle never drains, is flushed at shutdown, and
    finalize's INV-3 fails the run.
"""

from __future__ import annotations

from oaos2.trace.emit import make_event
from oaos2.trace.invariants import causality_ok, load_all_events, run_invariants
from oaos2.trace.schema import Event
from oaos2.trace.spool import DurableEventQueue
from oaos2.trace.writer import TraceWriter


def _ingest_only_writer(run_dir):
    w = TraceWriter(run_dir, run_id="r")
    w.open_files()
    return w


def test_inv3_prevention_effect_before_cause(tmp_path) -> None:
    w = _ingest_only_writer(tmp_path)
    cause = make_event("run.started", "r")
    effect = make_event("model.invoked", "r", caused_by=cause.event_id, agent_id="a1")

    # Ingest the EFFECT first — it must be buffered, not appended.
    w.ingest(effect)
    assert effect.sequence_number is None  # not yet appended
    assert len(w.pending) == 1

    # Ingest the CAUSE — it appends, then the effect drains right after.
    w.ingest(cause)
    w.close()

    events = load_all_events(tmp_path)
    seq = {e["event_id"]: e["sequence_number"] for e in events}
    assert seq[cause.event_id] < seq[effect.event_id]  # seq(cause) < seq(effect)
    report = run_invariants(tmp_path, DurableEventQueue(tmp_path), w)
    # INV-1/2/3 hold; INV-4 not meaningful here (we bypassed the queue), so only
    # assert the causality invariants.
    assert "INV-2" not in " ".join(report.failures)
    assert "INV-3" not in " ".join(report.failures)


def test_inv2_multiparent_fanin_no_false_positive(tmp_path) -> None:
    w = _ingest_only_writer(tmp_path)
    handoff = make_event("handoff", "r", agent_id="a1")
    clar = make_event("chat.response", "r", agent_id="a2")
    work = make_event("file.write", "r", agent_id="a1")
    w.ingest(handoff)
    w.ingest(clar)
    w.ingest(work)
    # A commitment genuinely combining three antecedents (multi-parent DAG).
    commit = make_event(
        "state.committed",
        "r",
        caused_by=[handoff.event_id, clar.event_id, work.event_id],
        agent_id="a1",
    )
    w.ingest(commit)
    w.close()
    assert causality_ok(tmp_path)  # fan-in is not a cycle


def test_parent_event_id_edge_orders_in_reorder_buffer(tmp_path) -> None:
    """The structural ``parent_event_id`` nesting edge is an ordering edge too
    (DESIGN §6.3): a child ingested before its structural parent must buffer and
    the parent must precede it in the total order."""
    w = _ingest_only_writer(tmp_path)
    parent = make_event("chat.requested", "r", agent_id="a1",
                        payload={"target_agent_id": "a2", "paused_turn_id": "t~a2.1"})
    child = make_event("model.invoked", "r", agent_id="a2")
    child.parent_event_id = parent.event_id  # structural nesting, no caused_by edge

    w.ingest(child)
    assert child.sequence_number is None  # buffered on the structural parent
    assert len(w.pending) == 1
    w.ingest(parent)
    w.close()

    seq = {e["event_id"]: e["sequence_number"] for e in load_all_events(tmp_path)}
    assert seq[parent.event_id] < seq[child.event_id]
    assert causality_ok(tmp_path)


def test_inv2_cycle_through_parent_event_id_is_detected(tmp_path) -> None:
    """A cycle that runs through ``parent_event_id`` (not ``caused_by``) is caught
    by INV-2 — previously such an edge was invisible to the acyclicity check."""
    w = _ingest_only_writer(tmp_path)
    a_id, b_id = "01AAAAAAAAAAAAAAAAAAAAAAAA", "01BBBBBBBBBBBBBBBBBBBBBBBB"
    a = Event(event_class="model.invoked", run_id="r", event_id=a_id,
              parent_event_id=b_id, audience="researcher", channel="formal",
              phase_class="execution", phase_name="reasoning")
    b = Event(event_class="model.responded", run_id="r", event_id=b_id,
              parent_event_id=a_id, audience="researcher", channel="formal",
              phase_class="execution", phase_name="reasoning")
    w.ingest(a)
    w.ingest(b)
    assert len(w.pending) == 2  # neither structural parent ever satisfies
    w._flush_pending("shutdown")
    w.close()

    report = run_invariants(tmp_path, DurableEventQueue(tmp_path), w)
    assert not report.ok
    assert any("INV-3" in f for f in report.failures) or any("INV-2" in f for f in report.failures)


def test_inv3_backstop_real_cycle_fails_finalize(tmp_path) -> None:
    w = _ingest_only_writer(tmp_path)
    # A↔B: each cites the other, so neither can ever satisfy in the buffer.
    a_id, b_id = "01AAAAAAAAAAAAAAAAAAAAAAAA", "01BBBBBBBBBBBBBBBBBBBBBBBB"
    a = Event(event_class="model.invoked", run_id="r", event_id=a_id,
              caused_by_event_ids=[b_id], audience="researcher", channel="formal",
              phase_class="execution", phase_name="reasoning")
    b = Event(event_class="model.responded", run_id="r", event_id=b_id,
              caused_by_event_ids=[a_id], audience="researcher", channel="formal",
              phase_class="execution", phase_name="reasoning")
    w.ingest(a)
    w.ingest(b)
    assert len(w.pending) == 2  # both stuck
    w._flush_pending("shutdown")  # release them (a reorder_flush is recorded)
    w.close()

    assert not causality_ok(tmp_path)
    report = run_invariants(tmp_path, DurableEventQueue(tmp_path), w)
    assert not report.ok
    assert any("INV-3" in f for f in report.failures)
