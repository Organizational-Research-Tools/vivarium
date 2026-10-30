"""Anthropic adapter `translate` — offline (no SDK import, no key): the cache-breakpoint
markers place `cache_control` where M3 §3.1 pins them. Placement is cost-bearing apparatus
(differing placement changes hit rate → realized usd), so it is asserted offline rather
than only observed in live runs."""
from __future__ import annotations

from oaos2.models.adapters.anthropic import AnthropicProviderAdapter
from oaos2.models.types import (
    BlockKind,
    CachePolicy,
    ModelRequest,
    NeutralBlock,
    NeutralMessage,
    ReasoningRequest,
    SamplingParams,
    ToolSpec,
)


def _text(t: str) -> NeutralBlock:
    return NeutralBlock(kind=BlockKind.TEXT.value, text=t)


def _req(messages, breakpoints, tools=(), ttls=None):
    return ModelRequest(
        call_id="01TEST", model_ref="anthropic/claude-haiku-4-5", messages=messages,
        tools=list(tools), sampling=SamplingParams(max_output_tokens=64, temperature=1.0),
        reasoning=ReasoningRequest(kind="none"),
        cache=CachePolicy(breakpoints=list(breakpoints), ttl_overrides=dict(ttls or {})),
    )


def _cc(block: dict) -> bool:
    return block.get("cache_control") == {"type": "ephemeral"}


def test_system_and_tools_markers():
    msgs = [NeutralMessage("system", [_text("sys")]), NeutralMessage("user", [_text("q")])]
    tool = ToolSpec(name="t", description="d", parameters_schema={"properties": {}})
    payload = AnthropicProviderAdapter().translate(_req(msgs, ["system", "tools"], tools=[tool]))
    assert _cc(payload["system"][0])
    assert _cc(payload["tools"][-1])
    assert not any("cache_control" in b for b in payload["messages"][0]["content"])


def test_conversation_tail_marks_last_block_of_last_message():
    msgs = [NeutralMessage("user", [_text("a")]), NeutralMessage("assistant", [_text("b")]),
            NeutralMessage("user", [_text("c")])]
    payload = AnthropicProviderAdapter().translate(_req(msgs, ["conversation_tail"]))
    assert _cc(payload["messages"][-1]["content"][-1])
    assert not any("cache_control" in b for m in payload["messages"][:-1] for b in m["content"])


def test_transcript_tail_marks_penultimate_message_not_the_constant_suffix():
    # Deliberation shape: [header, turns..., constant closing prompt]. The breakpoint must
    # land on the newest TURN — caching through the constant suffix would never be re-read
    # (the next, longer transcript diverges from that prefix at the suffix position).
    msgs = [NeutralMessage("system", [_text("sys")]),
            NeutralMessage("user", [_text("# The discussion so far")]),
            NeutralMessage("user", [_text("B: transit first")]),
            NeutralMessage("user", [_text("C: equity disagrees")]),
            NeutralMessage("user", [_text("# Your turn")])]
    payload = AnthropicProviderAdapter().translate(_req(msgs, ["system", "transcript_tail"]))
    rendered = payload["messages"]  # system extracted → [header, turn, turn, closing]
    assert _cc(rendered[-2]["content"][-1])
    assert rendered[-2]["content"][-1]["text"] == "C: equity disagrees"
    assert not any("cache_control" in b for b in rendered[-1]["content"])


def test_transcript_tail_noop_on_single_message():
    msgs = [NeutralMessage("user", [_text("only")])]
    payload = AnthropicProviderAdapter().translate(_req(msgs, ["transcript_tail"]))
    assert not any("cache_control" in b for b in payload["messages"][0]["content"])


def test_ttl_override_renders_only_on_its_breakpoint():
    # 1h on the static prefix; the rolling tail keeps the provider default (5m) — the
    # provider requires longer-lived entries to precede shorter-lived ones.
    msgs = [NeutralMessage("system", [_text("sys")]),
            NeutralMessage("user", [_text("turn 1")]),
            NeutralMessage("user", [_text("# Your turn")])]
    payload = AnthropicProviderAdapter().translate(
        _req(msgs, ["system", "transcript_tail"], ttls={"system": "1h"}))
    assert payload["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert payload["messages"][-2]["content"][-1]["cache_control"] == {"type": "ephemeral"}


def test_fingerprint_covers_ttl_but_preserves_pre_ttl_values():
    plain = CachePolicy(breakpoints=["system", "tools"])
    explicit_empty = CachePolicy(breakpoints=["system", "tools"], ttl_overrides={})
    with_ttl = CachePolicy(breakpoints=["system", "tools"], ttl_overrides={"system": "1h"})
    # No overrides → the fingerprint archived manifests already pin (empty dict included).
    assert plain.fingerprint() == explicit_empty.fingerprint()
    # TTL is cost-bearing apparatus → it must move the fingerprint the confound gate reads.
    assert with_ttl.fingerprint() != plain.fingerprint()


def test_pinned_policies_put_long_ttls_on_static_prefix_only():
    # The provider rejects a 1h entry AFTER a 5m entry; both pinned policies must keep
    # overrides on static-prefix markers and leave the rolling tails at the default.
    from oaos2.agents.model_agent import DEFAULT_CACHE_POLICY, DELIBERATION_CACHE_POLICY

    for policy, tail in ((DEFAULT_CACHE_POLICY, "conversation_tail"),
                         (DELIBERATION_CACHE_POLICY, "transcript_tail")):
        assert tail in policy.breakpoints and tail not in policy.ttl_overrides
        # every override names a real breakpoint, and all overridden markers precede the tail
        tail_idx = policy.breakpoints.index(tail)
        for bp in policy.ttl_overrides:
            assert policy.breakpoints.index(bp) < tail_idx
    assert DEFAULT_CACHE_POLICY.ttl_overrides.get("system") == "1h"
    assert DELIBERATION_CACHE_POLICY.ttl_overrides.get("system") == "1h"
