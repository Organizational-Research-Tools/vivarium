"""Live conversation primitive (M5 §2.6): layered closure, floor regime, the
clarification reduction, and the three distinct non-answer dispositions.

Unit tests drive ``run_conversation`` with an injected volley provider (deterministic,
no full runtime); the integration test drives the whole primitive through the
concurrent supervisor with scripted behaviors."""

from __future__ import annotations

import asyncio

import pytest

from oaos2.communication.conversation import (
    ConversationContract,
    ConversationState,
    InvalidContract,
)
from oaos2.communication.messages import ChatRequest, ChatResponse
from oaos2.kernel.run_dir import RunDir
from oaos2.kernel.runtime import (
    ActionPlan,
    ConversationOpenIntent,
    ConversationVolleyIntent,
    RuntimeState,
    _handle_pause,
    _handle_response_to_pause,
    build_runtime,
    make_agent,
    run_conversation,
    run_supervisor,
)
from oaos2.trace.invariants import load_all_events
from oaos2.trace.spine import RunSpine


async def _spine(tmp_path, run="r") -> tuple[RunDir, RunSpine]:
    rd = RunDir.create(tmp_path, "e", "p", run)
    spine = RunSpine(rd.root, run_id=run)
    await spine.start()
    return rd, spine


def _classes(rd) -> list[str]:
    return [e["event_class"] for e in load_all_events(rd.root)]


def _scripted_provider(answers):
    """A volley provider that emits the next canned answer as a conversation.volley."""
    it = iter(answers)

    async def provider(rs, conv, floor, prev):
        text, done = next(it)
        ev = await rs.spine.emit_event(
            "conversation.volley", agent_id=floor, caused_by=prev,
            channel="informal", audience="agent",
            payload={"conversation_id": conv.conversation_id, "speaker": floor,
                     "round_index": conv.volleys, "text": text},
        )
        return text, done, ev

    return provider


# --- the clarification reduction (max_rounds=1) ---------------------------- #

async def test_clarification_reduction_closes_after_partner_answers(tmp_path) -> None:
    rd, spine = await _spine(tmp_path)
    rs = RuntimeState(run_id="r", spine=spine)
    seed = await spine.emit_event("turn.started", agent_id="A", turn_id="t")
    closed = await run_conversation(
        ConversationContract.clarification(("A", "B")), rs, "A", "what?", seed,
        volley_provider=_scripted_provider([("42", False)]),
    )
    await spine.finalize("completed")
    cls = _classes(rd)
    assert cls.count("conversation.opened") == 1 and cls.count("conversation.closed") == 1
    assert cls.count("conversation.volley") == 2  # opener question + partner answer
    closed_ev = next(e for e in load_all_events(rd.root) if e["event_id"] == closed)
    assert closed_ev["payload"]["reason"] == "max_rounds"
    assert closed_ev["payload"]["closure_layer"] == "hard_backstop"
    assert not rs.open_conversations  # state cleaned up


# --- Layer-2 agent-controlled close beats the hard backstop ---------------- #

async def test_agent_done_closes_before_max_rounds(tmp_path) -> None:
    rd, spine = await _spine(tmp_path)
    rs = RuntimeState(run_id="r", spine=spine)
    seed = await spine.emit_event("turn.started", agent_id="A", turn_id="t")
    # first_done + a generous round ceiling; the partner self-terminates with the marker.
    contract = ConversationContract(participants=("A", "B"), agent_closure="first_done", max_rounds=5)
    closed = await run_conversation(
        contract, rs, "A", "lets coordinate", seed,
        volley_provider=_scripted_provider([("done here <satisfied/>", True)]),
    )
    await spine.finalize("completed")
    closed_ev = next(e for e in load_all_events(rd.root) if e["event_id"] == closed)
    assert closed_ev["payload"]["closure_layer"] == "agent_done"  # not the round backstop


# --- n-party deliberation: floor rotates, closes on consensus (all assent) -- #

async def test_n_party_deliberation_closes_on_consensus(tmp_path) -> None:
    rd, spine = await _spine(tmp_path)
    rs = RuntimeState(run_id="r", spine=spine)
    seed = await spine.emit_event("turn.started", agent_id="A", turn_id="t")
    # 3 deliberators, mutual_done = consensus (every participant must assent at least once).
    contract = ConversationContract(participants=("A", "B", "C"),
                                    agent_closure="mutual_done", max_rounds=5)
    # opener A proposes (not done); the floor rotates B → C → A, each assenting.
    closed = await run_conversation(
        contract, rs, "A", "here is a proposal", seed,
        volley_provider=_scripted_provider([("B agrees <satisfied/>", True),
                                            ("C agrees <satisfied/>", True),
                                            ("A agrees <satisfied/>", True)]),
    )
    await spine.finalize("completed")
    events = load_all_events(rd.root)
    volleys = [e for e in events if e["event_class"] == "conversation.volley"]
    assert [v["payload"]["speaker"] for v in volleys] == ["A", "B", "C", "A"]  # rotation
    closed_ev = next(e for e in events if e["event_id"] == closed)
    assert closed_ev["payload"]["closure_layer"] == "agent_done"  # consensus, not the backstop
    assert not rs.open_conversations


async def test_n_party_no_consensus_hits_round_backstop(tmp_path) -> None:
    rd, spine = await _spine(tmp_path)
    rs = RuntimeState(run_id="r", spine=spine)
    seed = await spine.emit_event("turn.started", agent_id="A", turn_id="t")
    # No one assents; the chat must terminate on the finite round backstop (recorded, not silent).
    contract = ConversationContract(participants=("A", "B", "C"), agent_closure="mutual_done",
                                    max_rounds=1, rounds_warn_remaining=None)
    closed = await run_conversation(
        contract, rs, "A", "proposal", seed,
        volley_provider=_scripted_provider([("no", False), ("no", False), ("no", False)]),
    )
    await spine.finalize("completed")
    closed_ev = next(e for e in load_all_events(rd.root) if e["event_id"] == closed)
    assert closed_ev["payload"]["reason"] == "max_rounds"  # forced close = no consensus
    assert closed_ev["payload"]["closure_layer"] == "hard_backstop"


# --- Layer-1 soft regulator (warn, then continue) -------------------------- #

async def test_soft_wrapup_warning_fires_once_before_hard_backstop(tmp_path) -> None:
    rd, spine = await _spine(tmp_path)
    rs = RuntimeState(run_id="r", spine=spine)

    async def always_ok(rs, conv, floor, prev):
        ev = await rs.spine.emit_event("conversation.volley", agent_id=floor, caused_by=prev,
                                       channel="informal", audience="agent",
                                       payload={"conversation_id": conv.conversation_id,
                                                "speaker": floor, "text": "ok", "round_index": conv.volleys})
        return ("ok", False, ev)

    # max_rounds=4, warn at 2 remaining → one warning, then closes at the round backstop.
    contract = ConversationContract(participants=("A", "B"), max_rounds=4, rounds_warn_remaining=2)
    seed = await spine.emit_event("turn.started", agent_id="A", turn_id="t")
    closed = await run_conversation(contract, rs, "A", "hi", seed, volley_provider=always_ok)
    await spine.finalize("completed")
    cls = _classes(rd)
    assert cls.count("context.pressure_warning") == 1  # fired once (land-the-plane), not every volley
    closed_ev = next(e for e in load_all_events(rd.root) if e["event_id"] == closed)
    assert closed_ev["payload"]["reason"] == "max_rounds"  # soft warned, then hard-closed


# --- driver never parks forever: abandons + closes on a dead floor-holder --- #

async def test_driver_closes_on_abandoned_volley(tmp_path) -> None:
    from oaos2.kernel.runtime import _ConversationAbandoned
    rd, spine = await _spine(tmp_path)
    rs = RuntimeState(run_id="r", spine=spine)

    async def abandoning(rs, conv, floor, prev):
        raise _ConversationAbandoned("floor_holder_unavailable")

    seed = await spine.emit_event("turn.started", agent_id="A", turn_id="t")
    closed = await run_conversation(ConversationContract.clarification(("A", "B")), rs, "A",
                                    "hi?", seed, volley_provider=abandoning)
    await spine.finalize("completed")
    ev = next(e for e in load_all_events(rd.root) if e["event_id"] == closed)
    assert ev["payload"]["reason"] == "floor_holder_unavailable" and not rs.open_conversations


async def test_conversation_abandoned_when_floor_holder_retires(tmp_path) -> None:
    # The real mailbox path: the partner retires WITHOUT volleying → the driver detects
    # the dead floor-holder and closes the chat instead of hanging the run's TaskGroup.
    rd, spine = await _spine(tmp_path)

    def opener():
        async def b(agent, rs, ctx):
            if not agent.state.get("opened"):
                agent.state["opened"] = True
                return ActionPlan(conversation_open=ConversationOpenIntent(
                    partner="B", opening_payload="hi?",
                    contract=ConversationContract.clarification(("A", "B"))))
            return ActionPlan(result="retire")
        return b

    def partner():
        async def b(agent, rs, ctx):
            for o in ctx.observations:
                if o["kind"] == "conversation_volley_request":
                    return ActionPlan(result="retire")  # die mid-floor, never volley
            return ActionPlan(result="finish_turn")
        return b

    rs = build_runtime(spine, [make_agent("A", opener()), make_agent("B", partner())], scheduler="free")
    await asyncio.wait_for(run_supervisor(rs), timeout=10)
    report = await spine.finalize("completed")
    assert report.ok
    closed = [e for e in load_all_events(rd.root) if e["event_class"] == "conversation.closed"]
    assert closed and closed[0]["payload"]["reason"] == "floor_holder_unavailable"
    assert not rs.open_conversations


# --- the ≥1-finite-backstop invariant is enforced at open ------------------ #

def test_contract_with_no_finite_backstop_rejected() -> None:
    bad = ConversationContract(participants=("A", "B"), max_rounds=None, max_cost_usd=None,
                               stop_at_first_compaction=False)
    with pytest.raises(InvalidContract):
        bad.validate()


def test_contract_arity() -> None:
    # ≥2 participants is valid (n-party deliberation); <2 and duplicates are rejected at load.
    ConversationContract(participants=("A", "B", "C"), max_rounds=1).validate()  # n-party: OK
    ConversationContract(participants=("A", "B"), max_rounds=1).validate()       # bilateral: OK
    with pytest.raises(InvalidContract):
        ConversationContract(participants=("A",), max_rounds=1).validate()       # too few
    with pytest.raises(InvalidContract):
        ConversationContract(participants=("A", "A", "B"), max_rounds=1).validate()  # not distinct


def test_floor_rotates_through_n_participants() -> None:
    from oaos2.communication.conversation import ConversationState
    conv = ConversationState(conversation_id="c", floor_holder_id="A",
                             contract=ConversationContract(participants=("A", "B", "C"), max_rounds=3))
    assert conv.next_floor("A") == "B" and conv.next_floor("B") == "C" and conv.next_floor("C") == "A"
    assert conv.prev_floor("A") == "C" and conv.prev_floor("B") == "A"
    # bilateral back-compat: next == prev == "the other"
    bi = ConversationState(conversation_id="c2", floor_holder_id="A",
                           contract=ConversationContract(participants=("A", "B"), max_rounds=1))
    assert bi.next_floor("A") == "B" == bi.prev_floor("A") == bi.other("A")


# --- pause-inside-conversation invariant (floor_held) ---------------------- #

async def test_pause_inside_conversation_is_declined_floor_held(tmp_path) -> None:
    rd, spine = await _spine(tmp_path)
    rs = RuntimeState(run_id="r", spine=spine)
    agent = make_agent("A", behavior=None, role_id="r")
    rs.agents["A"] = agent
    # A is a participant in an open conversation → it may not open a cross-agent pause.
    conv = ConversationState(conversation_id="c1",
                             contract=ConversationContract.clarification(("A", "B")),
                             floor_holder_id="A")
    rs.open_conversations["c1"] = conv
    await _handle_pause(ChatRequest(to_agent="C", payload="?"), agent, rs, "A.t1", caused_by=None)
    await spine.finalize("completed")
    declined = [e for e in load_all_events(rd.root) if e["event_class"] == "chat.declined"]
    assert declined and declined[0]["payload"]["reason"] == "floor_held"
    assert not rs.paused_turns  # no pause was created


# --- chat.ignored is a third, distinct disposition ------------------------- #

async def test_ignore_emits_chat_ignored_and_leaves_pause_unresolved(tmp_path) -> None:
    rd, spine = await _spine(tmp_path)
    rs = RuntimeState(run_id="r", spine=spine)
    a, b = make_agent("A", None), make_agent("B", None)
    rs.agents.update({"A": a, "B": b})
    # Open a pause from A to B, then B "ignores" it.
    pause_task = asyncio.create_task(
        _handle_pause(ChatRequest(to_agent="B", payload="q", timeout_seconds=999), a, rs, "A.t1", caused_by=None)
    )
    await asyncio.sleep(0)  # let the pause register
    pt_id = next(iter(rs.paused_turns))
    await _handle_response_to_pause(ChatResponse(paused_turn_id=pt_id, ignore=True), b, rs, caused_by=None)
    assert rs.paused_turns[pt_id].resolution_kind is None  # still unresolved (would time out)
    # Resolve it so the awaiting task can finish (avoid a dangling coroutine).
    await _handle_response_to_pause(ChatResponse(paused_turn_id=pt_id, payload="ok"), b, rs, caused_by=None)
    await asyncio.wait_for(pause_task, timeout=2)
    await spine.finalize("completed")
    assert "chat.ignored" in _classes(rd)  # read after finalize (events flushed)


# --- full-runtime integration: open → volley → close, archive valid -------- #

async def test_conversation_through_supervisor(tmp_path) -> None:
    rd, spine = await _spine(tmp_path)

    def opener():
        async def b(agent, rs, ctx):
            if not agent.state.get("opened"):
                agent.state["opened"] = True
                return ActionPlan(conversation_open=ConversationOpenIntent(
                    partner="B", opening_payload="hello?",
                    contract=ConversationContract.clarification(("A", "B"))))
            return ActionPlan(result="retire")  # after the conversation, wind down
        return b

    def partner():
        async def b(agent, rs, ctx):
            for o in ctx.observations:
                if o["kind"] == "conversation_volley_request":
                    return ActionPlan(conversation_volley=ConversationVolleyIntent(
                        conversation_id=o["payload"]["conversation_id"], text="hi back"))
                if o["kind"] == "conversation_closed":
                    return ActionPlan(result="retire")
            return ActionPlan(result="finish_turn")  # idle until the floor reaches us
        return b

    rs = build_runtime(spine, [make_agent("A", opener()), make_agent("B", partner())], scheduler="free")
    await asyncio.wait_for(run_supervisor(rs), timeout=10)
    report = await spine.finalize("completed")
    assert report.ok, report.failures  # one coherent, causally-consistent archive

    cls = _classes(rd)
    assert cls.count("conversation.opened") == 1 and cls.count("conversation.closed") == 1
    assert cls.count("conversation.volley") == 2  # opener opening + partner reply
    assert not rs.open_conversations
