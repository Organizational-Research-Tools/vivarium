"""Deterministic stub adapter (DESIGN Tier-A "deterministic stub model").

The bootstrap / CI model: offline, deterministic, zero-cost (priced at 0 in the
foundation pricing table). It is a *real* ``ProviderAdapter` — it implements the
full contract — so the gateway, cost core, and (at M7) the parity machinery can
run end-to-end with no network and no credentials.

Its scripted behavior makes it a valid **multi-turn tool-calling** participant
(M3 §2.3): when a tool is available and no prior ``tool_result`` is present, it
emits a ``tool_use``; once it sees the tool result echoed back, it closes with
``end_turn``. That exercises the turn-2+ tool-result round-trip the parity gate
needs.

Token accounting is built so ``estimate_tokens`` (a local upper bound with
margin) **never under-counts** the input the adapter reports — the property the
pre-dispatch cap's "no mid-thought kill" guarantee rests on (M3 §3.2).
"""

from __future__ import annotations

import json
import math

from oaos2.models.adapters.base import (
    ModelBackendCapabilities,
    RawProviderResponse,
)
from oaos2.models.types import (
    ModelRequest,
    ModelResponse,
    NeutralBlock,
    NeutralMessage,
    TokenSplit,
    ToolSpec,
)

MODEL_REF = "stub/deterministic"
_MARGIN = 1.2  # estimate inflates the base count so it never under-projects
_MARGIN_FLOOR = 16


def _count(text: str) -> int:
    return math.ceil(len(text or "") / 4)


def _base_input_tokens(messages: list[NeutralMessage], tools: list[ToolSpec]) -> int:
    total = 0
    for m in messages:
        total += _count(m.role)
        for b in m.blocks:
            total += _count(b.text)
            if b.arguments:
                total += _count(json.dumps(b.arguments, sort_keys=True))
    for t in tools:
        total += _count(t.name) + _count(t.description)
        total += _count(json.dumps(t.parameters_schema, sort_keys=True))
    return total


class StubProviderAdapter:
    def __init__(
        self,
        satisfiable: frozenset[str] | None = None,
        *,
        provider_id: str = "stub",
        divergent: bool = False,
    ) -> None:
        # ``provider_id`` lets a second, behaviorally-identical adapter exist for the
        # provider-parity gate (M7). ``divergent`` makes an adapter that NEVER calls
        # the tool (always closes with text) — used to show parity *fails* when two
        # adapters diverge in loop behavior.
        self.provider_id = provider_id
        self.divergent = divergent
        self.capabilities = ModelBackendCapabilities(
            reasoning_kind="none",
            context_window=200_000,
            supports_tools=True,
            provider_seed_support=True,  # deterministic given identical inputs
            prompt_cache_support=False,
            satisfiable_exposures=satisfiable if satisfiable is not None else frozenset(),
        )

    # The stub doesn't have a separate dialect — translate is identity.
    def translate(self, req: ModelRequest):
        return req

    async def invoke(self, payload) -> RawProviderResponse:
        req: ModelRequest = payload
        saw_tool_result = any(
            b.kind == "tool_result" for m in req.messages for b in m.blocks
        )
        base_input = _base_input_tokens(req.messages, req.tools)
        if req.tools and not saw_tool_result and not self.divergent:
            # Turn 1 with a tool available: call it (deterministic args).
            block = {
                "kind": "tool_use",
                "tool_name": req.tools[0].name,
                "tool_call_id": f"stubcall-{req.call_id[:10]}",
                "arguments": {"query": "stub"},
            }
            stop = "tool_use"
            out_text = json.dumps(block["arguments"], sort_keys=True)
        else:
            block = {"kind": "text", "text": "STUB_DONE"}
            stop = "end_turn"
            out_text = "STUB_DONE"
        raw = {
            "model_ref": req.model_ref,
            "blocks": [block],
            "stop": stop,
            "input_tokens": base_input,  # exact; estimate (with margin) is >= this
            "output_tokens": _count(out_text),
        }
        return RawProviderResponse(payload=raw)

    def normalize(self, raw: RawProviderResponse, req: ModelRequest, raw_ref: str) -> ModelResponse:
        p = raw.payload
        blocks = [
            NeutralBlock(
                kind=b["kind"],
                text=b.get("text", ""),
                tool_name=b.get("tool_name"),
                tool_call_id=b.get("tool_call_id"),
                arguments=b.get("arguments"),
            )
            for b in p["blocks"]
        ]
        return ModelResponse(
            model_call_id=req.call_id,
            model_ref=req.model_ref,
            stop_reason=p["stop"],
            content_blocks=blocks,
            usage=TokenSplit(input=p["input_tokens"], output=p["output_tokens"]),
            raw_provider_response_ref=raw_ref,
        )

    def satisfiable_exposures(self) -> set[str]:
        return set(self.capabilities.satisfiable_exposures)

    def estimate_tokens(self, messages: list[NeutralMessage], tools: list[ToolSpec]) -> int:
        base = _base_input_tokens(messages, tools)
        return math.ceil(base * _MARGIN) + _MARGIN_FLOOR  # upper bound; never under-counts
