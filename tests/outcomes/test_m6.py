"""M6 tests: coordination, commit()/outcomes, evaluators, assisted label,
plus the synthetic-registry and zero-diff viability gates (DESIGN §22)."""

from __future__ import annotations

import pytest

from oaos2.communication.messages import COMM_KIND_SPEC
from oaos2.evaluation.foundation_schema import FieldSchema, SchemaEvaluator
from oaos2.evaluation.public_feedback import (
    EvaluationRejected,
    PublicFeedbackSchema,
    write_evaluation,
)
from oaos2.kernel.run_dir import RunDir
from oaos2.outcomes.commit import OutcomeCoordinator
from oaos2.outcomes.contracts import (
    ClosureCondition,
    ClosureKind,
    Commitment,
    InvalidContract,
    OutcomeContract,
)
from oaos2.outcomes.label import label_outcome
from oaos2.pricing.attribution import ACTIVITY_CLASS_SPEC
from oaos2.protocols.coordination import (
    AggregationContract,
    ContractShape,
    CoordinationContract,
    HandoffContract,
)
from oaos2.protocols.markers import MarkerPolicy, extract_handoff
from oaos2.registry import RegistrySpec
from oaos2.trace.event_classes import EVENT_CLASS_SPEC
from oaos2.trace.invariants import load_all_events
from oaos2.trace.spine import RunSpine


async def _spine(tmp_path):
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = RunSpine(rd.root, run_id="run1")
    await spine.start()
    return rd, spine


def _simple_contract() -> OutcomeContract:
    return OutcomeContract(
        outcome_id="o1",
        commitments=[Commitment(commitment_id="final", kind="artifact_submission")],
    )


# --------------------------------------------------------------------------- #
# commit() and closure
# --------------------------------------------------------------------------- #


async def test_commit_closes_outcome_and_writes_submitted_zone(tmp_path) -> None:
    rd, spine = await _spine(tmp_path)
    coord = OutcomeCoordinator(_simple_contract(), spine, rd.submitted)
    sc = await coord.commit(commitment_id="final", payload={"answer": 42}, agent_id="a1", session_id="s1")
    report = await spine.finalize("completed")
    assert report.ok, report.failures
    assert sc is not None and coord.closed
    classes = {e["event_class"] for e in load_all_events(rd.root)}
    assert {"state.committed", "outcome.closed"} <= classes
    # The commitment payload is in the OS-ro-to-container submitted/ zone.
    assert (rd.submitted / "final.json").exists()


async def test_commit_refuses_nonobject_even_without_field_constraints(tmp_path) -> None:
    from oaos2.outcomes.conformance import CommitmentConformanceError

    rd, spine = await _spine(tmp_path)
    coord = OutcomeCoordinator(_simple_contract(), spine, rd.submitted)
    try:
        with pytest.raises(CommitmentConformanceError, match='JSON object'):
            await coord.commit(commitment_id='final', payload=['answer', 42],
                               agent_id='a1', session_id='s1')
        assert not coord.committed and not coord.closed
        assert not (rd.submitted / 'final.json').exists()
    finally:
        await spine.finalize('completed')


async def test_commit_before_blockers_refused(tmp_path) -> None:
    rd, spine = await _spine(tmp_path)
    contract = OutcomeContract(
        outcome_id="o1",
        commitments=[
            Commitment(commitment_id="draft", kind="artifact_submission"),
            Commitment(commitment_id="final", kind="artifact_submission", blocks=["draft"]),
        ],
    )
    coord = OutcomeCoordinator(contract, spine, rd.submitted)
    blocked = await coord.commit(commitment_id="final", payload={}, agent_id="a1", session_id="s1")
    await spine.finalize("completed")
    assert blocked is None  # refused: blocker not yet committed
    assert "protocol.violation" in {e["event_class"] for e in load_all_events(rd.root)}


def test_cyclic_blocks_rejected_at_load() -> None:
    contract = OutcomeContract(
        outcome_id="o1",
        commitments=[
            Commitment(commitment_id="a", kind="k", blocks=["b"]),
            Commitment(commitment_id="b", kind="k", blocks=["a"]),
        ],
    )
    with pytest.raises(InvalidContract):
        contract.validate()


# --------------------------------------------------------------------------- #
# assisted / unassisted label
# --------------------------------------------------------------------------- #


async def test_unassisted_label_clean_outcome(tmp_path) -> None:
    rd, spine = await _spine(tmp_path)
    coord = OutcomeCoordinator(_simple_contract(), spine, rd.submitted)
    work = await spine.emit_event("file.write", agent_id="a1", payload={})
    await coord.commit(commitment_id="final", payload={"x": 1}, agent_id="a1", session_id="s1", caused_by=work)
    await spine.finalize("completed")
    label = label_outcome(rd.root, list(coord.committed_event_ids.values()))
    assert label == "unassisted"


async def test_assisted_label_with_intervention_in_ancestry(tmp_path) -> None:
    rd, spine = await _spine(tmp_path)
    coord = OutcomeCoordinator(_simple_contract(), spine, rd.submitted)
    work = await spine.emit_event("file.write", agent_id="a1", payload={})
    iv = await spine.emit_event(
        "intervention.recorded", agent_id="a1", caused_by=work,
        payload={"kind": "marker_retry", "class": "recorded"},
    )
    # The commitment consumed the assisted work (multi-parent: work + intervention).
    await coord.commit(commitment_id="final", payload={"x": 1}, agent_id="a1", session_id="s1",
                       caused_by=[work, iv])
    await spine.finalize("completed")
    label = label_outcome(rd.root, list(coord.committed_event_ids.values()))
    assert label == "assisted"


# --------------------------------------------------------------------------- #
# marker policy
# --------------------------------------------------------------------------- #


async def test_marker_extraction_present(tmp_path) -> None:
    rd, spine = await _spine(tmp_path)
    seed = await spine.emit_event("agent.observed", agent_id="a1", payload={})
    res = await extract_handoff(
        narration="here is my work <handoff>PAYLOAD</handoff> done",
        policy=MarkerPolicy(), spine=spine, agent_id="a1", turn_id="t1", caused_by=seed,
    )
    await spine.finalize("completed")
    assert res.payload == "PAYLOAD" and not res.is_stub


async def test_marker_extraction_exhausted_emits_stub(tmp_path) -> None:
    rd, spine = await _spine(tmp_path)
    seed = await spine.emit_event("agent.observed", agent_id="a1", payload={})
    res = await extract_handoff(
        narration="I forgot the marker entirely", policy=MarkerPolicy(max_retries=1),
        spine=spine, agent_id="a1", turn_id="t1", caused_by=seed, retry_fn=None,
    )
    await spine.finalize("completed")
    assert res.is_stub and "oaos-handoff-failure" in res.payload
    classes = {e["event_class"] for e in load_all_events(rd.root)}
    assert {"handoff_extraction_failed", "handoff_stub_injected", "intervention.recorded"} <= classes


# --------------------------------------------------------------------------- #
# diagnostic split (the answer-key side-channel closer)
# --------------------------------------------------------------------------- #


def test_diagnostic_split_whitelist_and_forbidden_substring() -> None:
    schema = PublicFeedbackSchema(
        allowed_fields=frozenset({"passed", "problem_count"}),
        forbidden_substrings=frozenset({"the answer is 42"}),
    )
    ev = SchemaEvaluator("schema:shape", FieldSchema(required=["answer"]))
    raw = ev.evaluate(payload={"answer": 1})
    rec = write_evaluation(raw=raw, public_schema=schema, outcome_id="o1", commitment_id="final")
    assert rec.agent_feedback.keys() <= {"passed", "problem_count"}
    assert "problems" in rec.researcher_diagnostics  # full detail kept researcher-side

    # A disallowed key in agent_feedback is rejected.
    raw.agent_feedback["leak"] = "x"
    with pytest.raises(EvaluationRejected):
        write_evaluation(raw=raw, public_schema=schema, outcome_id="o1", commitment_id="final")

    # A verbatim answer-key substring in a free-text field is rejected (normalized).
    raw2 = ev.evaluate(payload={"answer": 1})
    raw2.agent_feedback = {"passed": "The Answer  Is 42!"}
    schema2 = PublicFeedbackSchema(allowed_fields=frozenset({"passed"}),
                                   forbidden_substrings=frozenset({"the answer is 42"}))
    with pytest.raises(EvaluationRejected):
        write_evaluation(raw=raw2, public_schema=schema2, outcome_id="o1", commitment_id="final")


def test_handoff_contract_permits_topology() -> None:
    hc = HandoffContract(contract_id="h1", shape="one_to_one", senders=["writer"], recipients=["editor"])
    assert hc.permits("writer", "editor", "handoff")
    assert not hc.permits("editor", "writer", "handoff")


def test_evaluation_record_persists_determinism() -> None:
    schema = PublicFeedbackSchema(allowed_fields=frozenset({"passed", "problem_count"}))
    ev = SchemaEvaluator("schema:shape", FieldSchema(required=["answer"]))
    raw = ev.evaluate(payload={"answer": 1})
    raw.determinism = "stochastic(seeded)"
    rec = write_evaluation(raw=raw, public_schema=schema, outcome_id="o", commitment_id="c")
    assert rec.determinism == "stochastic(seeded)"  # signal survives onto the archived record


async def test_handoff_contract_enforced_on_delivery(tmp_path) -> None:
    """The HandoffContract is consulted at delivery (M6 §1): a topology-violating
    or under-specified handoff produces a protocol.violation and is NOT delivered;
    a permitted one emits a handoff event carrying the HandoffDelta slot."""
    from oaos2.communication.messages import MessageIntent
    from oaos2.kernel.runtime import _send_message, build_runtime, make_agent

    rd, spine = await _spine(tmp_path)

    async def _noop(agent, rs, ctx):
        from oaos2.kernel.runtime import ActionPlan
        return ActionPlan(result="retire")

    writer = make_agent("W", _noop, role_id="writer")
    editor = make_agent("E", _noop, role_id="editor")
    rs = build_runtime(spine, [writer, editor], scheduler="free")
    rs.handoff_contract = HandoffContract(
        contract_id="h", shape="one_to_one", senders=["writer"], recipients=["editor"],
        required_fields=frozenset({"summary"}),
    )
    # Permitted + complete: delivered, handoff event + HandoffDelta captured.
    await _send_message(MessageIntent(to_agent="E", kind="handoff", payload='{"summary": "x"}'),
                        writer, rs, caused_by=None)
    # Topology violation (editor -> writer not permitted): refused.
    await _send_message(MessageIntent(to_agent="W", kind="handoff", payload='{"summary": "x"}'),
                        editor, rs, caused_by=None)
    # Missing required field: refused.
    await _send_message(MessageIntent(to_agent="E", kind="handoff", payload="{}"),
                        writer, rs, caused_by=None)
    await spine.finalize("completed")

    events = load_all_events(rd.root)
    classes = [e["event_class"] for e in events]
    assert "handoff" in classes
    reasons = {e["payload"].get("reason") for e in events if e["event_class"] == "protocol.violation"}
    assert "handoff_not_in_topology" in reasons
    assert "handoff_missing_fields" in reasons
    # The permitted handoff carried a HandoffDelta boundary-loss slot.
    handoff = next(e for e in events if e["event_class"] == "handoff")
    assert "handoff_delta" in handoff["payload"]


# --------------------------------------------------------------------------- #
# Synthetic-registry gate: one contract per shape (incl. an auction), one
# outcome kind, one evaluator — runs end-to-end; registry diamond deterministic.
# --------------------------------------------------------------------------- #


async def test_synthetic_registry_gate(tmp_path) -> None:
    # One contract per shape + an auction (proves the shape resolves).
    contracts = [
        CoordinationContract(contract_id="c_1to1", shape=ContractShape.ONE_TO_ONE.value),
        CoordinationContract(contract_id="c_1tom", shape=ContractShape.ONE_TO_MANY.value),
        CoordinationContract(contract_id="c_mto1", shape=ContractShape.MANY_TO_ONE.value),
        AggregationContract(contract_id="c_auction", shape=ContractShape.MANY_TO_MANY.value,
                            aggregation_rule="auction", rounds=3),
    ]
    assert {c.shape for c in contracts} == {s.value for s in ContractShape}

    # One synthetic outcome kind + one schema evaluator, run end-to-end.
    rd, spine = await _spine(tmp_path)
    contract = OutcomeContract(
        outcome_id="syn",
        commitments=[Commitment(commitment_id="x", kind="synthetic_commit",
                                evaluators=["schema:shape"])],
        closure_condition=ClosureCondition(kind=ClosureKind.ALL_REQUIRED_COMMITTED.value),
    )
    coord = OutcomeCoordinator(contract, spine, rd.submitted)
    await coord.commit(commitment_id="x", payload={"field": "v"}, agent_id="a1", session_id="s1")
    report = await spine.finalize("completed")
    assert report.ok and coord.closed
    ev = SchemaEvaluator("schema:shape", FieldSchema(required=["field"]))
    assert ev.evaluate(payload={"field": "v"}).agent_feedback["passed"]


# --------------------------------------------------------------------------- #
# Zero-diff gate: a new task family registers new event class / comm kind /
# activity class / outcome+evaluator via inherits_from — NO core module changes.
# --------------------------------------------------------------------------- #


async def test_zero_diff_gate_new_vocab_via_registries(tmp_path) -> None:
    # A pack adds vocabulary purely by composing registries (inherits_from), never
    # by editing a core enum. Core registries are unchanged afterward.
    core_event_ids = EVENT_CLASS_SPEC.resolve().ids()
    core_kind_ids = COMM_KIND_SPEC.resolve().ids()
    core_activity_ids = ACTIVITY_CLASS_SPEC.resolve().ids()

    pack_events = RegistrySpec(
        "pack.events",
        entries={"culture.norm_codified": EVENT_CLASS_SPEC.resolve()["run.started"]},
        inherits_from=(EVENT_CLASS_SPEC,),
    ).resolve()
    pack_kinds = RegistrySpec(
        "pack.kinds", entries={"vote": "declaration"}, inherits_from=(COMM_KIND_SPEC,)
    ).resolve()
    pack_activity = RegistrySpec(
        "pack.activity", entries={"culture_ritual": "treatment"}, inherits_from=(ACTIVITY_CLASS_SPEC,)
    ).resolve()

    # The new vocabulary resolves and composes over the foundation...
    assert "culture.norm_codified" in pack_events and "run.started" in pack_events
    assert "vote" in pack_kinds and "message" in pack_kinds
    assert pack_activity["culture_ritual"] == "treatment"
    # ...and the CORE registries are untouched (zero diff to core).
    assert EVENT_CLASS_SPEC.resolve().ids() == core_event_ids
    assert COMM_KIND_SPEC.resolve().ids() == core_kind_ids
    assert ACTIVITY_CLASS_SPEC.resolve().ids() == core_activity_ids
