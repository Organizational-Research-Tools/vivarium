"""Translate platform requests into individual Anthropic Messages calls.

Each invocation makes one request; agents/model_agent.py controls subsequent
calls and host-side tool execution. This module maps messages, reasoning
settings, tool requests, responses, and usage into the platform's shared types.
It loads credentials on the host. The anthropic SDK and python-dotenv are
optional dependencies supplied by the live extra."""

from __future__ import annotations

import os
from dataclasses import replace
from typing import Any

from oaos2.models.adapters.base import (
    FAILED,
    LOST,
    NOT_PROCESSED,
    NOT_SENT,
    RATE_LIMITED,
    REJECTED,
    TRANSIENT_STATUSES,
    UNCERTAIN,
    UNCERTAIN_WAITS,
    ModelBackendCapabilities,
    ProviderError,
    RawProviderResponse,
    estimate_input_tokens_chars,
    invoke_under_policy,
    is_malformed_response,
)
from oaos2.models.types import (
    BlockKind,
    ModelRequest,
    ModelResponse,
    NeutralBlock,
    NeutralMessage,
    RealizedReasoning,
    ReasoningKind,
    StopReason,
    TokenSplit,
    ToolSpec,
)

_STOP_MAP = {
    "end_turn": StopReason.END_TURN.value,
    "tool_use": StopReason.TOOL_USE.value,
    "max_tokens": StopReason.MAX_TOKENS.value,
    "stop_sequence": StopReason.STOP_SEQUENCE.value,
    "refusal": StopReason.REFUSAL.value,
    "pause_turn": StopReason.END_TURN.value,
}


# Models whose reasoning is set by an effort level, not a token budget (added 2026-10-03).
# On these a thinking budget, disabled thinking and non-default sampling are refused by the
# provider; reasoning is adaptive or, at the lowest setting, ``between_tools`` (no extended
# thinking). The effort level is a study setting and must be given explicitly. Sampling is
# fixed at the provider's default: a requested temperature or top_p (the memory recap asks
# for 0.0) is not sent. The archive keeps the platform's request, which still shows what was
# asked for, so a run on these models must record that its sampling was the provider's
# default. Every other model keeps the request form it had.
EFFORT_MODELS = frozenset({"claude-sonnet-5-5", "claude-haiku-5-5"})
# How each effort model takes "no reasoning" (memory recaps ask for none). Sonnet 5.5's lowest
# setting is ``between_tools``; Claude Haiku 5.5 refuses that type (400) and accepts
# ``disabled`` (Models API capabilities, checked October 11, 2026). Before this table every
# recap on Haiku 5.5 failed, which ended the G4 strain pilot of that day.
NO_REASONING_TYPE = {"claude-sonnet-5-5": "between_tools", "claude-haiku-5-5": "disabled"}
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


def _load_api_key() -> str:
    """Read ANTHROPIC_API_KEY host-side: the environment, else the repository's own .env. Never to a container."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        try:
            import dotenv  # optional
            from pathlib import Path

            key = dotenv.dotenv_values(Path(__file__).resolve().parents[3] / ".env").get("ANTHROPIC_API_KEY")
        except Exception:  # pragma: no cover
            pass
    if not key:
        raise ProviderError("ANTHROPIC_API_KEY not set (host-side .env or env var)")
    return key


REQUEST_TIMEOUT_S = 180.0  # seconds; far above any normal call, far below the SDK's 600 s default

class AnthropicProviderAdapter:
    provider_id = "anthropic"

    # Anthropic beta that makes the model emit a thinking block on EACH turn during a
    # tool loop (not just the first) — so per-turn reasoning is captured, not 2/N turns.
    _INTERLEAVED_THINKING_BETA = "interleaved-thinking-2025-05-14"

    def __init__(self, *, api_key: str | None = None, expose_thinking: bool = False,
                 interleaved_thinking: bool = True, effort: str | None = None) -> None:
        if effort is not None and effort not in EFFORT_LEVELS:
            raise ValueError(f"effort must be one of {EFFORT_LEVELS}, not {effort!r}")
        self._api_key = api_key
        self._client = None  # lazy
        self.expose_thinking = expose_thinking
        self.interleaved_thinking = interleaved_thinking
        self.effort = effort  # used only by EFFORT_MODELS
        self.capabilities = ModelBackendCapabilities(
            reasoning_kind="thinking",
            context_window=200_000,
            supports_tools=True,
            provider_seed_support=False,  # Anthropic has no request seed
            prompt_cache_support=True,
            satisfiable_exposures=frozenset({"thinking_trace_to_agent", "reasoning_tokens_to_agent"}),
        )

    @classmethod
    def for_reasoning(cls, *, reasoning_kind: str, interleaved_thinking: bool = True,
                      effort: str | None = None) -> "AnthropicProviderAdapter":
        """Map the platform's neutral reasoning request onto THIS provider's surface —
        Anthropic exposes verbatim thinking blocks (kind="thinking") and supports the
        interleaved-thinking beta. Provider capability knowledge lives here, never at
        the call site (the runner factory only namespace-routes)."""
        return cls(expose_thinking=(reasoning_kind == "thinking"),
                   interleaved_thinking=interleaved_thinking, effort=effort)

    def _ensure_client(self):
        if self._client is None:
            import anthropic  # lazy (optional `live` extra)

            # A request that gets no answer fails after REQUEST_TIMEOUT_S, not after the SDK's
            # default 600 s (G5 probe, October 14, 2026: a network drop froze two runs for ten
            # minutes, every agent waiting in a model call). max_retries=0: the SDK's own retries
            # would resend a possibly billed request without a record (base.invoke_under_policy).
            self._client = anthropic.Anthropic(api_key=self._api_key or _load_api_key(),
                                               timeout=REQUEST_TIMEOUT_S, max_retries=0)
        return self._client

    # -- translate: neutral → Anthropic Messages API ----------------------- #

    def translate(self, req: ModelRequest) -> dict[str, Any]:
        bps = set(req.cache.breakpoints or [])  # cache markers (manifest-pinned, §3.1)
        ttls = req.cache.ttl_overrides or {}

        def _cc(bp: str) -> dict:
            # Per-breakpoint lifetime ("1h" survives the gaps between same-prefix cells in
            # a sweep; default 5m). Ordering (longer TTLs first) is the policy author's job.
            return {"type": "ephemeral", "ttl": ttls[bp]} if bp in ttls else {"type": "ephemeral"}

        def _mark(blocks: list, bp: str) -> None:
            # The provider refuses cache_control on a thinking block (400, October 10, 2026:
            # a refused response left an assistant message holding only thinking). Mark the
            # last other block; a message of thinking blocks only gets no marker.
            for blk in reversed(blocks):
                if blk.get("type") not in ("thinking", "redacted_thinking"):
                    blk["cache_control"] = _cc(bp)
                    return

        system_parts: list[str] = []
        messages: list[dict] = []
        first_user_idx: int | None = None
        for m in req.messages:
            if m.role == "system":
                system_parts.append(" ".join(b.text for b in m.blocks if b.text))
                continue
            role = "user" if m.role in ("user", "tool") else "assistant"
            content = [self._block_to_anthropic(b) for b in m.blocks]
            if role == "user" and first_user_idx is None:
                first_user_idx = len(messages)
            messages.append({"role": role, "content": content})

        model = req.model_ref.split("/", 1)[-1]  # "anthropic/claude-sonnet-4-6" → "claude-sonnet-4-6"
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": req.sampling.max_output_tokens,
            "messages": messages,
        }
        if system_parts:
            text = "\n\n".join(p for p in system_parts if p)
            if "system" in bps:
                # Cache the static system prefix (read at ~10% on subsequent calls).
                payload["system"] = [{"type": "text", "text": text,
                                      "cache_control": _cc("system")}]
            else:
                payload["system"] = text
        if req.tools:
            tools = [self._tool_to_anthropic(t) for t in req.tools]
            if "tools" in bps and tools:
                tools[-1]["cache_control"] = _cc("tools")  # cache the static tool set
            payload["tools"] = tools
        if "initial_user" in bps and first_user_idx is not None:
            # Cache through the (static) initial user message — the big paper prefix.
            blocks = payload["messages"][first_user_idx]["content"]
            if blocks:
                _mark(blocks, "initial_user")
        if "conversation_tail" in bps and messages:
            # Rolling breakpoint at the latest turn → incremental caching of the whole
            # growing context (pay cache-write once on new tokens, cache-read after).
            tail = payload["messages"][-1]["content"]
            if tail:
                _mark(tail, "conversation_tail")
        if "transcript_tail" in bps and len(messages) >= 2:
            # Rolling breakpoint at the last block BEFORE the final message — for prompts
            # shaped [append-only transcript..., constant closing prompt] (deliberation
            # volleys, M3 §3.1): the cached prefix must end at the transcript. A breakpoint
            # after the constant suffix would never be re-read — the next volley's longer
            # transcript diverges from that prefix at the suffix position.
            blocks = payload["messages"][-2]["content"]
            if blocks:
                _mark(blocks, "transcript_tail")
        if req.sampling.stop:
            payload["stop_sequences"] = list(req.sampling.stop)

        if model in EFFORT_MODELS:
            self._effort_reasoning(payload, req)
        elif req.reasoning.kind == ReasoningKind.THINKING.value:
            payload["thinking"] = {
                "type": "enabled",
                "budget_tokens": req.reasoning.budget_tokens or 4096,
            }
            payload["temperature"] = 1.0  # Anthropic requires temperature=1 with thinking
            if self.interleaved_thinking:
                # Per-turn thinking blocks across the tool loop (DESIGN §17.1 reasoning
                # capture); without this, standard thinking emits a block on ~the first
                # turn only when tools are present.
                payload["extra_headers"] = {"anthropic-beta": self._INTERLEAVED_THINKING_BETA}
        else:
            payload["temperature"] = req.sampling.temperature
        return payload

    def _effort_reasoning(self, payload: dict[str, Any], req: ModelRequest) -> None:
        """Reasoning and sampling for EFFORT_MODELS. A thinking request becomes adaptive
        thinking (summarized when exposed: the raw reasoning is never returned); no
        reasoning becomes ``between_tools``, the lowest setting. A missing effort, a thinking
        budget, or effort xhigh/max without reasoning is refused here, before a request is
        sent; sampling is the provider's default (see EFFORT_MODELS)."""
        model = payload["model"]
        if self.effort is None:
            raise ProviderError(f"{model} needs an explicit effort level (a study setting); none was given")
        if req.reasoning.budget_tokens is not None:
            raise ProviderError(f"{model} takes no thinking budget (requested {req.reasoning.budget_tokens}); "
                                "set an effort level and no budget")
        if req.reasoning.kind == ReasoningKind.THINKING.value:
            payload["thinking"] = ({"type": "adaptive", "display": "summarized"} if self.expose_thinking
                                   else {"type": "adaptive"})
        else:
            if self.effort in ("xhigh", "max"):
                raise ProviderError(f"{model}: effort {self.effort!r} needs reasoning; the lowest setting "
                                    "allows effort 'high' or below")
            payload["thinking"] = {"type": NO_REASONING_TYPE.get(model, "between_tools")}
        payload["output_config"] = {"effort": self.effort}

    def _block_to_anthropic(self, b: NeutralBlock) -> dict:
        if b.kind == BlockKind.TOOL_USE.value:
            return {"type": "tool_use", "id": b.tool_call_id, "name": b.tool_name, "input": b.arguments or {}}
        if b.kind == BlockKind.TOOL_RESULT.value:
            return {"type": "tool_result", "tool_use_id": b.tool_call_id, "content": b.text}
        if b.kind == BlockKind.THINKING.value and b.provider_opaque:
            return dict(b.provider_opaque)  # re-emit the signed thinking block VERBATIM
        return {"type": "text", "text": b.text}

    def _tool_to_anthropic(self, t: ToolSpec) -> dict:
        schema = t.parameters_schema or {"type": "object", "properties": {}}
        if "type" not in schema:
            schema = {"type": "object", **schema}
        return {"name": t.name, "description": t.description, "input_schema": schema}

    # -- invoke: ONE request/response (no loop, no tool_runner) ------------- #

    # Waits before resending a call whose connection could not open, or that the provider
    # refused before processing (429), in seconds (LK1 pilot, 2026-10-04: a network outage of
    # under a minute ended a run, because one failed call removes a role). About eight minutes
    # in all. A request that may have been processed is resent only after UNCERTAIN_WAITS.
    TRANSPORT_WAITS: tuple[float, ...] = (15, 30, 60, 120, 240)
    UNCERTAIN_WAITS: tuple[float, ...] = UNCERTAIN_WAITS

    @staticmethod
    def _classify(exc: BaseException) -> tuple[str, int | str | None]:
        """Sort a failed attempt for the shared call policy (base.invoke_under_policy)."""
        import anthropic
        import httpx

        if is_malformed_response(exc, anthropic.APIResponseValidationError):  # before the status checks: it may carry 200
            return UNCERTAIN, "malformed"
        if isinstance(exc, anthropic.APITimeoutError):  # before APIConnectionError, its parent
            return UNCERTAIN, "timeout"
        if isinstance(exc, anthropic.APIConnectionError):
            if isinstance(exc.__cause__, (httpx.ConnectError, httpx.ConnectTimeout)):
                return NOT_SENT, None
            return LOST, None
        status = getattr(exc, "status_code", None)  # anthropic.APIStatusError carries the HTTP status
        if status == 429:
            return RATE_LIMITED, status
        if status in TRANSIENT_STATUSES:
            return UNCERTAIN, status
        if status in NOT_PROCESSED:
            return REJECTED, status
        return FAILED, status

    async def invoke(self, payload: dict[str, Any]) -> RawProviderResponse:
        client = self._ensure_client()
        return await invoke_under_policy(lambda: client.messages.create(**payload), self._classify,
                                         "anthropic messages.create", transport_waits=self.TRANSPORT_WAITS,
                                         uncertain_waits=self.UNCERTAIN_WAITS)

    # -- normalize: Anthropic → neutral (+ raw ref) ------------------------- #

    def normalize(self, raw: RawProviderResponse, req: ModelRequest, raw_ref: str) -> ModelResponse:
        p = raw.payload
        blocks: list[NeutralBlock] = []
        for blk in p.get("content", []):
            t = blk.get("type")
            if t == "text":
                blocks.append(NeutralBlock(kind=BlockKind.TEXT.value, text=blk.get("text", "")))
            elif t == "tool_use":
                blocks.append(NeutralBlock(
                    kind=BlockKind.TOOL_USE.value, tool_name=blk.get("name"),
                    tool_call_id=blk.get("id"), arguments=blk.get("input") or {},
                ))
            elif t == "thinking":
                # Keep the signed block verbatim so it can ride back out on the next turn.
                exposed = self.expose_thinking
                blocks.append(NeutralBlock(
                    kind=BlockKind.THINKING.value,
                    text=blk.get("thinking", "") if exposed else "",
                    provider_opaque=dict(blk),
                ))
        usage = p.get("usage", {}) or {}
        cache_read = usage.get("cache_read_input_tokens")
        cache_write = usage.get("cache_creation_input_tokens")
        creation = usage.get("cache_creation")
        write_split = ({"5m": creation.get("ephemeral_5m_input_tokens", 0),
                        "1h": creation.get("ephemeral_1h_input_tokens", 0)}
                       if isinstance(creation, dict) else None)
        if cache_write and "1h" in req.cache.ttl_overrides.values() and write_split is None:
            raise ProviderError("cache-write usage is missing the requested lifetime breakdown")
        in_tok = usage.get("input_tokens", 0)
        # Reasoning/thinking tokens only when the provider reports them — never
        # fabricated (M3 §1). Anthropic bills thinking inside output_tokens and
        # may surface a dedicated count under one of these keys depending on API
        # version; absent that, this stays None rather than guessing.
        reasoning_tok = usage.get("reasoning_output_tokens")
        if reasoning_tok is None:  # explicit None, not falsy — a reported 0 is a real report
            reasoning_tok = usage.get("thinking_tokens")
        token_split = TokenSplit(
            input=in_tok,
            output=usage.get("output_tokens", 0),
            cache_read=cache_read,
            cache_write=cache_write,
            reasoning=reasoning_tok,
            input_uncached_equiv=(in_tok + (cache_read or 0) + (cache_write or 0))
            if cache_read is not None or cache_write is not None else None,
            cache_write_by_ttl=write_split,
        )
        stop = _STOP_MAP.get(p.get("stop_reason"), StopReason.ERROR.value)
        return ModelResponse(
            model_call_id=req.call_id,
            model_ref=req.model_ref,
            stop_reason=stop,
            content_blocks=blocks,
            usage=token_split,
            realized_reasoning=RealizedReasoning(
                kind=(ReasoningKind.SUMMARY.value if req.model_ref.split("/", 1)[-1] in EFFORT_MODELS
                      and req.reasoning.kind != "none" else req.reasoning.kind),
                requested_budget=req.reasoning.budget_tokens,
                realized_tokens=reasoning_tok,
            ),
            raw_provider_response_ref=raw_ref,
        )

    def satisfiable_exposures(self) -> set[str]:
        return set(self.capabilities.satisfiable_exposures)

    def capabilities_for(self, model_ref: str) -> ModelBackendCapabilities:
        """Effort models expose summaries, which cannot satisfy a full-trace contract."""
        if model_ref.split("/", 1)[-1] in EFFORT_MODELS:
            return replace(self.capabilities, reasoning_kind="summary", context_window=1_000_000,
                           satisfiable_exposures=self.capabilities.satisfiable_exposures - {"thinking_trace_to_agent"})
        return self.capabilities

    # -- estimate_tokens: local estimate (no provider request) --------- #

    def estimate_tokens(self, messages: list[NeutralMessage], tools: list[ToolSpec]) -> int:
        """Estimate input tokens locally using the shared text-length and framing heuristic."""
        return estimate_input_tokens_chars(messages, tools)
