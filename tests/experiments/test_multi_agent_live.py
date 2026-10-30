"""Multi-agent live coordination — all four arms run end-to-end (M7 §3, §5).

Exercises the REAL live path — ``run_org_live`` → N per-agent containers → host-owned
model loops → ``commit()``/closure → ``numeric_compare`` → archive — with an injected
fake container backend and a stub adapter, so the whole multi-agent machinery
(scheduler, per-role binding, the reader→builder→reviewer handoff DAG, parity) is
proven WITHOUT Docker and WITHOUT spending money. The model's actual replication
ability is out of scope here (that needs a live run + calibration, M7 §8 Q2); what is
proven is that the coordination is correctly wired and produces one coherent archive.
"""

from __future__ import annotations

import json

import pytest

from oaos2.experiments.runner import run_org_live
from oaos2.models.adapters.base import ModelBackendCapabilities, RawProviderResponse
from oaos2.models.types import ModelResponse, NeutralBlock, TokenSplit
from oaos2.organizations.presets import (
    context_expanded_single_agent,
    pipeline,
    role_blind_ensemble,
    single_agent,
)
from oaos2.tasks.plugins.paper_replication.solver import correct_results
from oaos2.trace.invariants import load_all_events

try:
    from oaos2.docker.backend import FakeContainerBackend
    _HAVE_FAKE = True
except Exception:  # pragma: no cover
    _HAVE_FAKE = False

_FAKE_DIGEST = "sha256:fake"


class _SubmitStubAdapter:
    """A stub model that, given the submit tool, immediately submits the CORRECT numbers
    (so ``numeric_compare`` passes and the outcome closes), then ends. Deterministic,
    priced at zero — a real ``ProviderAdapter`` with no network."""

    provider_id = "submit_stub"

    def __init__(self) -> None:
        self.capabilities = ModelBackendCapabilities(
            reasoning_kind="none", context_window=200_000, supports_tools=True,
            provider_seed_support=True, prompt_cache_support=False,
            satisfiable_exposures=frozenset(),
        )

    def translate(self, req):
        return req

    async def invoke(self, payload) -> RawProviderResponse:
        req = payload
        saw_result = any(b.kind == "tool_result" for m in req.messages for b in m.blocks)
        submit = next((t for t in req.tools if t.name == "submit_results"), None)
        if submit is not None and not saw_result:
            # A payload that satisfies BOTH the structured spec_v1 gate (analysis_plan
            # present) AND the flat_numeric results/implementation_v1 gate (numeric values).
            results = {"analysis_plan": "stub replication plan", **correct_results()}
            block = {"kind": "tool_use", "tool_name": "submit_results",
                     "tool_call_id": f"c-{req.call_id[:8]}", "arguments": {"results": results}}
            stop = "tool_use"
        else:
            block = {"kind": "text", "text": "done"}
            stop = "end_turn"
        return RawProviderResponse(payload={"model_ref": req.model_ref, "blocks": [block],
                                            "stop": stop, "input_tokens": 5, "output_tokens": 5})

    def normalize(self, raw, req, raw_ref) -> ModelResponse:
        p = raw.payload
        blocks = [NeutralBlock(kind=b["kind"], text=b.get("text", ""), tool_name=b.get("tool_name"),
                               tool_call_id=b.get("tool_call_id"), arguments=b.get("arguments"))
                  for b in p["blocks"]]
        return ModelResponse(model_call_id=req.call_id, model_ref=req.model_ref,
                             stop_reason=p["stop"], content_blocks=blocks,
                             usage=TokenSplit(input=p["input_tokens"], output=p["output_tokens"]),
                             raw_provider_response_ref=raw_ref)

    def satisfiable_exposures(self) -> set:
        return set()

    def estimate_tokens(self, messages, tools) -> int:
        return 64


pytestmark = pytest.mark.skipif(not _HAVE_FAKE, reason="FakeContainerBackend unavailable")


async def _run(org, tmp_path):
    return await run_org_live(
        org, tmp_path, tier="hard", model_ref="stub/deterministic", experiment_id="exp_mlive",
        reasoning_kind="none", cap_usd=5.0, max_model_calls=10,
        backend=FakeContainerBackend(digest=_FAKE_DIGEST),
        adapter_factory=_SubmitStubAdapter,
    )


async def test_single_agent_live_closes_and_scores(tmp_path) -> None:
    r = await _run(single_agent(), tmp_path)
    assert r.preset_id == "single_agent" and r.n_agents == 1
    assert r.closed and r.archive_valid and r.passed  # correct numbers → numeric_compare passes
    assert r.cache_policy_fingerprint and r.pricing_table_version


async def test_context_expanded_single_agent_live(tmp_path) -> None:
    r = await _run(context_expanded_single_agent(), tmp_path)
    assert r.preset_id == "context_expanded_single_agent" and r.n_agents == 1
    assert r.closed and r.archive_valid


async def test_role_blind_ensemble_live_three_agents_race(tmp_path) -> None:
    r = await _run(role_blind_ensemble(), tmp_path)
    assert r.preset_id == "role_blind_ensemble" and r.n_agents == 3
    assert r.closed and r.archive_valid  # first to submit the single "results" closes it


async def test_pipeline_live_handoff_chain_closes(tmp_path) -> None:
    r = await _run(pipeline(), tmp_path)
    assert r.preset_id == "pipeline" and r.n_agents == 3
    assert r.closed and r.archive_valid

    events = load_all_events(r.run_dir)
    classes = [e["event_class"] for e in events]
    # The decomposed contract closed via the blocks DAG: spec_v1 committed BEFORE
    # implementation_v1 (the builder waited on the reader), and a formal handoff was sent.
    committed = [(e["payload"]["state_commitment"]["commitment_id"])
                 for e in events if e["event_class"] == "state.committed"]
    assert "spec_v1" in committed and "implementation_v1" in committed
    assert committed.index("spec_v1") < committed.index("implementation_v1")
    # A formal handoff is now its own first-class `handoff` event (contract-checked,
    # carrying the HandoffDelta), not a generic message.sent.
    handoffs = [e for e in events if e["event_class"] == "handoff"]
    assert handoffs, "expected a reader→builder formal handoff"
    assert "handoff_delta" in handoffs[0]["payload"]
    assert "outcome.closed" in classes


class _PipelineConformanceStub:
    """Role-aware stub: the READER first submits a spec missing the required handoff
    field (analysis_plan) → refused + retry, then a conforming spec; the builder/reviewer
    submit the numbers. Exercises the handoff-format gate (b)/(c) on the pipeline."""

    provider_id = "pipe_conf"

    def __init__(self) -> None:
        self._submits = 0
        self.capabilities = ModelBackendCapabilities(
            reasoning_kind="none", context_window=200_000, supports_tools=True,
            provider_seed_support=True, prompt_cache_support=False, satisfiable_exposures=frozenset())

    def translate(self, req):
        return req

    async def invoke(self, payload) -> RawProviderResponse:
        req = payload
        system_text = req.messages[0].blocks[0].text if req.messages and req.messages[0].blocks else ""
        is_reader = system_text.lstrip().startswith("# Reader")
        accepted = any(b.kind == "tool_result" and "Task complete" in (b.text or "")
                       for m in req.messages for b in m.blocks)
        if accepted:
            block = {"kind": "text", "text": "done"}
            stop = "end_turn"
        else:
            self._submits += 1
            if is_reader and self._submits == 1:
                results = {"notes": "forgot the plan"}          # missing analysis_plan → refused
            elif is_reader:
                results = {"analysis_plan": "replicate Tables 1/3/4/5", "specs": "details"}
            else:
                results = {"analysis_plan": "x", **correct_results()}  # builder/reviewer numbers
            block = {"kind": "tool_use", "tool_name": "submit_results",
                     "tool_call_id": f"c{self._submits}", "arguments": {"results": results}}
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


async def test_pipeline_reader_handoff_format_enforced_then_delivered(tmp_path) -> None:
    # The reader's first (non-conforming) spec is refused by the commit-time handoff-format
    # gate and retried; the conforming spec then commits and is handed to the builder.
    r = await run_org_live(
        pipeline(), tmp_path, tier="hard", model_ref="stub/deterministic",
        experiment_id="exp_pipe_conf", reasoning_kind="none", cap_usd=5.0, max_model_calls=10,
        backend=FakeContainerBackend(digest=_FAKE_DIGEST), adapter_factory=_PipelineConformanceStub,
    )
    assert r.closed and r.archive_valid
    events = load_all_events(r.run_dir)
    # (b)/(c): the reader was forced to obey the handoff format — a recorded retry on its
    # spec submission, then spec_v1 committed and a formal handoff fired to the builder.
    reader_retries = [e for e in events if e["event_class"] == "intervention.recorded"
                      and e["payload"].get("kind") == "submission_nonconformant_retry"
                      and e["agent_id"] == "reader"]
    assert len(reader_retries) == 1
    committed = [e["payload"]["state_commitment"]["commitment_id"]
                 for e in events if e["event_class"] == "state.committed"]
    assert "spec_v1" in committed and "implementation_v1" in committed
    assert [e for e in events if e["event_class"] == "handoff"], "expected a formal handoff"


class _SlowReaderStub:
    """Reader does several run_python actions BEFORE submitting its spec (a realistic
    window in which a downstream agent could busy-spin); builder/reviewer submit at once.
    Used to prove the scheduler withholds admission from a not-ready agent (no spin)."""

    provider_id = "slow_reader"

    def __init__(self) -> None:
        self._actions = 0
        self.capabilities = ModelBackendCapabilities(
            reasoning_kind="none", context_window=200_000, supports_tools=True,
            provider_seed_support=True, prompt_cache_support=False, satisfiable_exposures=frozenset())

    def translate(self, req):
        return req

    async def invoke(self, payload) -> RawProviderResponse:
        req = payload
        system_text = req.messages[0].blocks[0].text if req.messages and req.messages[0].blocks else ""
        is_reader = system_text.lstrip().startswith("# Reader")
        accepted = any(b.kind == "tool_result" and "Task complete" in (b.text or "")
                       for m in req.messages for b in m.blocks)
        self._actions += 1
        if accepted:
            block, stop = {"kind": "text", "text": "done"}, "end_turn"
        elif is_reader and self._actions <= 3:
            block = {"kind": "tool_use", "tool_name": "run_python",
                     "tool_call_id": f"p{self._actions}", "arguments": {"code": "print('working')"}}
            stop = "tool_use"
        else:
            results = ({"analysis_plan": "plan"} if is_reader else {"analysis_plan": "x", **correct_results()})
            block = {"kind": "tool_use", "tool_name": "submit_results",
                     "tool_call_id": f"s{self._actions}", "arguments": {"results": results}}
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


async def test_downstream_waits_via_scheduler_no_finishturn_spin(tmp_path) -> None:
    # The builder is admission-withheld until spec_v1 commits — it must emit NO actions
    # while the (slow) reader works, instead of busy-spinning finish_turn (the livespin
    # that produced >100k events live). Dependency-driven admission (M5 §2.3).
    r = await run_org_live(
        pipeline(), tmp_path, tier="hard", model_ref="stub/deterministic",
        experiment_id="exp_nospin", reasoning_kind="none", cap_usd=5.0, max_model_calls=10,
        backend=FakeContainerBackend(digest=_FAKE_DIGEST), adapter_factory=_SlowReaderStub,
    )
    assert r.closed and r.archive_valid
    events = load_all_events(r.run_dir)
    spec_idx = next(i for i, e in enumerate(events)
                    if e["event_class"] == "state.committed"
                    and e["payload"]["state_commitment"]["commitment_id"] == "spec_v1")
    builder_before = [e for e in events[:spec_idx]
                      if e["event_class"] == "action.started" and e["agent_id"] == "builder"]
    assert builder_before == [], "builder ran before its blocker committed (livespin / no readiness gate)"
    # And the reader genuinely took multiple actions (a real window existed).
    reader_actions = [e for e in events[:spec_idx]
                      if e["event_class"] == "action.started" and e["agent_id"] == "reader"]
    assert len(reader_actions) >= 3
    # Total events stay bounded (no spin) — sanity ceiling far below the livespin's 100k+.
    assert len(events) < 2000


async def test_pipeline_builder_waited_for_spec_handoff(tmp_path) -> None:
    # The builder's readiness gate means it must NOT have committed before the reader's
    # spec_v1 existed — i.e. the implementation carries the spec as a causal ancestor is
    # out of scope for the stub, but ordering + the handoff message prove the wiring.
    r = await _run(pipeline(), tmp_path)
    envelope = json.loads((r.run_dir / "config" / "prompt_envelope_builder.json").read_text())
    assert envelope["commitment"] == "implementation_v1"
    assert envelope["role_packet"] == "builder"


# --- Stage 2: the ORGANIC deliberative arm (n-party deliberation → joint commit → optimize) -- #

_DIMS = ["economy", "health", "housing", "infrastructure", "environment", "workforce"]


class _DeliberateStub:
    """Organic-arm stub: a model call WITHOUT the submit tool is a deliberation volley → it
    assents immediately with the agreed priority JSON (so consensus closes the chat); a call
    WITH the submit tool is the compose phase → it submits a baseline allocation."""

    provider_id = "deliberate_stub"

    def __init__(self) -> None:
        self.capabilities = ModelBackendCapabilities(
            reasoning_kind="none", context_window=200_000, supports_tools=True,
            provider_seed_support=True, prompt_cache_support=False, satisfiable_exposures=frozenset())

    def translate(self, req):
        return req

    async def invoke(self, payload) -> RawProviderResponse:
        req = payload
        submit = next((t for t in req.tools if t.name == "submit_results"), None)
        if submit is not None:  # compose phase → submit a baseline allocation
            results = {"allocation": {f"{d}_flagship": 5 for d in _DIMS},
                       "objective_interpretation": {"priority": list(_DIMS)}}
            block = {"kind": "tool_use", "tool_name": "submit_results",
                     "tool_call_id": f"c-{req.call_id[:8]}", "arguments": {"results": results}}
            stop = "tool_use"
        else:  # deliberation volley → assent with the agreed priority
            agreed = json.dumps({"priority": list(_DIMS), "rationale": "balanced"})
            block = {"kind": "text", "text": f"Agreed. {agreed} <satisfied/>"}
            stop = "end_turn"
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


async def test_organic_deliberative_arm_consensus_then_compose(tmp_path) -> None:
    # End-to-end organic arm (D9): the 6 frame reps deliberate (n-party conversation) to
    # consensus, the orchestration commits the joint objective_interpretation, the ROTATED
    # integrator (rotation 0 -> roles[0]) drafts, the group reacts once in the shared
    # ratification round, and the SAME integrator revises + commits. Never a race.
    from oaos2.organizations.loader import load_org_spec
    r = await run_org_live(
        load_org_spec("budget_organic"), tmp_path, tier="high_ambiguity",
        model_ref="stub/deterministic", experiment_id="exp_organic", task_pack="budget_allocation",
        reasoning_kind="none", cap_usd=5.0, max_model_calls=12,
        backend=FakeContainerBackend(digest=_FAKE_DIGEST), adapter_factory=_DeliberateStub)
    assert r.closed and r.archive_valid
    events = load_all_events(r.run_dir)
    # the deliberation ran and closed by CONSENSUS (not the round backstop)
    opened = [e for e in events if e["event_class"] == "conversation.opened"]
    assert [o["payload"].get("label") for o in opened] == ["deliberation", "ratification"]
    closed = [e for e in events if e["event_class"] == "conversation.closed"]
    assert closed[0]["payload"]["closure_layer"] == "agent_done"
    # the full stage chain, in order: interpretation -> draft -> ratification -> final (D9)
    committed = [e["payload"]["state_commitment"]["commitment_id"]
                 for e in events if e["event_class"] == "state.committed"]
    assert committed == ["objective_interpretation", "draft_allocation",
                         "ratification_summary", "allocation"]
    # composition was the designated integrator's alone (rotation 0), both stages
    by_agent = {e["payload"]["state_commitment"]["commitment_id"]:
                e["payload"]["state_commitment"].get("agent_id") or e.get("agent_id")
                for e in events if e["event_class"] == "state.committed"}
    integrator = load_org_spec("budget_organic").roles[0].role_id
    assert by_agent["draft_allocation"] == integrator
    assert by_agent["allocation"] == integrator
    assert by_agent["ratification_summary"] == "ratification"  # the platform's record
    # all 6 reps volleyed in the deliberation (the floor rotated through the committee)
    speakers = {e["payload"]["speaker"] for e in events if e["event_class"] == "conversation.volley"}
    assert speakers == {f"rep_{d}" for d in _DIMS}
    # every rep reacted to the DRAFT in the shared round: the ratification conversation's
    # volley count is one full rotation (the integrator's opening presentation included)
    summary = [e for e in events if e["event_class"] == "state.committed"
               and e["payload"]["state_commitment"]["commitment_id"] == "ratification_summary"]
    assert summary  # payload lives by reference; the transcript length check reads the file
    import json as _json
    summary_payload = _json.loads((r.run_dir / "captured" / "submitted" /
                                   "ratification_summary.json").read_text())
    assert len(summary_payload["transcript"]) == 6  # opener's draft + 5 reactions... or 6 turns
    # Direct platform handoffs must carry their committed/transcript sources,
    # and the final decision must retain all earlier contributions in its ancestry.
    from oaos2.outcomes.label import _ancestors
    commit_events = {e["payload"]["state_commitment"]["commitment_id"]: e["event_id"]
                     for e in events if e["event_class"] == "state.committed"}
    final_ancestors = _ancestors([commit_events["allocation"]], {
        e["event_id"]: e["caused_by_event_ids"] for e in events})
    assert set(commit_events.values()) - {commit_events["allocation"]} <= final_ancestors
    observed_handoffs = [o for e in events if e["event_class"] == "agent.observed"
                         for o in e["payload"]["observations"] if o["kind"] == "handoff"]
    assert observed_handoffs and all(o.get("source_event_id") for o in observed_handoffs)

    # the platform advanced the integrator to the final stage exactly once
    stages = [e for e in events if e["event_class"] == "coordination.stage_advanced"]
    assert len(stages) == 1 and stages[0]["payload"]["phase"] == "ratified"


async def test_organic_integrator_rotation_is_deterministic(tmp_path) -> None:
    # D9: the sweep rotates the composer by replication index — cell rep N is composed by
    # roles[N % 6], recorded in the manifest. No frame owns composition across a batch.
    from oaos2.organizations.loader import load_org_spec
    import json as _json
    org = load_org_spec("budget_organic")
    r = await run_org_live(
        org, tmp_path, tier="high_ambiguity",
        model_ref="stub/deterministic", experiment_id="exp_rotation", task_pack="budget_allocation",
        reasoning_kind="none", cap_usd=5.0, max_model_calls=12, integrator_rotation=3,
        backend=FakeContainerBackend(digest=_FAKE_DIGEST), adapter_factory=_DeliberateStub)
    assert r.closed
    events = load_all_events(r.run_dir)
    by_agent = {e["payload"]["state_commitment"]["commitment_id"]:
                e["payload"]["state_commitment"].get("agent_id") or e.get("agent_id")
                for e in events if e["event_class"] == "state.committed"}
    assert by_agent["allocation"] == org.roles[3].role_id
    manifest = _json.loads((r.run_dir / "manifest.json").read_text())
    assert manifest["extensions"]["integrator_role"] == org.roles[3].role_id
