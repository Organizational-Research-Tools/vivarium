"""Translate platform requests into OpenAI Responses API calls (namespace ``openai_responses``).

The Chat Completions adapter (``openai.py``) returns no reasoning summary and cannot send function tools together
with a reasoning setting to some newer models (``gpt-6-luna`` rejects the combination, October 12, 2026). The
Responses API does both: each reasoning item carries a summary, which the platform records as a summary (never as a
raw trace), and its encrypted content, which this adapter echoes back on the next request so the model keeps its
reasoning across tool calls without the provider storing the conversation (``store: false``).

One request per invocation; the host's agent loop runs the tools. Accounting follows the Anthropic adapter: the
SDK's hidden retries are off; only a connection that never opened is retried (it cannot have been processed); a
validation, authentication, permission, payment or rate-limit rejection is marked not billed; any other failure
leaves usage unknown. Cached input is subtracted from input before cost attribution.

A separate namespace keeps the Chat Completions path, and the provider checks recorded for it, unchanged.
"""

from __future__ import annotations

import json
from typing import Any

from oaos2.models.adapters.base import (
    ModelBackendCapabilities,
    RawProviderResponse,
    estimate_input_tokens_chars,
)
from oaos2.models.adapters.base import UNCERTAIN_WAITS, invoke_under_policy
from oaos2.models.adapters.openai import (CALL_DEADLINE_S, REQUEST_TIMEOUT_S, OpenAIProviderAdapter, _load_api_key,
                                          _reasoning_effort)
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


class OpenAIResponsesProviderAdapter:
    provider_id = "openai_responses"
    api_key_env = "OPENAI_API_KEY"
    TRANSPORT_WAITS: tuple[float, ...] = (15, 30, 60, 120, 240)
    UNCERTAIN_WAITS: tuple[float, ...] = UNCERTAIN_WAITS
    # the same SDK and status codes as Chat Completions: the same sorting of failed attempts
    _classify = staticmethod(OpenAIProviderAdapter._classify)
    # ``tool_choice`` sent with every request that offers tools (None: not sent, the provider's "auto"). G5,
    # October 19: gpt-5-mini through this adapter still ended most turns with a status report to an imagined
    # operator; "required" makes each turn act, and waiting stays a tool the agent can choose.
    tool_choice: str | None = None
    # ``inbox_as_tool_result`` (G5, October 19; off: unchanged). The agent loop delivers what arrives between turns
    # (other teams' notes, the workshop's announcements) as a user message, which gpt-5-mini answered as if a person
    # had written to it ("Acknowledged — the run continues. Current state..."). With this on, every user message
    # after the first (the brief, or a recap after compaction) is sent as the result of a ``read_notes`` call, the
    # OpenAI convention for what an agent's environment reports. The platform's own history is unchanged.
    inbox_as_tool_result: bool = False

    def __init__(self, *, api_key: str | None = None, expose_thinking: bool = False) -> None:
        self._api_key = api_key
        self._client = None
        self.expose_thinking = expose_thinking
        self.capabilities = ModelBackendCapabilities(
            reasoning_kind="summary",  # summaries, not the raw trace
            context_window=400_000,
            supports_tools=True,
            provider_seed_support=False,  # the Responses API takes no seed
            prompt_cache_support=True,  # automatic prompt caching
            satisfiable_exposures=frozenset({"reasoning_tokens_to_agent"}),
        )

    @classmethod
    def for_reasoning(cls, *, reasoning_kind: str, interleaved_thinking: bool = True,
                      effort: str | None = None) -> "OpenAIResponsesProviderAdapter":
        del interleaved_thinking, effort  # Anthropic-only surfaces
        return cls(expose_thinking=(reasoning_kind in ("thinking", "summary")))

    def _drop_client(self):
        """Close the client and its connections (a call abandoned at its deadline); the next call opens a new one."""
        client, self._client = self._client, None
        if client is not None and hasattr(client, "close"):
            client.close()

    def _ensure_client(self):
        if self._client is None:
            import openai

            self._client = openai.OpenAI(api_key=self._api_key or _load_api_key(self.api_key_env), max_retries=0,
                                         timeout=REQUEST_TIMEOUT_S)
        return self._client

    # -- translate: neutral → Responses input items -------------------------- #

    def translate(self, req: ModelRequest) -> dict[str, Any]:
        instructions: list[str] = []
        items: list[dict] = []
        users = 0
        for i, m in enumerate(req.messages):
            if m.role == "system":
                instructions += [b.text for b in m.blocks if b.text]
                continue
            if m.role == "user":
                users += 1
                text = " ".join(b.text for b in m.blocks if b.text)
                if self.inbox_as_tool_result and users > 1 and text:
                    call_id = f"inbox_{i}"
                    items += [{"type": "function_call", "call_id": call_id, "name": "read_notes", "arguments": "{}"},
                              {"type": "function_call_output", "call_id": call_id, "output": text}]
                    continue
            items.extend(self._message_items(m))
        payload: dict[str, Any] = {
            "model": req.model_ref.split("/", 1)[-1],
            "input": items,
            "max_output_tokens": req.sampling.max_output_tokens,
            "store": False,
        }
        if instructions:
            payload["instructions"] = "\n\n".join(instructions)
        if req.tools:
            payload["tools"] = [self._tool(t) for t in req.tools]
            if self.tool_choice:
                payload["tool_choice"] = self.tool_choice
        if req.reasoning.kind in (ReasoningKind.THINKING.value, ReasoningKind.SUMMARY.value):
            # Reasoning models fix temperature; the summary is requested and the encrypted reasoning is returned so
            # that it can ride back on the next request.
            payload["reasoning"] = {"effort": _reasoning_effort(req.reasoning.budget_tokens), "summary": "auto"}
            payload["include"] = ["reasoning.encrypted_content"]
        # No temperature, ever: the models reached this way are reasoning models, which reject one (400). A request
        # without reasoning (a memory recap) therefore runs at the model's default reasoning; until October 12,
        # 2026 it was sent a temperature, and two labs of the first Responses run failed at their first recap.
        return payload

    def _message_items(self, m: NeutralMessage) -> list[dict]:
        if m.role == "tool":
            return [{"type": "function_call_output", "call_id": b.tool_call_id, "output": b.text or ""}
                    for b in m.blocks if b.kind == BlockKind.TOOL_RESULT.value]
        if m.role == "assistant":
            out: list[dict] = []
            text: list[str] = []
            for b in m.blocks:
                if b.kind == BlockKind.THINKING.value:
                    op = b.provider_opaque or {}
                    if op.get("type") == "reasoning" and op.get("encrypted_content"):
                        out.append({"type": "reasoning", "id": op.get("id"), "summary": op.get("summary") or [],
                                    "encrypted_content": op["encrypted_content"]})
                elif b.kind == BlockKind.TEXT.value and b.text:
                    text.append(b.text)
                elif b.kind == BlockKind.TOOL_USE.value:
                    if text:
                        out.append({"role": "assistant", "content": "\n".join(text)})
                        text = []
                    out.append({"type": "function_call", "call_id": b.tool_call_id, "name": b.tool_name,
                                "arguments": json.dumps(b.arguments or {})})
            if text:
                out.append({"role": "assistant", "content": "\n".join(text)})
            return out
        text = " ".join(b.text for b in m.blocks if b.text)
        return [{"role": "user", "content": text}] if text else []

    @staticmethod
    def _tool(t: ToolSpec) -> dict:
        schema = t.parameters_schema or {"type": "object", "properties": {}}
        if "type" not in schema:
            schema = {"type": "object", **schema}
        return {"type": "function", "name": t.name, "description": t.description, "parameters": schema,
                "strict": False}

    # -- invoke: one request -------------------------------------------------- #

    async def invoke(self, payload: dict[str, Any]) -> RawProviderResponse:
        # Each attempt takes the adapter's current client: a call abandoned at its deadline closes
        # the client (_drop_client), and a resend on that closed client failed with "Cannot send a
        # request, as the client has been closed" (PC1 9.2 calibration, October 20, 2026).
        return await invoke_under_policy(lambda: self._ensure_client().responses.create(**payload),
                                         self._classify,
                                         f"{self.provider_id} responses.create",
                                         transport_waits=self.TRANSPORT_WAITS, uncertain_waits=self.UNCERTAIN_WAITS,
                                         deadline_s=CALL_DEADLINE_S, on_deadline=self._drop_client,
                                         refusal_payload=lambda: {
                                             "status": "incomplete", "incomplete_details": {"reason": "content_filter"},
                                             "output": [], "usage": {"input_tokens": 0, "output_tokens": 0,
                                                                     "input_tokens_details": {"cached_tokens": 0},
                                                                     "output_tokens_details": {"reasoning_tokens": 0}}})

    # -- normalize: Responses output → neutral --------------------------------- #

    def normalize(self, raw: RawProviderResponse, req: ModelRequest, raw_ref: str) -> ModelResponse:
        p = raw.payload
        blocks: list[NeutralBlock] = []
        refused = False
        for item in p.get("output") or []:
            t = item.get("type")
            if t == "reasoning":
                summary = "\n\n".join(s.get("text", "") for s in item.get("summary") or [] if isinstance(s, dict))
                blocks.append(NeutralBlock(
                    kind=BlockKind.THINKING.value, text=summary if self.expose_thinking else "",
                    provider_opaque={"type": "reasoning", "id": item.get("id"), "summary": item.get("summary") or [],
                                     "encrypted_content": item.get("encrypted_content"), "is_summary": True}))
            elif t == "message":
                for c in item.get("content") or []:
                    if c.get("type") == "output_text" and c.get("text"):
                        blocks.append(NeutralBlock(kind=BlockKind.TEXT.value, text=c["text"]))
                    elif c.get("type") == "refusal":
                        refused = True
            elif t == "function_call":
                try:
                    args = json.loads(item.get("arguments") or "{}")
                except (ValueError, TypeError):
                    args = {}
                blocks.append(NeutralBlock(kind=BlockKind.TOOL_USE.value, tool_name=item.get("name"),
                                           tool_call_id=item.get("call_id"), arguments=args))
        incomplete = (p.get("incomplete_details") or {}).get("reason")
        if refused or incomplete == "content_filter":
            stop = StopReason.REFUSAL.value
        elif incomplete == "max_output_tokens":
            stop = StopReason.MAX_TOKENS.value
        elif any(b.kind == BlockKind.TOOL_USE.value for b in blocks):
            stop = StopReason.TOOL_USE.value
        elif p.get("status") == "completed":
            stop = StopReason.END_TURN.value
        else:
            stop = StopReason.ERROR.value
        usage = p.get("usage") or {}
        in_full = usage.get("input_tokens", 0)
        cached = (usage.get("input_tokens_details") or {}).get("cached_tokens")
        reasoning_tok = (usage.get("output_tokens_details") or {}).get("reasoning_tokens")
        token_split = TokenSplit(
            input=(in_full - cached) if cached is not None else in_full,
            output=usage.get("output_tokens", 0),
            cache_read=cached,
            cache_write=None,
            reasoning=reasoning_tok,
            input_uncached_equiv=in_full if cached is not None else None,
        )
        return ModelResponse(
            model_call_id=req.call_id, model_ref=req.model_ref, stop_reason=stop, content_blocks=blocks,
            usage=token_split,
            realized_reasoning=RealizedReasoning(kind=req.reasoning.kind, requested_budget=req.reasoning.budget_tokens,
                                                 realized_tokens=reasoning_tok),
            raw_provider_response_ref=raw_ref,
        )

    def satisfiable_exposures(self) -> set[str]:
        return set(self.capabilities.satisfiable_exposures)

    def estimate_tokens(self, messages: list[NeutralMessage], tools: list[ToolSpec]) -> int:
        return estimate_input_tokens_chars(messages, tools)
