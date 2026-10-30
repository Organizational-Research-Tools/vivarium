"""Anthropic adapter, models set by an effort level (2026-10-03) — offline: Claude Sonnet
5.5 refuses thinking budgets, disabled thinking and non-default sampling, so its requests
take an explicit effort level and ``adaptive`` or ``between_tools`` reasoning. Every other
model keeps its request form byte for byte."""
from __future__ import annotations

import pytest

from oaos2.models.adapters.anthropic import AnthropicProviderAdapter
from oaos2.models.adapters.base import ProviderError
from oaos2.models.types import (
    BlockKind, CachePolicy, ModelRequest, NeutralBlock, NeutralMessage, ReasoningRequest, SamplingParams)
from oaos2.pricing.table import foundation_pricing_table, pricing_table_2026_10_03


def _req(model, kind="none", budget=None, temperature=1.0, top_p=None):
    return ModelRequest(
        call_id="01TEST", model_ref=f"anthropic/{model}",
        messages=[NeutralMessage("system", [NeutralBlock(kind=BlockKind.TEXT.value, text="sys")]),
                  NeutralMessage("user", [NeutralBlock(kind=BlockKind.TEXT.value, text="q")])],
        tools=[], sampling=SamplingParams(max_output_tokens=64, temperature=temperature, top_p=top_p),
        reasoning=ReasoningRequest(kind=kind, budget_tokens=budget), cache=CachePolicy(breakpoints=[]))


def test_earlier_models_keep_their_request_form():
    plain = AnthropicProviderAdapter().translate(_req("claude-sonnet-4-6"))
    assert plain == {"model": "claude-sonnet-4-6", "max_tokens": 64, "system": "sys",
                     "messages": [{"role": "user", "content": [{"type": "text", "text": "q"}]}],
                     "temperature": 1.0}
    thinking = AnthropicProviderAdapter(effort="low").translate(_req("claude-sonnet-4-6", "thinking", 8000))
    assert thinking["thinking"] == {"type": "enabled", "budget_tokens": 8000}
    assert "output_config" not in thinking


def test_sonnet_5_5_without_reasoning_is_between_tools_at_the_given_effort():
    p = AnthropicProviderAdapter(effort="medium").translate(_req("claude-sonnet-5-5"))
    assert p["thinking"] == {"type": "between_tools"}
    assert p["output_config"] == {"effort": "medium"}
    assert "temperature" not in p and "extra_headers" not in p


def test_sonnet_5_5_thinking_is_adaptive_and_summarized_only_when_exposed():
    hidden = AnthropicProviderAdapter(effort="low").translate(_req("claude-sonnet-5-5", "thinking"))
    assert hidden["thinking"] == {"type": "adaptive"} and hidden["output_config"] == {"effort": "low"}
    shown = AnthropicProviderAdapter(effort="xhigh", expose_thinking=True).translate(
        _req("claude-sonnet-5-5", "thinking"))
    assert shown["thinking"] == {"type": "adaptive", "display": "summarized"}


@pytest.mark.parametrize("adapter_kw, req_kw, says", [
    ({}, {}, "explicit effort"),
    ({"effort": "low"}, {"kind": "thinking", "budget": 8000}, "no thinking budget"),
    ({"effort": "max"}, {}, "needs reasoning"),
])
def test_sonnet_5_5_refuses_settings_it_cannot_honor(adapter_kw, req_kw, says):
    with pytest.raises(ProviderError, match=says):
        AnthropicProviderAdapter(**adapter_kw).translate(_req("claude-sonnet-5-5", **req_kw))


def test_sonnet_5_5_sends_no_sampling_it_cannot_honor():
    # the memory recap asks for temperature 0.0; the provider takes only its default
    p = AnthropicProviderAdapter(effort="low").translate(_req("claude-sonnet-5-5", temperature=0.0, top_p=0.9))
    assert "temperature" not in p and "top_p" not in p


def test_the_factory_passes_effort_through():
    a = AnthropicProviderAdapter.for_reasoning(reasoning_kind="thinking", effort="medium")
    assert a.effort == "medium" and a.expose_thinking
    from oaos2.models.adapters.openai import OpenAIProviderAdapter
    OpenAIProviderAdapter.for_reasoning(reasoning_kind="summary", effort="medium")   # accepted, unused


@pytest.mark.parametrize("model", ["claude-sonnet-5-5", "claude-haiku-5-5"])
def test_summary_reasoning_is_not_advertised_as_a_full_trace(model):
    from oaos2.models.adapters.base import RawProviderResponse
    from oaos2.models.exposure import ModelExposureContract, ExposureUnsatisfiable, resolve_exposure
    from oaos2.experiments.runner import _realized_reasoning_kind
    adapter = AnthropicProviderAdapter(effort="medium", expose_thinking=True)
    req = _req(model, "thinking")
    contract = ModelExposureContract(thinking_trace_to_agent=True)
    with pytest.raises(ExposureUnsatisfiable):
        resolve_exposure(contract, adapter, model_ref=req.model_ref)
    resolved = resolve_exposure(contract, adapter, model_ref=req.model_ref, confirmatory=False)
    assert resolved.confounded and not resolved.realized.thinking_trace_to_agent
    assert _realized_reasoning_kind(adapter, "thinking", req.model_ref) == "summary"
    raw = RawProviderResponse(payload={"content": [{"type": "thinking", "thinking": "summary", "signature": "sig"}],
                                      "stop_reason": "end_turn", "usage": {}})
    response = adapter.normalize(raw, req, "raw")
    assert response.realized_reasoning.kind == "summary"
    assert response.content_blocks[0].provider_opaque == raw.payload["content"][0]
    assert resolve_exposure(contract, adapter, model_ref="anthropic/claude-sonnet-4-6").realized.thinking_trace_to_agent


def test_effort_must_be_a_level():
    with pytest.raises(ValueError):
        AnthropicProviderAdapter(effort="extreme")


def test_the_newer_price_table_adds_sonnet_5_5_and_leaves_the_foundation_table_alone():
    base, newer = foundation_pricing_table(), pricing_table_2026_10_03()
    assert base.version == "2026-09-10" and "anthropic/claude-sonnet-5-5" not in base.rows
    row = newer.price("anthropic/claude-sonnet-5-5")
    assert (row.input, row.output, row.cache_read) == (2.0, 10.0, 0.2)
    assert all(newer.rows[k] == v for k, v in base.rows.items())
    assert newer.hash() != base.hash()


def test_haiku_5_5_is_priced_by_prompt_length_in_its_own_table():
    """October 10, 2026: Claude Haiku 5.5 enters a new table, priced by prompt length, with
    Sonnet 5.5's cache reads corrected; the earlier tables and their hashes do not move, and
    a model is priced by the oldest table that has it."""
    from oaos2.experiments.runner import _pricing_table_for
    from oaos2.models.types import ModelResponse, TokenSplit
    from oaos2.pricing.attribution import attribute_cost
    from oaos2.pricing.table import pricing_table_2026_10_10
    newer, t = pricing_table_2026_10_03(), pricing_table_2026_10_10()
    assert "anthropic/claude-haiku-5-5" not in newer.rows and t.price("anthropic/claude-sonnet-5-5").cache_read == 0.1
    assert newer.price("anthropic/claude-sonnet-5-5").cache_read == 0.2   # left as it was
    assert _pricing_table_for(["anthropic/claude-haiku-5-5"]).version == "2026-10-10"
    assert _pricing_table_for(["anthropic/claude-sonnet-5-5"]).version == "2026-10-03"
    assert _pricing_table_for(["anthropic/claude-sonnet-4-6"]).version == foundation_pricing_table().version

    def cost(inp, read, out):
        resp = ModelResponse(model_call_id="c", model_ref="anthropic/claude-haiku-5-5", stop_reason="end_turn",
                             usage=TokenSplit(input=inp, output=out, cache_read=read, cache_write=0))
        return attribute_cost(resp, t, "work_modeling").cost_usd
    assert cost(10_000, 90_000, 1_000) == pytest.approx((10_000 * 0.10 + 90_000 * 0.01 + 1_000 * 0.50) / 1e6)
    # one token more and the whole request is priced at the long-prompt rates
    assert cost(10_001, 90_000, 1_000) == pytest.approx((10_001 * 0.50 + 90_000 * 0.05 + 1_000 * 2.50) / 1e6)
    assert "claude-haiku-5-5" in __import__("oaos2.models.adapters.anthropic", fromlist=["x"]).EFFORT_MODELS


def test_the_2026_10_19_table_prices_the_inexpensive_models_and_moves_nothing_older():
    """October 19, 2026 (the G5 model check): GPT-5-mini and two OpenRouter models enter a new table;
    a model already priced keeps its table."""
    from oaos2.experiments.runner import _pricing_table_for
    from oaos2.pricing.table import pricing_table_2026_10_10, pricing_table_2026_10_19
    t = pricing_table_2026_10_19()
    for ref in ("openai/gpt-5-mini", "openrouter/qwen/qwen3.8-flash", "openrouter/deepseek/deepseek-v4-pro"):
        assert ref not in pricing_table_2026_10_10().rows and _pricing_table_for([ref]).version == "2026-10-19"
    assert t.price("openai/gpt-5-mini").output == 2.0
    assert _pricing_table_for(["anthropic/claude-haiku-5-5"]).version == "2026-10-10"
    assert t.price("anthropic/claude-haiku-5-5") == pricing_table_2026_10_10().price("anthropic/claude-haiku-5-5")


def test_haiku_5_5_takes_no_reasoning_as_disabled_and_sonnet_5_5_as_between_tools():
    """October 11, 2026: Haiku 5.5 refuses thinking.type between_tools (400), so every recap
    (which asks for no reasoning) failed; it accepts disabled. Sonnet 5.5 is unchanged."""
    from oaos2.models.types import ModelRequest, NeutralBlock, NeutralMessage, ReasoningRequest, SamplingParams
    def payload(model):
        req = ModelRequest(call_id="c", model_ref=f"anthropic/{model}",
                           messages=[NeutralMessage("user", [NeutralBlock(kind="text", text="hi")])],
                           sampling=SamplingParams(max_output_tokens=10), reasoning=ReasoningRequest(kind="none"))
        return AnthropicProviderAdapter(effort="medium").translate(req)
    assert payload("claude-haiku-5-5")["thinking"] == {"type": "disabled"}
    assert payload("claude-sonnet-5-5")["thinking"] == {"type": "between_tools"}
