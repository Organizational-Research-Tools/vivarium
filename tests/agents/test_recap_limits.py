"""Recap length enforced and recaps that cannot shrink the context (October 12, 2026). Offline."""

from __future__ import annotations

from oaos2.agents.model_agent import _SUMMARY_CUT_NOTE, _cut_recap
from oaos2.models.adapters.openai import OpenAIProviderAdapter
from oaos2.models.adapters.openai_compatible import OpencodeProviderAdapter, TogetherProviderAdapter
from oaos2.models.types import ModelRequest, NeutralBlock, NeutralMessage, ReasoningRequest, SamplingParams


def test_a_recap_within_the_limit_is_never_cut_and_a_longer_one_is_cut_at_a_paragraph():
    short = "NOW: one.\n\nCANDIDATES: two."
    assert _cut_recap(short, 16_000) == (short, 0) and _cut_recap(short, None) == (short, 0)
    long = "\n\n".join(f"Section {i}: " + "x" * 900 for i in range(30))  # about 27,500 characters
    cut, removed = _cut_recap(long, 16_000)
    assert len(cut) <= 16_000 and removed == len(long) - len(cut) and cut.endswith("x")
    assert cut == long[:len(cut)] and long[len(cut):].startswith("\n\nSection")  # at a paragraph boundary
    assert "length limit" in _SUMMARY_CUT_NOTE


def _req(model_ref):
    return ModelRequest(call_id="c", model_ref=model_ref,
                        messages=[NeutralMessage("user", [NeutralBlock(kind="text", text="recap")])],
                        sampling=SamplingParams(max_output_tokens=300, temperature=0.0),
                        reasoning=ReasoningRequest(kind="none"))


def test_open_weight_reasoning_models_get_low_reasoning_when_none_is_asked_and_others_nothing():
    t = TogetherProviderAdapter(api_key="k")
    assert t.translate(_req("together/zai-org/GLM-5.3-Flash"))["reasoning_effort"] == "low"
    assert t.translate(_req("together/deepseek-ai/DeepSeek-V4-Flash-0731"))["reasoning_effort"] == "low"
    assert "reasoning_effort" not in t.translate(_req("together/meta-llama/Llama-3.3-70B-Instruct-Turbo"))
    assert OpencodeProviderAdapter(api_key="k").translate(_req("opencode/glm-5.3-flash"))["reasoning_effort"] == "low"
    assert "reasoning_effort" not in OpenAIProviderAdapter(api_key="k").translate(_req("openai/gpt-4.1-mini"))


def test_openrouter_pins_hosts_from_the_model_reference_and_requires_tool_support():
    from oaos2.models.adapters.openai_compatible import OpenRouterProviderAdapter
    a = OpenRouterProviderAdapter(api_key="k")
    req = ModelRequest(call_id="c", model_ref="openrouter/deepseek/deepseek-v4-flash@deepinfra,fireworks",
                       messages=[NeutralMessage("user", [NeutralBlock(kind="text", text="hi")])],
                       sampling=SamplingParams(max_output_tokens=300, temperature=1.0, platform_seed=7),
                       reasoning=ReasoningRequest(kind="thinking", budget_tokens=1000))
    p = a.translate(req)
    assert p["model"] == "deepseek/deepseek-v4-flash" and "reasoning_effort" not in p
    assert "seed" not in p  # a seed would exclude hosts that do not take one (October 13, 2026)
    assert p["extra_body"] == {"provider": {"require_parameters": True, "only": ["deepinfra", "fireworks"],
                                            "allow_fallbacks": False}, "reasoning": {"effort": "low"}}
    recap = a.translate(_req("openrouter/z-ai/glm-5.3-flash"))
    assert recap["model"] == "z-ai/glm-5.3-flash" and recap["extra_body"] == {
        "provider": {"require_parameters": True}, "reasoning": {"effort": "low"}}
