"""Unit validation for the per-agent context-budget eviction (bounded info-processing capacity).

Proves the deterministic eviction policy: when the running context exceeds the budget, the
OLDEST tool-result TEXT is stub-replaced (reclaiming tokens) while the system prompt, the
initial handoff, the most recent turns, and every tool_use/tool_result PAIRING are preserved —
and that `budget=None`/under-budget is a no-op (back-compat).
"""
from __future__ import annotations

import oaos2.agents.model_agent as ma
from oaos2.agents.model_agent import (
    _evict_to_budget, _EVICTED_PREFIX, _compactable_cut, _apply_summary, _has_tool_use,
    _summarize_to_budget, _SUMMARY_PREFIX,
)
from oaos2.models.adapters.base import estimate_input_tokens_chars
from oaos2.models.types import BlockKind, NeutralBlock, NeutralMessage

import pytest


def _pairing_valid(msgs: list[NeutralMessage]) -> bool:
    """Every tool_use has a matching tool_result and vice versa (no orphan after surgery)."""
    use = {b.tool_call_id for m in msgs for b in m.blocks if b.kind == BlockKind.TOOL_USE.value}
    res = {b.tool_call_id for m in msgs for b in m.blocks if b.kind == BlockKind.TOOL_RESULT.value}
    return use == res


def _conversation(n_turns: int, old_size: int, recent_size: int) -> list[NeutralMessage]:
    """system + initial handoff + n_turns of (assistant tool_use, tool tool_result).
    Older tool-results are large (`old_size`), the last two small (`recent_size`)."""
    msgs = [
        NeutralMessage("system", [NeutralBlock(kind=BlockKind.TEXT.value, text="S" * 300)]),
        NeutralMessage("user", [NeutralBlock(kind=BlockKind.TEXT.value, text="initial handoff " * 50)]),
    ]
    for i in range(n_turns):
        size = recent_size if i >= n_turns - 2 else old_size
        msgs.append(NeutralMessage("assistant", [NeutralBlock(
            kind=BlockKind.TOOL_USE.value, tool_call_id=f"t{i}", tool_name="run_python",
            arguments={"code": "x=1"})]))
        msgs.append(NeutralMessage("tool", [NeutralBlock(
            kind=BlockKind.TOOL_RESULT.value, tool_call_id=f"t{i}", text="R" * size)]))
    return msgs


def test_evicts_oldest_until_under_budget():
    msgs = _conversation(n_turns=6, old_size=6000, recent_size=10)
    full = estimate_input_tokens_chars(msgs, [])
    budget = full // 2
    dropped = _evict_to_budget(msgs, budget, [])

    assert dropped, "expected some eviction when over budget"
    assert estimate_input_tokens_chars(msgs, []) <= budget
    # evicted blocks carry their token estimate + the tool_call_id (for the trace observable)
    assert all("tokens" in d and "tool_call_id" in d for d in dropped)


def test_preserves_system_initial_and_recent_turns():
    msgs = _conversation(n_turns=6, old_size=6000, recent_size=10)
    _evict_to_budget(msgs, estimate_input_tokens_chars(msgs, []) // 2, [])

    assert msgs[0].role == "system" and not msgs[0].blocks[0].text.startswith(_EVICTED_PREFIX)
    assert msgs[1].blocks[0].text.startswith("initial handoff")  # initial handoff intact
    # the last two messages (most recent turn) are never evicted
    for m in msgs[-2:]:
        for b in m.blocks:
            assert not (b.text or "").startswith(_EVICTED_PREFIX)
    # every tool_use still has a matching tool_result block (pairing preserved — stub, not delete)
    use_ids = {b.tool_call_id for m in msgs for b in m.blocks if b.kind == BlockKind.TOOL_USE.value}
    res_ids = {b.tool_call_id for m in msgs for b in m.blocks if b.kind == BlockKind.TOOL_RESULT.value}
    assert use_ids == res_ids


def test_evicts_oldest_first():
    msgs = _conversation(n_turns=6, old_size=6000, recent_size=10)
    # budget that forces evicting only some of the old results
    _evict_to_budget(msgs, int(estimate_input_tokens_chars(msgs, []) * 0.75), [])
    tool_results = [b for m in msgs if m.role == "tool" for b in m.blocks]
    evicted_flags = [b.text.startswith(_EVICTED_PREFIX) for b in tool_results]
    # once eviction stops, no earlier-than-an-intact block remains evicted after an intact one
    # i.e. evicted ones are a prefix of the tool-result sequence (oldest first)
    first_intact = evicted_flags.index(False) if False in evicted_flags else len(evicted_flags)
    assert all(evicted_flags[:first_intact]) and not any(evicted_flags[first_intact:])


def test_noop_when_unbounded_or_under_budget():
    msgs = _conversation(n_turns=3, old_size=200, recent_size=200)
    snapshot = [(m.role, [b.text for b in m.blocks]) for m in msgs]
    assert _evict_to_budget(msgs, None, []) == []          # unbounded
    assert _evict_to_budget(msgs, 10_000_000, []) == []    # comfortably under
    assert [(m.role, [b.text for b in m.blocks]) for m in msgs] == snapshot  # untouched


def test_deterministic():
    a = _conversation(n_turns=6, old_size=6000, recent_size=10)
    b = _conversation(n_turns=6, old_size=6000, recent_size=10)
    budget = estimate_input_tokens_chars(a, []) // 2
    da, db = _evict_to_budget(a, budget, []), _evict_to_budget(b, budget, [])
    assert da == db
    assert [bl.text for m in a for bl in m.blocks] == [bl.text for m in b for bl in m.blocks]


# ---- summarization compaction (the native compact-and-continue default) -------------------

def test_compactable_cut_never_splits_a_pair():
    msgs = _conversation(n_turns=6, old_size=6000, recent_size=10)
    cut = _compactable_cut(msgs, keep_recent=4)
    assert cut is not None and cut > 2
    # the kept tail must not begin with a dangling tool_result, and the last summarized
    # message must not be an assistant whose tool_result is kept
    assert msgs[cut].role != "tool"
    assert not _has_tool_use(msgs[cut - 1])


def test_apply_summary_preserves_structure_and_pairing():
    msgs = _conversation(n_turns=6, old_size=6000, recent_size=10)
    cut = _compactable_cut(msgs, keep_recent=4)
    n_before = len(msgs)
    stats = _apply_summary(msgs, cut, "RECAP of earlier work")

    assert msgs[0].role == "system" and msgs[1].blocks[0].text.startswith("initial handoff")
    assert msgs[2].role == "user" and msgs[2].blocks[0].text.startswith(_SUMMARY_PREFIX)
    assert _pairing_valid(msgs)                       # no orphaned tool_use/tool_result
    assert len(msgs) == n_before - (cut - 2) + 1      # span replaced by ONE recap message
    assert stats["policy"] == "summarize" and stats["messages_summarized"] == cut - 2


def test_compactable_cut_handles_interleaved_user_messages():
    # irregular structure (a stray user turn mid-stream) must still yield a pairing-safe cut
    msgs = _conversation(n_turns=5, old_size=4000, recent_size=10)
    msgs.insert(5, NeutralMessage("user", [NeutralBlock(kind=BlockKind.TEXT.value, text="clarification")]))
    cut = _compactable_cut(msgs, keep_recent=4)
    if cut is not None:
        _apply_summary(msgs, cut, "RECAP")
        assert _pairing_valid(msgs)


@pytest.mark.asyncio
async def test_summarize_to_budget_calls_gateway_and_splices(monkeypatch):
    msgs = _conversation(n_turns=6, old_size=6000, recent_size=10)

    class _Resp:
        content_blocks = [NeutralBlock(kind=BlockKind.TEXT.value, text="A concise recap.")]

    async def _fake_gateway(**kwargs):
        return _Resp()

    monkeypatch.setattr(ma, "call_model_gateway", _fake_gateway)
    budget = estimate_input_tokens_chars(msgs, []) // 2
    stats = await _summarize_to_budget(
        msgs, budget, [], adapter=None, model_ref="anthropic/claude-haiku-4-5",
        ledger=None, raw_store=None, spine=None, agent_id="solo", caused_by=None, confirmatory=False)

    assert stats and stats["policy"] == "summarize"
    assert any(b.text.startswith(_SUMMARY_PREFIX) for m in msgs for b in m.blocks)
    assert _pairing_valid(msgs)
    # under budget now (the big old span collapsed to one short recap)
    assert estimate_input_tokens_chars(msgs, []) <= budget


@pytest.mark.asyncio
async def test_summarize_noop_when_under_budget(monkeypatch):
    called = False

    async def _fake_gateway(**kwargs):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(ma, "call_model_gateway", _fake_gateway)
    msgs = _conversation(n_turns=2, old_size=100, recent_size=100)
    stats = await _summarize_to_budget(
        msgs, 10_000_000, [], adapter=None, model_ref="m", ledger=None, raw_store=None,
        spine=None, agent_id="a", caused_by=None, confirmatory=False)
    assert stats is None and not called  # under budget → no gateway call, no compaction


@pytest.mark.asyncio
async def test_summarize_uses_a_pack_declared_instruction_when_given(monkeypatch):
    seen = []

    class _Resp:
        content_blocks = [NeutralBlock(kind=BlockKind.TEXT.value, text="recap")]

    async def _fake_gateway(**kwargs):
        seen.append(kwargs["req"].messages[0].blocks[0].text)
        return _Resp()

    monkeypatch.setattr(ma, "call_model_gateway", _fake_gateway)
    for instruction, expected in ((None, ma._SUMMARIZE_SYSTEM), ("PACK PROMPT", "PACK PROMPT")):
        msgs = _conversation(n_turns=6, old_size=6000, recent_size=10)
        await _summarize_to_budget(
            msgs, estimate_input_tokens_chars(msgs, []) // 2, [], adapter=None, model_ref="m",
            ledger=None, raw_store=None, spine=None, agent_id="a", caused_by=None,
            confirmatory=False, instruction=instruction)
        assert seen[-1] == expected


@pytest.mark.asyncio
async def test_truncated_recap_is_marked_for_the_agent_and_in_the_stats(monkeypatch):
    """A recap the provider cut off at its ceiling is installed (the context must shrink)
    but never silently: the agent is told it is incomplete and the compaction stats say so.
    The ceiling is the caller's (pack-declared) value, 2,048 by default."""
    seen = []

    def _resp(stop):
        class _Resp:
            content_blocks = [NeutralBlock(kind=BlockKind.TEXT.value, text="| p_1 | [1,1")]
            stop_reason = stop
        return _Resp()

    for stop, max_tokens, expected_ceiling in (("max_tokens", None, 2048), ("end_turn", 4096, 4096)):
        async def _fake_gateway(**kwargs):
            seen.append(kwargs["req"].sampling.max_output_tokens)
            return _resp(stop)

        monkeypatch.setattr(ma, "call_model_gateway", _fake_gateway)
        msgs = _conversation(n_turns=6, old_size=6000, recent_size=10)
        stats = await _summarize_to_budget(
            msgs, estimate_input_tokens_chars(msgs, []) // 2, [], adapter=None, model_ref="m",
            ledger=None, raw_store=None, spine=None, agent_id="a", caused_by=None,
            confirmatory=False, max_tokens=max_tokens)
        recap = next(b.text for m in msgs for b in m.blocks if b.text and b.text.startswith(_SUMMARY_PREFIX))
        assert seen[-1] == expected_ceiling
        assert stats["summary_truncated"] is (stop == "max_tokens")
        assert ("cut off at its length limit" in recap) is (stop == "max_tokens")



@pytest.mark.asyncio
async def test_fabricated_recap_is_refused_once_and_a_second_failure_is_marked(monkeypatch):
    """The September 22, 2026 director control installed as the agent's memory a
    summarizer output that continued its work in the first person and wrote a tool call;
    the agent then treated the never-made registration as done. Such output is refused
    and the call retried with a reminder; if the retry is also not a recap, it is installed
    (the context must shrink) with a mark, and the stats say so."""
    bad = "I'll register a prototype to test c9=3.\n\n<tool_call>\n{\"name\": \"register_prototype\", \"arguments\": {}}\n</tool_call>"
    good = "(1) NOW: project A1; pending: the agent had decided to register [0,3,3,0,0,1,1,3,2,3,3,2] and had not done so."
    for outputs, expect_rejected in (([bad, good], False), ([bad, bad], True)):
        replies = list(outputs); prompts = []

        async def _fake_gateway(**kwargs):
            prompts.append(kwargs["req"].messages[0].blocks[0].text)

            class _Resp:
                content_blocks = [NeutralBlock(kind=BlockKind.TEXT.value, text=replies.pop(0))]
                stop_reason = "end_turn"
            return _Resp()

        monkeypatch.setattr(ma, "call_model_gateway", _fake_gateway)
        msgs = _conversation(n_turns=6, old_size=6000, recent_size=10)
        stats = await _summarize_to_budget(
            msgs, estimate_input_tokens_chars(msgs, []) // 2, [], adapter=None, model_ref="m",
            ledger=None, raw_store=None, spine=None, agent_id="a", caused_by=None, confirmatory=False)
        recap = next(b.text for m in msgs for b in m.blocks if b.text and b.text.startswith(_SUMMARY_PREFIX))
        assert len(prompts) == 2 and "was not a recap" in prompts[1] and "was not a recap" not in prompts[0]
        assert stats["summary_retried"] is True and stats["summary_rejected"] is expect_rejected
        assert ("<tool_call>" in recap) is expect_rejected
        assert ("failed a format check" in recap) is expect_rejected
        assert ("pending" in recap) is (not expect_rejected)
    assert not ma._looks_fabricated("(1) NOW: the agent was about to call `measure`; pending: measure p_1.")
    assert ma._looks_fabricated("Let me register the prototypes now.")
