"""OpenAI adapter transport logic — translate/normalize, no network (M3 §2, M7 §10).

These exercise the pure translation seam (the only OpenAI-specific code); the live
HTTP path (`invoke`) is covered by the provider-parity gate when keys are present.
"""

from __future__ import annotations

from oaos2.models.adapters.base import RawProviderResponse
from oaos2.models.adapters.openai import OpenAIProviderAdapter
from oaos2.models.types import (
    BlockKind,
    ModelRequest,
    NeutralBlock,
    NeutralMessage,
    ReasoningRequest,
    ReasoningKind,
    SamplingParams,
    StopReason,
    ToolSpec,
)


def _req(messages, *, reasoning=None, tools=None, seed=None, model_ref="openai/gpt-5"):
    return ModelRequest(
        call_id="c1", model_ref=model_ref, messages=messages,
        tools=tools or [], sampling=SamplingParams(max_output_tokens=256, platform_seed=seed),
        reasoning=reasoning or ReasoningRequest(),
    )


def test_translate_aggregates_assistant_text_and_tool_calls() -> None:
    a = OpenAIProviderAdapter()
    msgs = [
        NeutralMessage("system", [NeutralBlock(kind=BlockKind.TEXT.value, text="be terse")]),
        NeutralMessage("user", [NeutralBlock(kind=BlockKind.TEXT.value, text="search please")]),
        NeutralMessage("assistant", [
            NeutralBlock(kind=BlockKind.TEXT.value, text="ok"),
            NeutralBlock(kind=BlockKind.TOOL_USE.value, tool_name="search",
                         tool_call_id="t1", arguments={"q": "x"}),
        ]),
        NeutralMessage("tool", [NeutralBlock(kind=BlockKind.TOOL_RESULT.value,
                                             tool_call_id="t1", text="42")]),
    ]
    tools = [ToolSpec(name="search", description="find", parameters_schema={})]
    payload = a.translate(_req(msgs, tools=tools))
    assert payload["model"] == "gpt-5" and "max_completion_tokens" in payload and "max_tokens" not in payload
    roles = [m["role"] for m in payload["messages"]]
    assert roles == ["system", "user", "assistant", "tool"]
    asst = payload["messages"][2]
    assert asst["content"] == "ok" and len(asst["tool_calls"]) == 1
    tc = asst["tool_calls"][0]
    assert tc["id"] == "t1" and tc["function"]["name"] == "search" and tc["function"]["arguments"] == '{"q": "x"}'
    assert payload["messages"][3] == {"role": "tool", "tool_call_id": "t1", "content": "42"}
    assert payload["tools"][0]["type"] == "function" and payload["tools"][0]["function"]["name"] == "search"


def test_translate_reasoning_drops_temperature_and_sets_effort() -> None:
    a = OpenAIProviderAdapter()
    msgs = [NeutralMessage("user", [NeutralBlock(kind=BlockKind.TEXT.value, text="hi")])]
    p = a.translate(_req(msgs, reasoning=ReasoningRequest(kind=ReasoningKind.THINKING.value, budget_tokens=1024)))
    assert p["reasoning_effort"] == "low" and "temperature" not in p
    p2 = a.translate(_req(msgs, reasoning=ReasoningRequest(kind=ReasoningKind.THINKING.value, budget_tokens=32000)))
    assert p2["reasoning_effort"] == "high"
    # No reasoning on a GPT-5 model (a memory recap): the least reasoning, no temperature, which
    # these models refuse (G5 model check, 2026-10-19: a refused recap removed a role)
    p3 = a.translate(_req(msgs))
    assert p3["reasoning_effort"] == "minimal" and "temperature" not in p3
    # No reasoning on a model that takes sampling: temperature passes through, no effort knob.
    p4 = a.translate(_req(msgs, model_ref="openrouter/qwen/qwen3.8-flash"))
    assert "reasoning_effort" not in p4 and "temperature" in p4


def test_translate_passes_seed_when_present() -> None:
    a = OpenAIProviderAdapter()
    msgs = [NeutralMessage("user", [NeutralBlock(kind=BlockKind.TEXT.value, text="hi")])]
    assert a.translate(_req(msgs, seed=7))["seed"] == 7
    assert "seed" not in a.translate(_req(msgs))


def test_normalize_blocks_and_stop_reason() -> None:
    a = OpenAIProviderAdapter()
    raw = RawProviderResponse(payload={
        "choices": [{
            "finish_reason": "tool_calls",
            "message": {"content": "thinking out loud",
                        "tool_calls": [{"id": "t9", "type": "function",
                                        "function": {"name": "search", "arguments": '{"q": "y"}'}}]},
        }],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20},
    })
    resp = a.normalize(raw, _req([]), raw_ref="sha256:abc")
    kinds = [b.kind for b in resp.content_blocks]
    assert BlockKind.TEXT.value in kinds and BlockKind.TOOL_USE.value in kinds
    tu = next(b for b in resp.content_blocks if b.kind == BlockKind.TOOL_USE.value)
    assert tu.tool_name == "search" and tu.arguments == {"q": "y"} and tu.tool_call_id == "t9"
    assert resp.stop_reason == StopReason.TOOL_USE.value
    assert resp.raw_provider_response_ref == "sha256:abc"


def test_normalize_subtracts_cached_tokens_to_avoid_double_billing() -> None:
    # OpenAI folds cached tokens into prompt_tokens; the ledger prices input at full +
    # cache_read at the cache rate, so net input must EXCLUDE the cached portion.
    a = OpenAIProviderAdapter()
    raw = RawProviderResponse(payload={
        "choices": [{"finish_reason": "stop", "message": {"content": "done"}}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 50,
                  "prompt_tokens_details": {"cached_tokens": 800},
                  "completion_tokens_details": {"reasoning_tokens": 30}},
    })
    u = a.normalize(raw, _req([]), raw_ref="r").usage
    assert u.input == 200 and u.cache_read == 800  # 1000 - 800 cached
    assert u.input_uncached_equiv == 1000 and u.cache_write is None
    assert u.output == 50 and u.reasoning == 30


def test_normalize_reasoning_summary_is_marked_not_raw_trace() -> None:
    a = OpenAIProviderAdapter(expose_thinking=True)
    raw = RawProviderResponse(payload={
        "choices": [{"finish_reason": "stop",
                     "message": {"content": "answer", "reasoning": "a brief summary"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    })
    resp = a.normalize(raw, _req([]), raw_ref="r")
    think = next(b for b in resp.content_blocks if b.kind == BlockKind.THINKING.value)
    assert think.provider_opaque["type"] == "reasoning_summary" and think.text == "a brief summary"


def test_estimate_tokens_never_undercounts() -> None:
    a = OpenAIProviderAdapter()
    msgs = [NeutralMessage("user", [NeutralBlock(kind=BlockKind.TEXT.value, text="x" * 300)])]
    # ~300 chars → comfortably above the real ~75-token count (upper bound, M3 §3.2).
    assert a.estimate_tokens(msgs, []) >= 100


def test_lcd_with_anthropic_excludes_raw_thinking_trace() -> None:
    # Provider parity runs at the lowest common exposure: OpenAI can't satisfy the raw
    # thinking trace (only summaries), so the LCD is just the reasoning-token count.
    from oaos2.models.adapters.anthropic import AnthropicProviderAdapter
    oa, an = OpenAIProviderAdapter(), AnthropicProviderAdapter()
    lcd = oa.satisfiable_exposures() & an.satisfiable_exposures()
    assert lcd == {"reasoning_tokens_to_agent"}
    assert "thinking_trace_to_agent" not in oa.satisfiable_exposures()


def test_tool_choice_is_sent_only_when_set_and_tools_are_offered() -> None:
    """G5 model check, 2026-10-19: GPT-5-mini ended most turns in prose; ``tool_choice`` "required"
    makes each call that offers tools call one. Unset, nothing is sent (the provider's auto)."""
    a = OpenAIProviderAdapter()
    msgs = [NeutralMessage("user", [NeutralBlock(kind=BlockKind.TEXT.value, text="hi")])]
    tools = [ToolSpec(name="wait", description="wait", parameters_schema={"type": "object", "properties": {}})]
    assert "tool_choice" not in a.translate(_req(msgs, tools=tools))
    a.tool_choice = "required"
    assert a.translate(_req(msgs, tools=tools))["tool_choice"] == "required"
    assert "tool_choice" not in a.translate(_req(msgs))        # a recap offers no tools
