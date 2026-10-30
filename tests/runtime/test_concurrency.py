"""M5 concurrent-runtime gates (DESIGN §22): concurrency, deadlock, cycle,
causality, cost-cap. Agent cognition is scripted via the behavior seam so the
engine mechanics are exercised deterministically."""

from __future__ import annotations

import asyncio

import pytest

from oaos2.communication.messages import ChatRequest, ChatResponse
from oaos2.kernel.run_dir import RunDir
from oaos2.kernel.runtime import ActionPlan, build_runtime, make_agent, run_supervisor
from oaos2.trace.invariants import load_all_events
from oaos2.trace.spine import RunSpine
from oaos2.workspace.acl import Zone
from oaos2.workspace.monitor import WorkspaceManager
from oaos2.workspace.zones import ZoneClass


async def _spine(tmp_path) -> tuple[RunDir, RunSpine]:
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = RunSpine(rd.root, run_id="run1")
    await spine.start()
    return rd, spine


def _classes(rd) -> list[str]:
    return [e["event_class"] for e in load_all_events(rd.root)]


# --------------------------------------------------------------------------- #
# Concurrency gate: 2+ agents in genuine parallel → one coherent archive.
# --------------------------------------------------------------------------- #


async def test_concurrency_gate_parallel_writes(tmp_path) -> None:
    rd, spine = await _spine(tmp_path)
    wm = WorkspaceManager(rd, spine)
    shared = Zone("shared", ZoneClass.AGENT_WRITABLE.value, is_shared=True)

    def behave(tag):
        async def b(agent, rs, ctx):
            from oaos2.kernel.runtime import WriteIntent

            return ActionPlan(
                writes=[
                    WriteIntent(rd.shared / "doc.txt", f"{tag}-shared".encode(), shared),
                    WriteIntent(rd.agent_scratch(agent.agent_id) / "p.txt", b"priv",
                                Zone(f"scratch_{tag}", ZoneClass.AGENT_WRITABLE.value)),
                ],
                result="retire",
            )

        return b

    rs = build_runtime(spine, [make_agent("A", behave("A")), make_agent("B", behave("B"))],
                       scheduler="free", workspace=wm)
    await asyncio.wait_for(run_supervisor(rs), timeout=10)
    report = await spine.finalize("completed")
    assert report.ok, report.failures  # one coherent, causally-consistent archive

    writes = [e for e in load_all_events(rd.root) if e["event_class"] in ("file.write", "file.edit")]
    assert len(writes) == 4  # 2 agents × (shared + private), all captured
    assert "file.write_contended" in _classes(rd)  # the same-file race is recorded


async def test_round_robin_selects_from_ready_agents(tmp_path) -> None:
    """A blocked role before a ready role in rotation must not wedge admission."""
    rd, spine = await _spine(tmp_path)
    acted: list[str] = []

    async def behave(agent, rs, ctx):
        acted.append(agent.agent_id)
        rs.close_outcome()
        return ActionPlan(result="retire")

    rs = build_runtime(
        spine, [make_agent("A", behave), make_agent("B", behave)],
        scheduler="round_robin",
    )
    rs.readiness["A"] = lambda: False
    rs.readiness["B"] = lambda: True
    await asyncio.wait_for(run_supervisor(rs), timeout=2)
    report = await spine.finalize("completed")
    assert report.ok, report.failures
    assert acted == ["B"]


# --------------------------------------------------------------------------- #
# Deadlock gate: a single pause resolves WITHOUT timeout under EVERY policy.
# --------------------------------------------------------------------------- #


async def _requester(agent, rs, ctx):
    if not agent.state.get("asked"):
        agent.state["asked"] = True
        return ActionPlan(
            chat_request=ChatRequest(to_agent="B", payload="what?", timeout_seconds=30),
            result="continue",
        )
    return ActionPlan(result="retire")  # resumed → done


async def _responder(agent, rs, ctx):
    for obs in ctx.observations:
        if obs["kind"] == "clarification_request":
            return ActionPlan(
                chat_responses=[ChatResponse(paused_turn_id=obs["payload"]["paused_turn_id"], payload="42")],
                result="retire",
            )
    return ActionPlan(result="finish_turn")  # nothing yet → loop


@pytest.mark.parametrize("policy", ["free", "sequential", "round_robin", "manager_dispatch"])
async def test_pause_resolves_under_every_policy(tmp_path, policy) -> None:
    rd, spine = await _spine(tmp_path)
    rs = build_runtime(spine, [make_agent("A", _requester), make_agent("B", _responder)],
                       scheduler=policy)
    if policy == "manager_dispatch":
        rs.manager_last_dispatch = ["A", "B"]  # a manager admits both
    await asyncio.wait_for(run_supervisor(rs), timeout=10)
    report = await spine.finalize("completed")
    assert report.ok, report.failures
    classes = _classes(rd)
    # The pause resolved by a real RESPONSE, not a timeout (the deadlock fix).
    assert "chat.response" in classes
    assert "agent.resumed" in classes
    assert "chat.timed_out" not in classes


async def _decliner(agent, rs, ctx):
    for obs in ctx.observations:
        if obs["kind"] == "clarification_request":
            # Refusal-as-authority: resolve the pause by declining, not answering.
            return ActionPlan(
                chat_responses=[ChatResponse(paused_turn_id=obs["payload"]["paused_turn_id"],
                                             decline=True, reason="refusal")],
                result="retire",
            )
    return ActionPlan(result="finish_turn")


async def test_refusal_as_authority_resolves_with_chat_declined(tmp_path) -> None:
    rd, spine = await _spine(tmp_path)
    rs = build_runtime(spine, [make_agent("A", _requester), make_agent("B", _decliner)],
                       scheduler="free")
    await asyncio.wait_for(run_supervisor(rs), timeout=10)
    report = await spine.finalize("completed")
    assert report.ok, report.failures
    classes = _classes(rd)
    # The pause resolved by a DECLINE (a distinct disposition), not a response or timeout.
    assert "chat.declined" in classes
    assert "agent.resumed" in classes
    assert "chat.response" not in classes
    assert "chat.timed_out" not in classes


async def test_nesting_depth_guard_fires_on_chained_pauses(tmp_path) -> None:
    """max_nesting_depth is enforced via the open-pause chain (the pausing agent is
    itself the target of an unresolved pause), not by counting '~' on a turn_id that
    never contains one — so a too-deep nested pause is declined."""
    import asyncio as _asyncio

    from oaos2.kernel.runtime import PausedTurnRecord, _handle_pause, make_agent

    rd, spine = await _spine(tmp_path)

    async def _noop(agent, rs, ctx):
        return ActionPlan(result="retire")

    a, b = make_agent("A", _noop), make_agent("B", _noop)
    rs = build_runtime(spine, [a, b], scheduler="free")
    rs.max_nesting_depth = 2
    # B is currently servicing an open pause at depth 2 (target == B).
    rs.paused_turns["x~B.1"] = PausedTurnRecord(
        paused_turn_id="x~B.1", parent_turn_id="x", pausing_agent_id="A",
        target_agent_id="B", request_payload="", resume_event=_asyncio.Event(),
        nesting_depth=2, deadline_seconds=rs.now() + 100,
    )
    # B now opens a pause → depth 3 > 2 → declined immediately (no await/block).
    await _handle_pause(ChatRequest(to_agent="C", payload="?"), b, rs, "B.t1", caused_by=None)
    await spine.finalize("completed")
    events = load_all_events(rd.root)
    decl = next(e for e in events if e["event_class"] == "chat.declined")
    assert decl["payload"]["reason"] == "nesting_depth_exceeded"
    assert decl["payload"]["depth"] == 3


async def test_paused_turn_ids_unique_across_pause_resume_cycles(tmp_path) -> None:
    """A monotonic counter mints paused_turn_id suffixes, so a second pause after the
    first resolved (and was popped) does not reuse '.1' and overwrite its index row."""
    async def requester_twice(agent, rs, ctx):
        if agent.state.get("asks", 0) >= 2:
            return ActionPlan(result="retire")
        agent.state["asks"] = agent.state.get("asks", 0) + 1
        return ActionPlan(
            chat_request=ChatRequest(to_agent="B", payload="q", timeout_seconds=5),
            result="continue",
        )

    async def responder_twice(agent, rs, ctx):
        for obs in ctx.observations:
            if obs["kind"] == "clarification_request":
                agent.state["n"] = agent.state.get("n", 0) + 1
                return ActionPlan(
                    chat_responses=[ChatResponse(paused_turn_id=obs["payload"]["paused_turn_id"], payload="ok")],
                    result=("retire" if agent.state["n"] >= 2 else "continue"),
                )
        return ActionPlan(result="finish_turn")

    rd, spine = await _spine(tmp_path)
    rs = build_runtime(spine, [make_agent("A", requester_twice), make_agent("B", responder_twice)],
                       scheduler="free")
    await asyncio.wait_for(run_supervisor(rs), timeout=10)
    report = await spine.finalize("completed")
    assert report.ok, report.failures
    ids = [e["payload"]["paused_turn_id"] for e in load_all_events(rd.root)
           if e["event_class"] == "chat.requested"]
    assert len(ids) == 2 and len(set(ids)) == 2, f"paused_turn_ids must be unique, got {ids}"


async def test_admission_directive_drives_manager_dispatch(tmp_path) -> None:
    """manager_dispatch admits whomever a manager-AGENT's admission_directive named,
    read from the trace — not an externally pre-set field (M5 §2.3)."""
    rd, spine = await _spine(tmp_path)

    async def manager(agent, rs, ctx):
        if not agent.state.get("dispatched"):
            agent.state["dispatched"] = True
            from oaos2.communication.messages import MessageIntent
            return ActionPlan(
                messages=[MessageIntent(to_agent=None, kind="admission_directive",
                                        payload="", extensions={"admit": ["W"]})],
                result="retire",
            )
        return ActionPlan(result="retire")

    async def worker(agent, rs, ctx):
        agent.state["ran"] = agent.state.get("ran", 0) + 1
        return ActionPlan(result="retire")

    mgr = make_agent("M", manager, role_id="manager")
    wkr = make_agent("W", worker, role_id="worker")
    rs = build_runtime(spine, [mgr, wkr], scheduler="manager_dispatch")
    rs.manager_last_dispatch = ["M"]  # bootstrap: admit the manager so it can dispatch
    await asyncio.wait_for(run_supervisor(rs), timeout=10)
    await spine.finalize("completed")
    # The worker ran because the manager's admission_directive admitted it.
    assert wkr.state.get("ran", 0) >= 1
    assert rs.manager_last_dispatch == ["W"]


# --------------------------------------------------------------------------- #
# Causality gate: seq(chat.requested) < seq(chat.response) < seq(agent.resumed).
# --------------------------------------------------------------------------- #


async def test_causality_pause_ordering(tmp_path) -> None:
    rd, spine = await _spine(tmp_path)
    rs = build_runtime(spine, [make_agent("A", _requester), make_agent("B", _responder)],
                       scheduler="free")
    await asyncio.wait_for(run_supervisor(rs), timeout=10)
    await spine.finalize("completed")
    events = load_all_events(rd.root)
    seq = {}
    for e in events:
        seq.setdefault(e["event_class"], e["sequence_number"])
    assert seq["chat.requested"] < seq["chat.response"] < seq["agent.resumed"]


# --------------------------------------------------------------------------- #
# Cycle gate: A→B→C→A bounded by timeout + nesting, no hang.
# --------------------------------------------------------------------------- #


async def test_request_cycle_bounded_by_timeout(tmp_path) -> None:
    rd, spine = await _spine(tmp_path)

    def ask(target):
        async def b(agent, rs, ctx):
            if not agent.state.get("asked"):
                agent.state["asked"] = True
                return ActionPlan(
                    chat_request=ChatRequest(to_agent=target, payload="?", timeout_seconds=0.2),
                    result="continue",
                )
            return ActionPlan(result="retire")

        return b

    # A waits on B, B waits on C, C waits on A → a genuine cycle; only timeouts break it.
    rs = build_runtime(
        spine,
        [make_agent("A", ask("B")), make_agent("B", ask("C")), make_agent("C", ask("A"))],
        scheduler="free",
    )
    await asyncio.wait_for(run_supervisor(rs), timeout=10)
    report = await spine.finalize("completed")
    assert report.ok, report.failures
    # The cycle did NOT hang — it unwound via timeouts (recorded interventions).
    assert "chat.timed_out" in _classes(rd)


# --------------------------------------------------------------------------- #
# Cost-cap gate: a turn whose projected cost exceeds the cap is refused
# pre-dispatch (never mid-call), surfaced as a cost_capped turn.
# --------------------------------------------------------------------------- #


async def test_cost_cap_refuses_pre_dispatch(tmp_path) -> None:
    from oaos2.models.adapters.stub import StubProviderAdapter
    from oaos2.models.gateway import call_model_gateway
    from oaos2.models.raw_store import RawPayloadStore
    from oaos2.models.types import ModelRequest, NeutralBlock, NeutralMessage, SamplingParams
    from oaos2.pricing.ledger import CostLedger
    from oaos2.pricing.table import foundation_pricing_table
    from oaos2.ulid import new_ulid

    rd, spine = await _spine(tmp_path)
    ledger = CostLedger(pricing_table=foundation_pricing_table(), cap_usd=1e-9)
    store = RawPayloadStore(rd.root)
    adapter = StubProviderAdapter()

    async def model_driven(agent, rs, ctx):
        # Calls the gateway; the pre-dispatch cap raises CostCapWouldBreach, which the
        # engine turns into a cost_capped turn (no mid-thought kill).
        req = ModelRequest(
            call_id=new_ulid(), model_ref="anthropic/claude-opus-4-8",
            messages=[NeutralMessage("user", [NeutralBlock(kind="text", text="hi")])],
            sampling=SamplingParams(max_output_tokens=4096),
        )
        await call_model_gateway(req=req, adapter=adapter, ledger=ledger, spine=spine,
                                 raw_store=store, agent_id=agent.agent_id)
        return ActionPlan(result="retire")

    rs = build_runtime(spine, [make_agent("A", model_driven)], scheduler="free")
    await asyncio.wait_for(run_supervisor(rs), timeout=10)
    await spine.finalize("completed")
    classes = _classes(rd)
    assert "cost.cap_blocked_dispatch" in classes
    assert "model.invoked" not in classes  # refused before dispatch
    # The turn was recorded as cost_capped.
    turn_completes = [
        e for e in load_all_events(rd.root) if e["event_class"] == "turn.completed"
    ]
    assert any(e["payload"].get("result") == "cost_capped" for e in turn_completes)
