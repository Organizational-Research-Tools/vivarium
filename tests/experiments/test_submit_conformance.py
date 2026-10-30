"""Submit-time conformance gate + bounded retry (DESIGN §13 / M7 §2.1).

The submit tool validates the payload SHAPE declared on the commitment before commit():
a non-conforming submission is refused with structural (answer-key-safe) feedback, the
agent resubmits, retries are bounded, and exhaustion fails the cell with a recorded
treatment-defining event — never a silent drop or a low-score substitution. Exercised end-to-end with
a fake backend + stub adapter (no Docker, no spend).
"""

from __future__ import annotations

import pytest

from oaos2.experiments.runner import run_org_live
from oaos2.models.adapters.base import ModelBackendCapabilities, RawProviderResponse
from oaos2.models.types import ModelResponse, NeutralBlock, TokenSplit
from oaos2.organizations.presets import single_agent
from oaos2.outcomes.conformance import check_conformance
from oaos2.tasks.plugins.paper_replication.solver import correct_results
from oaos2.trace.invariants import load_all_events

try:
    from oaos2.docker.backend import FakeContainerBackend
    _HAVE_FAKE = True
except Exception:  # pragma: no cover
    _HAVE_FAKE = False


# --- unit: the structural check itself ------------------------------------- #

def test_conformance_accepts_flat_numeric() -> None:
    ok, problems = check_conformance({"a": 1, "b": 2.5, "c": "3.0"}, {"format": "flat_numeric", "min_results": 1})
    assert ok and not problems


def test_conformance_rejects_nested_and_empty() -> None:
    ok, problems = check_conformance({"table2": {"x": 1}}, {"format": "flat_numeric", "min_results": 1})
    assert not ok and any("FLAT" in p for p in problems)
    ok2, problems2 = check_conformance({"status": "done"}, {"format": "flat_numeric", "min_results": 1})
    assert not ok2 and any("numeric" in p for p in problems2)


def test_conformance_noop_when_unconfigured() -> None:
    ok, problems = check_conformance({"anything": "goes"}, {})
    assert ok and not problems


def test_conformance_feedback_has_no_answer_values() -> None:
    # Structural feedback must not echo answer-key numbers (it describes shape only).
    _, problems = check_conformance({"t2_cq_intervention_b": {"nested": 1}}, {"format": "flat_numeric"})
    joined = " ".join(problems)
    assert "0.228" not in joined and "-0.125" not in joined


# --- end-to-end: reject -> retry -> accept; and exhaustion ----------------- #

class _SubmitSequenceAdapter:
    """Stub model: submits the payloads in ``sequence`` on successive submit attempts,
    repeating the last once exhausted. Deterministic, zero-cost."""

    provider_id = "submit_seq"

    def __init__(self, sequence):
        self._seq = sequence
        self._i = 0
        self.capabilities = ModelBackendCapabilities(
            reasoning_kind="none", context_window=200_000, supports_tools=True,
            provider_seed_support=True, prompt_cache_support=False, satisfiable_exposures=frozenset())

    def translate(self, req):
        return req

    async def invoke(self, payload) -> RawProviderResponse:
        req = payload
        # End only once a submission has been ACCEPTED (tool_result says "Task complete").
        accepted = any(b.kind == "tool_result" and "Task complete" in (b.text or "")
                       for m in req.messages for b in m.blocks)
        if accepted:
            block = {"kind": "text", "text": "done"}
            stop = "end_turn"
        else:
            results = self._seq[min(self._i, len(self._seq) - 1)]
            self._i += 1
            block = {"kind": "tool_use", "tool_name": "submit_results",
                     "tool_call_id": f"c{self._i}", "arguments": {"results": results}}
            stop = "tool_use"
        return RawProviderResponse(payload={"model_ref": req.model_ref, "blocks": [block],
                                            "stop": stop, "input_tokens": 5, "output_tokens": 5})

    def normalize(self, raw, req, raw_ref) -> ModelResponse:
        p = raw.payload
        blocks = [NeutralBlock(kind=b["kind"], text=b.get("text", ""), tool_name=b.get("tool_name"),
                               tool_call_id=b.get("tool_call_id"), arguments=b.get("arguments")) for b in p["blocks"]]
        return ModelResponse(model_call_id=req.call_id, model_ref=req.model_ref, stop_reason=p["stop"],
                             content_blocks=blocks,
                             usage=TokenSplit(input=p["input_tokens"], output=p["output_tokens"]),
                             raw_provider_response_ref=raw_ref)

    def satisfiable_exposures(self):
        return set()

    def estimate_tokens(self, messages, tools):
        return 64


pytestmark = pytest.mark.skipif(not _HAVE_FAKE, reason="FakeContainerBackend unavailable")


async def _run(sequence, tmp_path, eid):
    return await run_org_live(
        single_agent(), tmp_path, tier="hard", model_ref="stub/deterministic", experiment_id=eid,
        reasoning_kind="none", cap_usd=5.0, max_model_calls=10,
        backend=FakeContainerBackend(digest="sha256:fake"),
        adapter_factory=lambda: _SubmitSequenceAdapter(sequence),
    )


async def test_malformed_then_conforming_retries_then_commits(tmp_path) -> None:
    # First a nested (non-flat) payload → refused + retry; then the correct flat numbers.
    r = await _run([{"table2": {"x": 1}}, correct_results()], tmp_path, "exp_retry")
    assert r.closed and r.archive_valid and r.passed
    events = load_all_events(r.run_dir)
    retries = [e for e in events if e["event_class"] == "intervention.recorded"
               and e["payload"].get("kind") == "submission_nonconformant_retry"]
    assert len(retries) == 1, "expected exactly one nonconformance retry"
    # The recorded intervention in the causal ancestry ⇒ the outcome is labelled assisted.
    assert r.label == "assisted"


async def test_slot_id_envelope_is_unwrapped_not_refused(tmp_path) -> None:
    # Calibration round 2 (2026-08-12): a model sometimes wraps the payload under its
    # own slot id — {"results": {"<commitment_id>": {...}}} — which used to fail
    # `required` with the misleading "missing field(s)" (the fields exist one level
    # deeper) and killed a live cell on retry exhaustion. The wrapper names the slot
    # explicitly, so the submit tool unwraps it: first-try accept, no intervention.
    r = await _run([{"results": correct_results()}], tmp_path, "exp_envelope")
    assert r.closed and r.archive_valid and r.passed
    events = load_all_events(r.run_dir)
    retries = [e for e in events if e["event_class"] == "intervention.recorded"
               and e["payload"].get("kind") == "submission_nonconformant_retry"]
    assert retries == [], "an envelope wrap must not burn a retry"
    assert r.label == "unassisted"


async def test_persistent_nonconformance_fails_the_cell(tmp_path) -> None:
    # Always malformed → bounded corrective retries, then a hard apparatus failure.
    # Treatment nonconformance must never be committed and scored as a bad outcome.
    from oaos2.outcomes.conformance import CommitmentConformanceError
    with pytest.raises(CommitmentConformanceError):
        await _run([{"status": "done"}], tmp_path, "exp_exhaust")
    run_dir = next((tmp_path / "exp_exhaust").rglob("trace/events.jsonl")).parents[1]
    events = load_all_events(run_dir)
    kinds = [e["payload"].get("kind") for e in events if e["event_class"] == "intervention.recorded"]
    assert kinds.count("submission_nonconformant_retry") == 2  # bounded at max_retries
    assert "submission_nonconformant_rejected" in kinds
    assert not [e for e in events if e["event_class"] == "state.committed"]
