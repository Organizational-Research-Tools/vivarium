"""Exercise runtime boundaries with real event recording and simulated model replies."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

import oaos2.agents.model_agent as model_agent
from oaos2.agents.tools import ToolContext
from oaos2.communication.messages import ChatRequest, MessageIntent
from oaos2.experiments.coordination.base import CoordinationContext
from oaos2.experiments.coordination.staged import StagedCollectiveProtocol
from oaos2.kernel.clock import ClockState
from oaos2.kernel.run_dir import RunDir
from oaos2.kernel.runtime import (
    ActionPlan, TurnContext, _agent_turn, _send_message, build_runtime,
    make_agent, run_supervisor,
)
from oaos2.models.types import ModelResponse, NeutralBlock
from oaos2.outcomes.commit import OutcomeCoordinator
from oaos2.outcomes.contracts import Commitment, OutcomeContract
from oaos2.outcomes.label import _ancestors, label_outcome_from_events
from oaos2.trace.invariants import load_all_events
from oaos2.trace.spine import RunSpine


@pytest.fixture
async def recorder(tmp_path):
    rd = RunDir.create(tmp_path, "audit", "task", "run")
    spine = RunSpine(rd.root, run_id="run")
    await spine.start()
    yield rd, spine
    report = await spine.finalize("completed")
    assert report.ok, report.failures


def _tool(name, number, **args):
    return NeutralBlock("tool_use", tool_name=name, tool_call_id=str(number), arguments=args)


def _gateway(monkeypatch, responses):
    """Simulate model replies while preserving admission charges and event links."""
    pending = iter(responses)
    calls = []

    async def invoke(**kwargs):
        req, spine = kwargs["req"], kwargs["spine"]
        invoked = await spine.emit_event(
            "model.invoked", caused_by=kwargs["caused_by"], model_call_id=req.call_id)
        kwargs["on_admitted"]()
        blocks = next(pending)
        calls.append(req)
        responded = await spine.emit_event(
            "model.responded", caused_by=invoked, model_call_id=req.call_id)
        return ModelResponse(req.call_id, req.model_ref, "tool_use", content_blocks=blocks,
                             response_event_id=responded)

    monkeypatch.setattr(model_agent, "call_model_gateway", invoke)
    return calls


def _model_runtime(rd, spine, *, contract=None, **kwargs):
    co = OutcomeCoordinator(
        contract or OutcomeContract("o", [Commitment("final", "artifact")]),
        spine, rd.submitted)
    rs = build_runtime(spine, [])
    tc = ToolContext("A", rs, None, None, rd, co, co.contract.commitments[0].commitment_id)
    behavior = model_agent.make_model_agent_behavior(
        adapter=None, model_ref="offline/test", system_prompt="A role", initial_user_text="A task",
        toolspecs=[], tool_context=tc, ledger=SimpleNamespace(spent_usd=.8, cap_usd=1),
        raw_store=None, confirmatory=False, **kwargs)
    a = make_agent("A", behavior)
    rs.agents = {"A": a}
    rs.admission = {"A": asyncio.Event()}
    co.on_close = rs.close_outcome
    return rs, a, tc, co


def _ancestry(events, event_id):
    return _ancestors([event_id], {e["event_id"]: e["caused_by_event_ids"] for e in events})


@pytest.mark.parametrize("limit", [1, 2])
async def test_deliberation_and_work_share_one_call_limit(recorder, monkeypatch, limit):
    rd, spine = recorder
    calls = _gateway(monkeypatch, [
        [NeutralBlock("text", text="Agreed. <satisfied/>")],
        [_tool("submit_results", 1, results={"answer": 1})],
    ])
    rs, agent, _, coordinator = _model_runtime(
        rd, spine, deliberation=True, max_model_calls=limit, budget_pressure_frac=2)
    seed = await spine.emit_event("turn.started", agent_id="A")
    volley = await agent.behavior(agent, rs, TurnContext("t1", 1, seed, [{
        "kind": "conversation_volley_request",
        "payload": {"conversation_id": "discussion", "transcript": []},
    }]))
    assert volley.conversation_volley.done
    assert volley.last_event_id
    plan = await agent.behavior(agent, rs, TurnContext("t2", 1, volley.last_event_id, []))
    assert len(calls) == limit
    assert agent.state["calls"] == limit
    assert bool(coordinator.committed) is (limit == 2)
    assert plan.result == "retire"


@pytest.mark.parametrize("actions_per_turn", [1, 64])
async def test_later_submission_retains_prior_action_intervention_and_results(
        recorder, monkeypatch, actions_per_turn):
    rd, spine = recorder
    _gateway(monkeypatch, [
        [_tool("read_file", 1, path="missing.txt")],
        [_tool("submit_results", 2, results={"answer": 1})],
    ])
    rs, _, _, co = _model_runtime(rd, spine)
    rs.max_actions_per_turn = actions_per_turn
    await asyncio.wait_for(run_supervisor(rs), 2)
    # Drain before examining durable records, without ending the shared fixture.
    await spine.queue.queue.join()
    events = load_all_events(rd.root)
    cid = co.committed_event_ids["final"]
    ancestry = _ancestry(events, cid)
    intervention = next(e for e in events if e["event_class"] == "intervention.recorded")
    first_result = next(e for e in events if e["event_class"] == "tool.result")
    responses = [e for e in events if e["event_class"] == "model.responded"]
    assert intervention["event_id"] in ancestry
    assert first_result["event_id"] in ancestry
    assert all(e["event_id"] in ancestry for e in responses)
    assert label_outcome_from_events(events, [cid]) == "assisted"


@pytest.mark.parametrize("kind", ["message", "handoff"])
async def test_delivery_links_sender_evidence_to_recipient_commit(recorder, kind):
    rd, spine = recorder
    co = OutcomeCoordinator(OutcomeContract("o", [Commitment("final", "artifact")]),
                            spine, rd.submitted)

    async def receive(agent, rs, ctx):
        assert ctx.observations[0]["payload"] == '{"answer": 42}'
        await co.commit(commitment_id="final", payload={"answer": 42}, agent_id="B",
                        session_id="s", caused_by=ctx.caused_by)
        return ActionPlan(result="retire")

    a, b = make_agent("A", None), make_agent("B", receive)
    rs = build_runtime(spine, [a, b])
    intervention = await spine.emit_event("intervention.recorded", payload={"class": "recorded"})
    await _send_message(MessageIntent("B", '{"answer": 42}', kind=kind), a, rs, intervention)
    await _agent_turn(b, rs)
    await spine.queue.queue.join()
    events = load_all_events(rd.root)
    observed = next(e for e in events if e["event_class"] == "agent.observed")
    transfer = next(e for e in events if e["event_class"] == ("handoff" if kind == "handoff" else "message.sent"))
    assert observed["payload"]["observations"][0]["source_event_id"] == transfer["event_id"]
    assert transfer["event_id"] in observed["caused_by_event_ids"]
    assert label_outcome_from_events(events, [co.committed_event_ids["final"]]) == "assisted"


@pytest.mark.parametrize("scheduler", ["sequential", "round_robin"])
async def test_serial_policy_stays_serial_after_a_message_kicks_scheduler(recorder, scheduler):
    _, spine = recorder
    statuses = []

    async def first(agent, rs, ctx):
        if ctx.action_index == 1:
            return ActionPlan(result="continue", messages=[MessageIntent("B", "ordinary work")])
        # Let the message-triggered scheduler pass run while this turn is active.
        await asyncio.sleep(.01)
        return ActionPlan(result="retire")

    async def second(agent, rs, ctx):
        statuses.append(rs.agents["A"].status)
        return ActionPlan(result="retire")

    rs = build_runtime(spine, [make_agent("A", first), make_agent("B", second)], scheduler=scheduler)
    await asyncio.wait_for(run_supervisor(rs), 2)
    assert statuses == ["retired"]


@pytest.mark.parametrize("scheduler", ["sequential", "round_robin"])
async def test_serial_admission_is_consumed_after_one_turn(recorder, scheduler):
    _, spine = recorder
    order = []

    async def behavior(agent, rs, ctx):
        order.append(agent.agent_id)
        return ActionPlan(result="retire" if agent.turn_count == 2 else "finish_turn")

    rs = build_runtime(spine, [make_agent("A", behavior), make_agent("B", behavior)], scheduler=scheduler)
    await asyncio.wait_for(run_supervisor(rs), 2)
    assert order == ["A", "B", "A", "B"]


async def test_outcome_closure_releases_paused_turn_without_waiting_for_timeout(recorder):
    rd, spine = recorder
    resumed_actions = []

    async def requester(agent, rs, ctx):
        resumed_actions.append(ctx.action_index)
        return ActionPlan(chat_request=ChatRequest("B", "question", timeout_seconds=600))

    async def closer(agent, rs, ctx):
        assert rs.paused_turns
        return ActionPlan(result="closed")

    rs = build_runtime(spine, [make_agent("A", requester), make_agent("B", closer)])
    await asyncio.wait_for(run_supervisor(rs), 2)
    assert rs.outcome_closed and not rs.paused_turns
    assert resumed_actions == [1]  # no fresh work after the closed pause resumes
    await spine.queue.queue.join()
    events = load_all_events(rd.root)
    assert not any(e["event_class"] == "chat.timed_out" for e in events)
    assert any(e["event_class"] == "chat.declined" and e["payload"]["reason"] == "run_closed"
               for e in events)


async def test_cancelling_supervisor_removes_paused_records(recorder):
    _, spine = recorder
    waiting = asyncio.Event()

    async def requester(agent, rs, ctx):
        return ActionPlan(chat_request=ChatRequest("B", "question", timeout_seconds=600))

    async def responder(agent, rs, ctx):
        waiting.set()
        await asyncio.Event().wait()

    rs = build_runtime(spine, [make_agent("A", requester), make_agent("B", responder)])
    task = asyncio.create_task(run_supervisor(rs))
    await asyncio.wait_for(waiting.wait(), 2)
    assert rs.paused_turns
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not rs.paused_turns


@pytest.mark.parametrize("second_ready", [False, True])
async def test_multiple_submissions_check_new_duty_and_preserve_each_transfer(
        recorder, monkeypatch, second_ready):
    rd, spine = recorder
    contract = OutcomeContract("o", [
        Commitment("s1", "artifact", committer_roles=["A"]),
        Commitment("s2", "artifact", committer_roles=["A"], blocks=["s1"]),
        Commitment("final", "artifact", committer_roles=["B"], blocks=["s2"]),
    ])
    co = OutcomeCoordinator(contract, spine, rd.submitted)
    rs = build_runtime(spine, [])
    rs.clock = ClockState(10, round_no=1)
    tc = ToolContext("A", rs, None, None, rd, co, "s1")
    readiness = lambda: second_ready or tc.submit_commitment_id == "s1"

    async def advance(cid, *_):
        if cid == "s1":
            tc.advance_submit_binding("s2")

    co.on_commit = advance
    roles = [SimpleNamespace(role_id="A"), SimpleNamespace(role_id="B")]
    org = SimpleNamespace(roles=roles, live_coordination={"contribution_visibility": "shared_sequential"})
    ctx = CoordinationContext(org, None, co, [], True, 0, None, spine)
    hooks = StagedCollectiveProtocol().role_hooks(ctx, 0, roles[0], "s1", tc)
    _gateway(monkeypatch, [[_tool("submit_results", 1, results={"value": 1}),
                           _tool("submit_results", 2, results={"value": 2})]])
    behavior = model_agent.make_model_agent_behavior(
        adapter=None, model_ref="offline/test", system_prompt="role", initial_user_text="task",
        toolspecs=[], tool_context=tc, ledger=SimpleNamespace(spent_usd=0, cap_usd=1),
        raw_store=None, confirmatory=False, readiness_gate=readiness,
        post_submit_messages=hooks.post_submit)
    agent = make_agent("A", behavior)
    rs.agents = {"A": agent}
    await _agent_turn(agent, rs)
    expected = ["s1", "s2"] if second_ready else ["s1"]
    assert list(co.committed) == expected
    results = agent.state["messages"][-1].blocks
    assert [b.tool_call_id for b in results] == ["1", "2"]
    if not second_ready:
        assert "not accepted" in results[1].text
    await spine.queue.queue.join()
    events = load_all_events(rd.root)
    handoffs = [e for e in events if e["event_class"] == "handoff"]
    assert [json.loads(e["payload"]["payload_text"])["commitment_id"] for e in handoffs] == expected
    for handoff, cid in zip(handoffs, expected):
        assert co.committed_event_ids[cid] in _ancestry(events, handoff["event_id"])
    if second_ready:
        assert co.committed_event_ids["s2"] not in _ancestry(events, handoffs[0]["event_id"])
    else:
        assert any(e["event_class"] == "tool.denied" and e["payload"]["reason"] == "submission_not_ready"
                   for e in events)


@pytest.mark.parametrize("advance_during", ["model_call", "tool_called_event"])
async def test_peer_binding_change_cannot_redirect_an_in_flight_submission(
        recorder, monkeypatch, advance_during):
    rd, spine = recorder
    contract = OutcomeContract("o", [
        Commitment("shared", "artifact", committer_roles=["A", "B"]),
        Commitment("next_case", "artifact", committer_roles=["A"], blocks=["shared"]),
    ])
    rs, agent, tc, co = _model_runtime(
        rd, spine, contract=contract, readiness_gate=lambda: True, budget_pressure_frac=2)
    rs.max_actions_per_turn = 1

    async def advance(cid, *_):
        if cid == "shared":
            tc.advance_submit_binding("next_case")

    co.on_commit = advance
    original_emit = spine.emit_event

    async def peer_commit():
        source = await original_emit("turn.started", agent_id="B")
        await co.commit(commitment_id="shared", payload={"answer": "peer"},
                        agent_id="B", session_id="B", caused_by=source)

    async def emit_with_peer_turn(event_class, **kwargs):
        event_id = await original_emit(event_class, **kwargs)
        if (advance_during == "tool_called_event" and event_class == "tool.called"
                and "shared" not in co.committed):
            await peer_commit()
        return event_id

    monkeypatch.setattr(spine, "emit_event", emit_with_peer_turn)

    async def invoke(**kwargs):
        req = kwargs["req"]
        invoked = await spine.emit_event("model.invoked", caused_by=kwargs["caused_by"])
        kwargs["on_admitted"]()
        if advance_during == "model_call":
            await peer_commit()
        responded = await spine.emit_event("model.responded", caused_by=invoked)
        return ModelResponse(
            req.call_id, req.model_ref, "tool_use", response_event_id=responded,
            content_blocks=[_tool("submit_results", 1, results={"answer": "for the old shared case"})])

    monkeypatch.setattr(model_agent, "call_model_gateway", invoke)
    await _agent_turn(agent, rs)
    assert tc.submit_commitment_id == "next_case"
    assert list(co.committed) == ["shared"]
    assert co.payloads["shared"] == {"answer": "peer"}
    results = agent.state["messages"][-1].blocks
    assert len(results) == 1 and results[0].tool_call_id == "1"
    assert "Submitted" not in results[0].text
    await spine.queue.queue.join()
    events = load_all_events(rd.root)
    assert any(e["event_class"] == "tool.denied"
               and e["payload"]["reason"] == "submission_binding_changed" for e in events)


async def test_peer_change_after_submit_does_not_count_as_own_binding_advance(recorder, monkeypatch):
    rd, spine = recorder
    contract = OutcomeContract("o", [
        Commitment("first", "artifact", committer_roles=["A"]),
        Commitment("shared", "artifact", committer_roles=["A", "B"], blocks=["first"]),
        Commitment("next_case", "artifact", committer_roles=["A"], blocks=["shared"]),
    ])
    rs, agent, tc, co = _model_runtime(
        rd, spine, contract=contract, readiness_gate=lambda: True, budget_pressure_frac=2)

    async def advance(cid, *_):
        if cid == "first":
            tc.advance_submit_binding("shared")
        elif cid == "shared":
            tc.advance_submit_binding("next_case")

    co.on_commit = advance
    original_emit = spine.emit_event

    async def emit_with_peer_turn(event_class, **kwargs):
        event_id = await original_emit(event_class, **kwargs)
        if (event_class == "tool.result" and kwargs.get("payload", {}).get("submitted")
                and "shared" not in co.committed):
            await co.commit(commitment_id="shared", payload={"answer": "peer"},
                            agent_id="B", session_id="B", caused_by=event_id)
        return event_id

    monkeypatch.setattr(spine, "emit_event", emit_with_peer_turn)
    _gateway(monkeypatch, [[
        _tool("submit_results", 1, results={"answer": "first"}),
        _tool("submit_results", 2, results={"answer": "for the shared case"}),
    ]])
    await _agent_turn(agent, rs)
    assert list(co.committed) == ["first", "shared"]
    assert tc.submit_commitment_id == "next_case"
    results = agent.state["messages"][-1].blocks
    assert [b.tool_call_id for b in results] == ["1", "2"]
    assert "Submitted" in results[0].text and "Submitted" not in results[1].text
    await spine.queue.queue.join()
    events = load_all_events(rd.root)
    assert any(e["event_class"] == "tool.denied"
               and e["payload"]["reason"] == "submission_binding_changed"
               and e["payload"]["expected_commitment_id"] == "shared" for e in events)
