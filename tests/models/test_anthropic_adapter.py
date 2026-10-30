"""Anthropic adapter conformance (M3 §2.2, §3.2) — live, gated on the API key.

Verifies the transport-only adapter (`messages.create`, never the SDK agent loop):
- `estimate_tokens` never under-counts the provider's reported input usage (the
  pre-dispatch cap's "no mid-thought kill" guarantee rests on this);
- a multi-turn tool round-trip works through the gateway (turn-2 tool_result
  re-serialization — where real dialect divergence lives).

Skipped automatically when no ANTHROPIC_API_KEY is available.
"""

from __future__ import annotations

import os

import pytest


def _has_key() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    try:
        import dotenv

        dotenv.load_dotenv()
    except Exception:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


pytestmark = pytest.mark.skipif(not _has_key(), reason="no ANTHROPIC_API_KEY")

MODEL = "anthropic/claude-sonnet-4-6"


def _adapter():
    from oaos2.models.adapters.anthropic import AnthropicProviderAdapter

    return AnthropicProviderAdapter()


async def _spine(tmp_path):
    from oaos2.trace.spine import RunSpine

    s = RunSpine(tmp_path, run_id="conf")
    await s.start()
    return s


async def test_estimate_never_undercounts_input(tmp_path) -> None:
    from oaos2.models.gateway import call_model_gateway
    from oaos2.models.raw_store import RawPayloadStore
    from oaos2.models.types import ModelRequest, NeutralBlock, NeutralMessage, SamplingParams
    from oaos2.pricing.ledger import CostLedger
    from oaos2.pricing.table import foundation_pricing_table
    from oaos2.ulid import new_ulid

    adapter = _adapter()
    spine = await _spine(tmp_path)
    ledger = CostLedger(pricing_table=foundation_pricing_table(), cap_usd=1.0)
    store = RawPayloadStore(tmp_path)
    messages = [NeutralMessage("user", [NeutralBlock(kind="text", text="Reply with the single word: ok")])]
    req = ModelRequest(call_id=new_ulid(), model_ref=MODEL, messages=messages,
                       sampling=SamplingParams(max_output_tokens=16))

    estimate = adapter.estimate_tokens(messages, [])
    resp = await call_model_gateway(req=req, adapter=adapter, ledger=ledger, spine=spine, raw_store=store)
    await spine.finalize("completed")
    assert estimate >= resp.usage.input, (estimate, resp.usage.input)
    assert resp.cost_usd > 0  # real spend recorded


async def test_multi_turn_tool_round_trip(tmp_path) -> None:
    from oaos2.models.gateway import call_model_gateway
    from oaos2.models.raw_store import RawPayloadStore
    from oaos2.models.types import (
        ModelRequest, NeutralBlock, NeutralMessage, SamplingParams, ToolSpec,
    )
    from oaos2.pricing.ledger import CostLedger
    from oaos2.pricing.table import foundation_pricing_table
    from oaos2.ulid import new_ulid

    adapter = _adapter()
    spine = await _spine(tmp_path)
    ledger = CostLedger(pricing_table=foundation_pricing_table(), cap_usd=1.0)
    store = RawPayloadStore(tmp_path)
    tool = ToolSpec(
        name="get_weather", description="Get the weather for a city.",
        parameters_schema={"type": "object", "properties": {"city": {"type": "string"}},
                           "required": ["city"]},
    )
    messages = [NeutralMessage("user", [NeutralBlock(kind="text", text="Use the get_weather tool for Paris, then tell me the temperature.")])]

    r1 = await call_model_gateway(
        req=ModelRequest(call_id=new_ulid(), model_ref=MODEL, messages=list(messages),
                         tools=[tool], sampling=SamplingParams(max_output_tokens=512)),
        adapter=adapter, ledger=ledger, spine=spine, raw_store=store,
    )
    tool_uses = [b for b in r1.content_blocks if b.kind == "tool_use"]
    assert r1.stop_reason == "tool_use" and tool_uses, r1.stop_reason
    tu = tool_uses[0]

    # Turn 2: echo the tool_result back (exercises tool_result re-serialization).
    messages.append(NeutralMessage("assistant", r1.content_blocks))
    messages.append(NeutralMessage("tool", [NeutralBlock(
        kind="tool_result", tool_call_id=tu.tool_call_id, text="18C and sunny")]))
    r2 = await call_model_gateway(
        req=ModelRequest(call_id=new_ulid(), model_ref=MODEL, messages=messages,
                         tools=[tool], sampling=SamplingParams(max_output_tokens=512)),
        adapter=adapter, ledger=ledger, spine=spine, raw_store=store,
    )
    await spine.finalize("completed")
    assert r2.stop_reason == "end_turn"
    text = "".join(b.text for b in r2.content_blocks if b.kind == "text")
    assert "18" in text  # the model used the tool result


async def test_extended_thinking_round_trip_with_tools(tmp_path) -> None:
    """Validates the UNTESTED-by-default thinking path: signed thinking blocks must
    survive normalization (provider_opaque) and ride back verbatim on turn 2 with a
    tool_result, or Anthropic rejects the request. Run before relying on
    reasoning_kind="thinking" in live runs."""
    from oaos2.models.gateway import call_model_gateway
    from oaos2.models.raw_store import RawPayloadStore
    from oaos2.models.types import (
        ModelRequest, NeutralBlock, NeutralMessage, ReasoningRequest, SamplingParams, ToolSpec,
    )
    from oaos2.models.adapters.anthropic import AnthropicProviderAdapter
    from oaos2.pricing.ledger import CostLedger
    from oaos2.pricing.table import foundation_pricing_table
    from oaos2.ulid import new_ulid

    adapter = AnthropicProviderAdapter(expose_thinking=True)
    spine = await _spine(tmp_path)
    ledger = CostLedger(pricing_table=foundation_pricing_table(), cap_usd=1.0)
    store = RawPayloadStore(tmp_path)
    tool = ToolSpec(name="get_weather", description="Get the weather for a city.",
                    parameters_schema={"type": "object", "properties": {"city": {"type": "string"}},
                                       "required": ["city"]})
    thinking = ReasoningRequest(kind="thinking", budget_tokens=2048)
    msgs = [NeutralMessage("user", [NeutralBlock(kind="text",
            text="Think about it, then use get_weather for Paris and report the temperature.")])]

    r1 = await call_model_gateway(
        req=ModelRequest(call_id=new_ulid(), model_ref=MODEL, messages=list(msgs), tools=[tool],
                         sampling=SamplingParams(max_output_tokens=3000, temperature=1.0), reasoning=thinking),
        adapter=adapter, ledger=ledger, spine=spine, raw_store=store, confirmatory=False,
    )
    # The thinking block was captured (content + signed provider_opaque for round-trip).
    thinking_blocks = [b for b in r1.content_blocks if b.kind == "thinking"]
    assert thinking_blocks and thinking_blocks[0].provider_opaque
    tu = next(b for b in r1.content_blocks if b.kind == "tool_use")

    # Turn 2 must echo the thinking block back verbatim, then the tool_result.
    msgs.append(NeutralMessage("assistant", r1.content_blocks))
    msgs.append(NeutralMessage("tool", [NeutralBlock(kind="tool_result", tool_call_id=tu.tool_call_id, text="18C")]))
    r2 = await call_model_gateway(
        req=ModelRequest(call_id=new_ulid(), model_ref=MODEL, messages=msgs, tools=[tool],
                         sampling=SamplingParams(max_output_tokens=3000, temperature=1.0), reasoning=thinking),
        adapter=adapter, ledger=ledger, spine=spine, raw_store=store, confirmatory=False,
    )
    await spine.finalize("completed")
    assert r2.stop_reason in ("end_turn", "tool_use")  # no 400 on the thinking round-trip
