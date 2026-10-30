"""Translate platform requests into OpenAI Chat Completions calls.

Each invocation makes one request; the host's agent loop executes tools and
chooses the next action. This adapter subtracts cached input from total input
before cost attribution, so cached tokens are not charged twice. It records
reasoning-token counts and any returned reasoning summary, but does not provide
a raw reasoning trace. A summary is not equivalent to that trace.

The openai SDK is imported lazily. It must be installed separately: the current
pyproject.toml's live extra includes anthropic, python-dotenv and openai.
See docs/RUNBOOK.md for setup and experiments/parity.py for comparison checks."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from oaos2.models.adapters.base import (
    FAILED,
    LOST,
    NOT_PROCESSED,
    NOT_SENT,
    PROMPT_FLAGGED,
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
    "stop": StopReason.END_TURN.value,
    "tool_calls": StopReason.TOOL_USE.value,
    "function_call": StopReason.TOOL_USE.value,
    "length": StopReason.MAX_TOKENS.value,
    "content_filter": StopReason.REFUSAL.value,
}


def _load_api_key(env_var: str = "OPENAI_API_KEY") -> str:
    """Read the provider key host-side: the environment, else the repository's own .env. Never to a container."""
    key = os.environ.get(env_var)
    if not key:
        try:
            import dotenv  # optional
            from pathlib import Path

            key = dotenv.dotenv_values(Path(__file__).resolve().parents[3] / ".env").get(env_var)
        except Exception:  # pragma: no cover
            pass
    if not key:
        raise ProviderError(f"{env_var} not set (host-side .env or env var)")
    return key


# Models that always reason and accept only the default sampling (no temperature or top_p).
REASONING_ONLY_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def _reasoning_effort(budget_tokens: int | None) -> str:
    """Map a neutral reasoning budget onto OpenAI's coarse effort knob.

    OpenAI reasoning models take ``reasoning_effort`` (low|medium|high), not a token
    budget; we bucket the requested budget so the *intent* (more thinking) carries
    across providers even though the dial is coarser.
    """
    b = budget_tokens or 0
    if b and b <= 2048:
        return "low"
    if b and b >= 16384:
        return "high"
    return "medium"


# A request with no answer within this many seconds is abandoned (the SDK's default is 600). On October 14, 2026 OpenAI
# left every open request unanswered for ten minutes, and four PC1 runs ended at once with usage unknown; the slowest
# response seen in PC1 took 52 s (ported from PC1, 4c69981).
REQUEST_TIMEOUT_S = 300.0
# The same limit on the whole call. The SDK's timeout bounds each wait for data, not the call: on October 15, 2026 a
# Kimi K2.6 call through OpenRouter ran 57.5 minutes, the connection never idle (ported from PC1, 486b63a).
CALL_DEADLINE_S = 300.0
# A provider's safety filter rejecting the prompt itself (October 15, 2026, the PC1 x5 audit): OpenAI answers 400
# "Invalid prompt: your prompt was flagged as potentially violating our usage policy"; OpenRouter hosts answer 400 or 403
# with a moderation message. Taken as an error, it retired the laboratory without counting as a refusal; it is returned
# instead as a refusal at no cost, which the agent loop re-sends, counts and bounds like any other (ported from PC1,
# 956f567).
PROMPT_REFUSED = re.compile(r"flagged as potentially violating|usage polic|moderation|content polic", re.I)


class OpenAIProviderAdapter:
    provider_id = "openai"
    # OpenAI-compatible endpoint knobs (subclassed by together/openrouter in
    # openai_compatible.py): the wire protocol is identical; only the base URL
    # and the host-side key variable differ. None → the official OpenAI API.
    base_url: str | None = None
    api_key_env: str = "OPENAI_API_KEY"

    def __init__(self, *, api_key: str | None = None, expose_thinking: bool = False) -> None:
        self._api_key = api_key
        self._client = None  # lazy
        # OpenAI never returns the raw chain-of-thought, only a summary, so
        # exposing "thinking" to the agent surfaces (at most) the reasoning summary.
        self.expose_thinking = expose_thinking
        self.capabilities = ModelBackendCapabilities(
            reasoning_kind="summary",  # summaries, not the raw trace (≠ Anthropic "thinking")
            context_window=400_000,
            supports_tools=True,
            provider_seed_support=True,  # OpenAI honours a request `seed` (best-effort)
            prompt_cache_support=True,  # automatic prompt caching (no explicit breakpoints)
            satisfiable_exposures=frozenset({"reasoning_tokens_to_agent"}),
        )

    @classmethod
    def for_reasoning(cls, *, reasoning_kind: str, interleaved_thinking: bool = True,
                      effort: str | None = None) -> "OpenAIProviderAdapter":
        """Map the platform's neutral reasoning request onto THIS provider's surface —
        OpenAI returns only reasoning summaries (never the raw trace), so both
        "thinking" and "summary" expose the summary; interleaved thinking is an
        Anthropic-only surface and is ignored here. Provider capability knowledge
        lives here, never at the call site."""
        del interleaved_thinking, effort  # Anthropic-only surfaces (effort: its EFFORT_MODELS)
        return cls(expose_thinking=(reasoning_kind in ("thinking", "summary")))

    def _ensure_client(self):
        if self._client is None:
            import openai  # lazy (optional `live` extra)

            # max_retries=0: the SDK's own retries would resend a possibly billed request
            # without a record (base.invoke_under_policy).
            self._client = openai.OpenAI(
                api_key=self._api_key or _load_api_key(self.api_key_env), max_retries=0,
                timeout=REQUEST_TIMEOUT_S, **({"base_url": self.base_url} if self.base_url else {}))
        return self._client

    def _drop_client(self) -> None:
        """Close the client and its connections (a call abandoned at its deadline); the next call opens a new one."""
        client, self._client = self._client, None
        try:
            if client is not None and hasattr(client, "close"):
                client.close()
        except Exception:  # noqa: BLE001 — a failed close must not end the call
            pass

    # -- translate: neutral → OpenAI Chat Completions ---------------------- #

    def translate(self, req: ModelRequest) -> dict[str, Any]:
        messages: list[dict] = []
        for m in req.messages:
            messages.extend(self._message_to_openai(m))

        model = req.model_ref.split("/", 1)[-1]  # "openai/gpt-5" → "gpt-5"
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            # Newer OpenAI models reject `max_tokens` in favour of `max_completion_tokens`
            # (reasoning tokens count against it too) — use the forward-compatible field.
            "max_completion_tokens": req.sampling.max_output_tokens,
        }
        if req.tools:
            payload["tools"] = [self._tool_to_openai(t) for t in req.tools]
            if self.tool_choice:
                payload["tool_choice"] = self.tool_choice
        if req.sampling.stop:
            payload["stop"] = list(req.sampling.stop)
        if req.sampling.platform_seed is not None:
            payload["seed"] = req.sampling.platform_seed  # OpenAI honours a request seed (best-effort)

        if req.reasoning.kind in (ReasoningKind.THINKING.value, ReasoningKind.SUMMARY.value):
            # Reasoning models fix temperature at the default; sending a custom temperature
            # is rejected, so we omit it entirely when reasoning is on.
            payload["reasoning_effort"] = _reasoning_effort(req.reasoning.budget_tokens)
        elif model.startswith(REASONING_ONLY_PREFIXES):
            # G5 model check, 2026-10-19: a memory recap asks for no reasoning at temperature 0,
            # which GPT-5 models refuse (400, "Only the default (1) value is supported"); one refused
            # recap removed a role. These models always reason: the least of it, default sampling.
            payload["reasoning_effort"] = "minimal"
        else:
            payload["temperature"] = req.sampling.temperature
            payload.update(self.no_reasoning_extra(model))
        return payload

    def no_reasoning_extra(self, model: str) -> dict[str, Any]:
        """Extra request fields when no reasoning is asked for (a memory recap). None on the OpenAI API itself; the
        open-weight hosts override it (openai_compatible.py)."""
        del model
        return {}

    def _message_to_openai(self, m: NeutralMessage) -> list[dict]:
        """One neutral message → one or more OpenAI messages.

        OpenAI aggregates an assistant turn's text + tool calls into a SINGLE
        message object (unlike Anthropic's block list), and each tool result is its
        own ``role:"tool"`` message — so this fans out rather than mapping 1:1.
        """
        if m.role == "system":
            text = " ".join(b.text for b in m.blocks if b.text)
            return [{"role": "system", "content": text}] if text else []
        if m.role == "tool":
            # Each tool_result becomes a standalone tool message keyed by call id.
            out = []
            for b in m.blocks:
                if b.kind == BlockKind.TOOL_RESULT.value:
                    out.append({"role": "tool", "tool_call_id": b.tool_call_id,
                                "content": b.text or ""})
            return out
        if m.role == "assistant":
            text_parts, tool_calls = [], []
            for b in m.blocks:
                if b.kind == BlockKind.TOOL_USE.value:
                    tool_calls.append({
                        "id": b.tool_call_id, "type": "function",
                        "function": {"name": b.tool_name,
                                     "arguments": json.dumps(b.arguments or {})},
                    })
                elif b.kind == BlockKind.TEXT.value and b.text:
                    text_parts.append(b.text)
                # THINKING blocks are dropped: OpenAI has no verbatim re-emission path
                # (the raw trace is never returned), so there is nothing to echo back.
            msg: dict[str, Any] = {"role": "assistant"}
            msg["content"] = "\n".join(text_parts) if text_parts else None
            if tool_calls:
                msg["tool_calls"] = tool_calls
            return [msg]
        # user (and any fallback)
        text = " ".join(b.text for b in m.blocks if b.text)
        return [{"role": "user", "content": text}]

    def _tool_to_openai(self, t: ToolSpec) -> dict:
        schema = t.parameters_schema or {"type": "object", "properties": {}}
        if "type" not in schema:
            schema = {"type": "object", **schema}
        return {"type": "function",
                "function": {"name": t.name, "description": t.description, "parameters": schema}}

    # -- invoke: ONE request/response (no loop, no tool_runner) ------------ #

    # Waits before resending a request that could not have been processed (a connection that
    # never opened, or a 429), and before resending one that may have been (seconds). G5 model
    # check, 2026-10-19: OpenRouter's upstream rate-limited Qwen 3.8 Flash (429) and the one
    # failed call removed a role, which ended the run (T1, 7905467).
    TRANSPORT_WAITS: tuple[float, ...] = (15, 30, 60, 120, 240)
    UNCERTAIN_WAITS: tuple[float, ...] = UNCERTAIN_WAITS
    # ``tool_choice`` sent with every request that offers tools (None: not sent, the provider's
    # "auto"). G5 model check, 2026-10-19: GPT-5-mini ended 147 of 160 turns in prose, a plan with
    # no tool call; "required" makes each turn act, and waiting stays a tool the agent can choose.
    tool_choice: str | None = None

    @staticmethod
    def _classify(exc: BaseException) -> tuple[str, int | str | None]:
        """Sort a failed attempt for the shared call policy (base.invoke_under_policy)."""
        import httpx
        import openai

        if is_malformed_response(exc, openai.APIResponseValidationError):  # before the status checks: it may carry 200
            return UNCERTAIN, "malformed"
        if isinstance(exc, openai.APITimeoutError):  # before APIConnectionError, its parent
            return UNCERTAIN, "timeout"
        if isinstance(exc, openai.APIConnectionError):
            if isinstance(exc.__cause__, (httpx.ConnectError, httpx.ConnectTimeout)):
                return NOT_SENT, None
            return LOST, None
        status = getattr(exc, "status_code", None)
        if status == 429 and getattr(exc, "code", None) == "insufficient_quota":
            return REJECTED, status  # an exhausted quota is not waited out (T1, 7905467)
        if status == 429:
            return RATE_LIMITED, status
        if status in TRANSIENT_STATUSES:
            return UNCERTAIN, status
        if status in (400, 403) and PROMPT_REFUSED.search(str(exc)):
            return PROMPT_FLAGGED, status
        if status in NOT_PROCESSED:
            return REJECTED, status
        return FAILED, status

    async def invoke(self, payload: dict[str, Any]) -> RawProviderResponse:
        # Each attempt takes the adapter's current client: a call abandoned at its deadline closes
        # the client (_drop_client), and a resend on that closed client failed with "Cannot send a
        # request, as the client has been closed" (PC1 9.2 calibration, October 20, 2026).
        return await invoke_under_policy(lambda: self._ensure_client().chat.completions.create(**payload),
                                         self._classify,
                                         f"{self.provider_id} chat.completions.create",
                                         transport_waits=self.TRANSPORT_WAITS, uncertain_waits=self.UNCERTAIN_WAITS,
                                         deadline_s=CALL_DEADLINE_S, on_deadline=self._drop_client,
                                         refusal_payload=lambda: {
                                             "choices": [{"message": {"content": None}, "finish_reason": "content_filter"}],
                                             "usage": {"prompt_tokens": 0, "completion_tokens": 0,
                                                       "prompt_tokens_details": {"cached_tokens": 0}}})

    # -- normalize: OpenAI → neutral (+ raw ref) --------------------------- #

    def normalize(self, raw: RawProviderResponse, req: ModelRequest, raw_ref: str) -> ModelResponse:
        p = raw.payload
        choices = p.get("choices") or [{}]
        choice = choices[0]
        msg = choice.get("message", {}) or {}
        blocks: list[NeutralBlock] = []

        # Reasoning summary (when present and exposed) rides as a THINKING block, but it
        # is a SUMMARY not the raw trace — recorded as such, never claimed as the CoT.
        summary = msg.get("reasoning") or msg.get("reasoning_content")
        if summary:
            blocks.append(NeutralBlock(
                kind=BlockKind.THINKING.value,
                text=str(summary) if self.expose_thinking else "",
                provider_opaque={"type": "reasoning_summary", "text": str(summary)},
            ))
        if msg.get("content"):
            blocks.append(NeutralBlock(kind=BlockKind.TEXT.value, text=msg["content"]))
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {}) or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except (ValueError, TypeError):
                args = {}  # malformed tool args → empty dict; the loop's gate handles it
            blocks.append(NeutralBlock(
                kind=BlockKind.TOOL_USE.value, tool_name=fn.get("name"),
                tool_call_id=tc.get("id"), arguments=args,
            ))

        usage = p.get("usage", {}) or {}
        in_full = usage.get("prompt_tokens", 0)  # OpenAI: INCLUDES cached tokens
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
        reasoning_tok = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        # Subtract the cached portion so the ledger doesn't bill it at full rate AND
        # the cache rate (see module docstring); input_uncached_equiv keeps the full count.
        net_input = (in_full - cached) if cached is not None else in_full
        token_split = TokenSplit(
            input=net_input,
            output=usage.get("completion_tokens", 0),
            cache_read=cached,
            cache_write=None,  # OpenAI auto-cache: no separately-billed write tokens
            reasoning=reasoning_tok,
            input_uncached_equiv=in_full if cached is not None else None,
        )
        stop = _STOP_MAP.get(choice.get("finish_reason"), StopReason.ERROR.value)
        return ModelResponse(
            model_call_id=req.call_id,
            model_ref=req.model_ref,
            stop_reason=stop,
            content_blocks=blocks,
            usage=token_split,
            realized_reasoning=RealizedReasoning(
                kind=req.reasoning.kind,
                requested_budget=req.reasoning.budget_tokens,
                realized_tokens=reasoning_tok,
            ),
            raw_provider_response_ref=raw_ref,
        )

    def satisfiable_exposures(self) -> set[str]:
        return set(self.capabilities.satisfiable_exposures)

    # -- estimate_tokens: local estimate (no provider request) -------- #

    def estimate_tokens(self, messages: list[NeutralMessage], tools: list[ToolSpec]) -> int:
        """Estimate input tokens locally using the shared text-length and framing heuristic."""
        return estimate_input_tokens_chars(messages, tools)
