"""Stage 2-H: the model agent's deliberation volley — assembles one model call from its brief +
the transcript, sets `done` on assent, and assents on cost-cap so the group can close.
Tested with a fake gateway (no live model)."""
from __future__ import annotations

import pytest

import oaos2.agents.model_agent as ma
from oaos2.agents.model_agent import _deliberation_volley, _DELIBERATION_DONE_MARKER
from oaos2.models.types import BlockKind, NeutralBlock
from oaos2.pricing.ledger import CostCapWouldBreach

_VREQ = {"payload": {"conversation_id": "c1", "from": "B",
                     "transcript": [{"speaker": "B", "text": "transit must come first"}]}}
_KW = dict(system_prompt="You speak for commerce.", initial_user_text="(your brief)",
           model_ref="anthropic/claude-haiku-4-5", adapter=None, ledger=None, raw_store=None,
           spine=None, agent_id="commerce_rep", activity_class="work_modeling",
           exposure_contract=None, confirmatory=False, temperature=1.0, caused_by=None)


def _resp(text):
    class _R:
        content_blocks = [NeutralBlock(kind=BlockKind.TEXT.value, text=text)]
    return _R()


@pytest.mark.asyncio
async def test_volley_not_done_when_no_marker(monkeypatch):
    async def fake(**kw):
        # constant prefix (packet + instruction + MATERIALS) in the cached system slot;
        # only the transcript varies per volley (the deliberation cost mechanism)
        sys_text = kw["req"].messages[0].blocks[0].text
        assert "speak for commerce" in sys_text and "jointly deciding" in sys_text
        assert "(your brief)" in sys_text  # initial_user_text moved into the cacheable prefix
        assert kw["req"].cache.breakpoints == ["system", "transcript_tail"]
        msgs = kw["req"].messages
        # [system, header, one message PER transcript turn..., constant closing prompt] —
        # turn messages are byte-identical across volleys so the rolling transcript_tail
        # breakpoint prefix-matches the previous volley's cache entry.
        assert msgs[1].blocks[0].text == "# The discussion so far"
        assert msgs[2].blocks[0].text == "B: transit must come first"
        assert msgs[-1].blocks[0].text.startswith("# Your turn")
        return _resp("I hear you, but commerce access can't be sacrificed.")
    monkeypatch.setattr(ma, "call_model_gateway", fake)
    intent = await _deliberation_volley(_VREQ, **_KW)
    assert intent.conversation_id == "c1"
    assert not intent.done and "commerce access" in intent.text


@pytest.mark.asyncio
async def test_volley_transcript_is_append_only_across_volleys(monkeypatch):
    """The caching contract: volley N+1's messages must extend volley N's byte-for-byte
    (same prefix, new turns appended before the constant closing prompt) — otherwise the
    rolling transcript_tail breakpoint never gets a cache read."""
    seen = []

    async def fake(**kw):
        seen.append(kw["req"].messages)
        return _resp("noted")
    monkeypatch.setattr(ma, "call_model_gateway", fake)

    t1 = [{"speaker": "B", "text": "transit must come first"}]
    t2 = t1 + [{"speaker": "C", "text": "equity disagrees"}]
    await _deliberation_volley({"payload": {"conversation_id": "c1", "transcript": t1}}, **_KW)
    await _deliberation_volley({"payload": {"conversation_id": "c1", "transcript": t2}}, **_KW)
    m1, m2 = seen
    prefix1, prefix2 = m1[:-1], m2[: len(m1) - 1]  # everything before the closing prompt
    assert [ [b.text for b in m.blocks] for m in prefix1 ] == \
           [ [b.text for b in m.blocks] for m in prefix2 ]
    assert m2[-2].blocks[0].text == "C: equity disagrees"  # the new turn, at the breakpoint
    assert m1[-1].blocks[0].text == m2[-1].blocks[0].text  # constant closing prompt


@pytest.mark.asyncio
async def test_volley_opening_has_placeholder_turn(monkeypatch):
    async def fake(**kw):
        msgs = kw["req"].messages
        assert msgs[2].blocks[0].text == "(you are opening the discussion)"
        assert msgs[-1].blocks[0].text.startswith("# Your turn")
        return _resp("I'll open.")
    monkeypatch.setattr(ma, "call_model_gateway", fake)
    await _deliberation_volley({"payload": {"conversation_id": "c1", "transcript": []}}, **_KW)


@pytest.mark.asyncio
async def test_volley_done_when_marker_present(monkeypatch):
    async def fake(**kw):
        return _resp('Agreed. {"priority": ["transit","commerce","equity"]} ' + _DELIBERATION_DONE_MARKER)
    monkeypatch.setattr(ma, "call_model_gateway", fake)
    intent = await _deliberation_volley(_VREQ, **_KW)
    assert intent.done


@pytest.mark.asyncio
async def test_cost_cap_assents_so_group_can_close(monkeypatch):
    async def fake(**kw):
        raise CostCapWouldBreach(projected_usd=1.0, cap_usd=0.5, spent_usd=0.5)
    monkeypatch.setattr(ma, "call_model_gateway", fake)
    intent = await _deliberation_volley(_VREQ, **_KW)
    assert intent.done and _DELIBERATION_DONE_MARKER in intent.text
    assert intent.budget_forced  # forced assent, not agreement — recorded, not disguised


@pytest.mark.asyncio
async def test_free_assent_is_not_marked_budget_forced(monkeypatch):
    async def fake(**kw):
        return _resp('Agreed. {"priority": ["transit"]} ' + _DELIBERATION_DONE_MARKER)
    monkeypatch.setattr(ma, "call_model_gateway", fake)
    intent = await _deliberation_volley(_VREQ, **_KW)
    assert intent.done and not intent.budget_forced


@pytest.mark.asyncio
async def test_forced_assent_reaches_closure_record_and_interpretation(tmp_path):
    """The full recording chain: a budget-forced volley → conversation.volley/closed
    events carry budget_forced → the committed interpretation says consensus was not
    free — a cost-capped close must be distinguishable from genuine mutual_done."""
    from oaos2.communication.conversation import ConversationContract
    from oaos2.tasks.plugins.budget_allocation.coordination import (
        extract_interpretation as _extract_interpretation,
    )
    from oaos2.kernel.runtime import (
        ConversationVolleyIntent, _begin_conversation, _drive_conversation, build_runtime,
        make_agent,
    )
    from oaos2.kernel.run_dir import RunDir
    from oaos2.trace.invariants import load_all_events
    from oaos2.trace.spine import RunSpine

    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = RunSpine(rd.root, run_id="run1")
    await spine.start()

    async def noop(agent, rs, ctx):  # driven via the volley provider, not the loop
        from oaos2.kernel.runtime import ActionPlan
        return ActionPlan(result="retire")

    rs = build_runtime(spine, [make_agent("A", noop), make_agent("B", noop)], scheduler="free")
    seed = await spine.emit_event("turn.started", payload={})
    contract = ConversationContract(participants=("A", "B"), agent_closure="mutual_done",
                                    max_rounds=4)
    conv, opened = await _begin_conversation(rs, contract, "A", caused_by=seed)

    volleys = iter([
        ConversationVolleyIntent("c", 'I propose {"priority": ["transit"], "rationale": "r"} '
                                 + _DELIBERATION_DONE_MARKER, done=True),
        ConversationVolleyIntent("c", f"(budget reached) {_DELIBERATION_DONE_MARKER}",
                                 done=True, budget_forced=True),
    ])

    async def provider(rs_, conv_, floor, prev):
        from oaos2.kernel.runtime import _handle_conversation_volley
        intent = next(volleys)
        intent.conversation_id = conv_.conversation_id
        ev = await _handle_conversation_volley(intent, rs_.agents[floor], rs_, prev)
        return intent.text, intent.done, ev

    await _drive_conversation(rs, conv, "A", None, opened, provider)
    interp = _extract_interpretation(conv)
    assert interp["consensus"] and not interp["consensus_free"]
    assert interp["budget_forced"] == ["B"]
    await spine.finalize("completed")
    events = load_all_events(rd.root)
    closed = next(e for e in events if e["event_class"] == "conversation.closed")
    assert closed["payload"]["budget_forced"] == ["B"]
    forced_volleys = [e for e in events if e["event_class"] == "conversation.volley"
                      and e["payload"].get("budget_forced")]
    assert len(forced_volleys) == 1 and forced_volleys[0]["payload"]["speaker"] == "B"
