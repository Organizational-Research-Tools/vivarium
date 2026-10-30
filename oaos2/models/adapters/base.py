"""Define the provider-adapter interface and shared token estimator.

translate converts a ModelRequest to provider format; invoke sends it;
normalize returns a ModelResponse linked to the saved provider payload.
satisfiable_exposures lists which requested model information the adapter can
supply. estimate_tokens supplies the input estimate used before reserving spend.

The character-based estimate includes margins and framing overhead. It is an
empirical estimate, not a mathematical upper bound for every tokenizer or model.
Validate it against reported usage for the selected provider and model before
relying on it for a study's spending limit. See experiments/parity.py."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Protocol

from oaos2.models.types import ModelRequest, ModelResponse, NeutralMessage, ToolSpec

# Estimate input before dispatch, including framing that is absent from visible text.
# The shared allowances were widened after provider probes found under-counting
# around tool definitions. They cover those probes, not every possible request.
# Keep adapters on one estimator and recheck usage when request shapes change.
_EST_MARGIN = 1.3
_EST_MARGIN_FLOOR = 64
_EST_MSG_OVERHEAD = 8       # per-message envelope
_EST_TOOL_OVERHEAD = 200    # per tool spec framing
_EST_TOOLS_BASE = 600       # tool-use system scaffolding (any tool present)


def estimate_input_tokens_chars(messages: list[NeutralMessage], tools: list[ToolSpec]) -> int:
    """Estimate input tokens from text length with added framing allowances.

    This local heuristic avoids a provider request. Compare it with reported
    usage for the models and request shapes a study will use; it is not a
    universal upper bound."""
    chars = 0
    for m in messages:
        chars += len(m.role)
        for b in m.blocks:
            chars += len(b.text or "")
            if b.arguments:
                chars += len(json.dumps(b.arguments))
            if getattr(b, "provider_opaque", None):
                chars += len(json.dumps(b.provider_opaque))
    for t in tools:
        chars += len(t.name) + len(t.description) + len(json.dumps(t.parameters_schema or {}))
    overhead = _EST_MSG_OVERHEAD * len(messages) + _EST_TOOL_OVERHEAD * len(tools)
    if tools:
        overhead += _EST_TOOLS_BASE
    return math.ceil(chars / 3 * _EST_MARGIN) + _EST_MARGIN_FLOOR + overhead


class ProviderError(Exception):
    """A provider/transport failure (→ model.invocation_failed).

    ``not_billed``: the adapter established that no request was processed (a connection
    never opened, or a validation/authentication/rate-limit rejection). The gateway then
    releases the call's reservation instead of holding the ledger unresolved (October 10,
    2026: one rejected request stopped every agent of a G4 check). Any other failure
    leaves usage unknown. ``transport_retries``: the waits completed before the final
    attempt failed, recorded by the gateway like those of a successful call."""

    def __init__(self, *args, not_billed: bool = False, transport_retries: list[dict] | None = None) -> None:
        super().__init__(*args)
        self.not_billed = not_billed
        self.transport_retries = list(transport_retries or [])


# The call policy shared by the provider adapters (consolidation, October 19, 2026). It
# reconciles two branches: T1 resent any lost connection, timeouts included, after the
# SDK's own hidden retries, so one reservation could cover many billed requests; PC1
# disabled the SDK retries and resent only what could not have been processed, except
# timeouts and server errors on the OpenAI family, resent under the reservation with
# usage recorded as unknown (October 12 and 14). The rule here: SDK retries are off in
# every adapter; every resend is a recorded attempt; a request the provider cannot have
# processed is resent freely and released if it never succeeds; a request it may have
# processed is resent at most len(uncertain_waits) times, each attempt recorded with
# usage unknown; anything else fails the call. A connection broken after sending (LOST) counts
# as possibly processed since October 21, 2026 (the PI): three of 26 G5 pilot runs on
# gpt-6-luna had ended on one ("Connection error", usage unknown, dispatch then refused).

# Statuses at which the provider refused the request before processing it.
NOT_PROCESSED = frozenset({400, 401, 402, 403, 404, 413, 422, 429})
# Server and gateway errors: the request may have been processed (October 15, 2026: a
# Cloudflare 520 at OpenAI and a 502 at Together each ended a PC1 run).
TRANSIENT_STATUSES = frozenset({500, 502, 503, 504, 520, 521, 522, 523, 524, 529})
# Waits before resending a request that may have been processed (seconds).
UNCERTAIN_WAITS: tuple[float, ...] = (15, 30, 60)

# What an adapter's ``classify`` may say about a failed attempt.
NOT_SENT = "not_sent"          # the connection never opened: resend freely, not billed
RATE_LIMITED = "rate_limited"  # refused before processing (429): resend after a wait, not billed
UNCERTAIN = "uncertain"        # timed out, a server error or an unreadable answer: may have been processed
LOST = "lost"                  # the connection broke after sending: may have been processed, resent like UNCERTAIN
REJECTED = "rejected"          # refused before processing: fail, not billed
PROMPT_FLAGGED = "prompt_flagged"  # the provider's safety filter refused the prompt: a refusal at no cost
FAILED = "failed"              # anything else: fail, usage unknown


def is_malformed_response(exc: BaseException, validation_error: type[BaseException]) -> bool:
    """Whether ``exc``, or its ``__cause__``, says the provider's answer could not be read.

    The SDKs raise ``json.JSONDecodeError`` on a body that is not JSON and their
    ``APIResponseValidationError`` (``validation_error``) on one that does not fit the
    expected shape. The request reached the provider, so it may have been processed
    (October 20, 2026: an unreadable OpenRouter body ended a PC1 calibration run)."""
    kinds = (json.JSONDecodeError, validation_error)
    return isinstance(exc, kinds) or isinstance(exc.__cause__, kinds)


async def invoke_under_policy(create, classify, label: str, *, transport_waits,
                              uncertain_waits=UNCERTAIN_WAITS, deadline_s: float | None = None,
                              on_deadline=None, refusal_payload=None) -> RawProviderResponse:
    """Make one provider request under the shared call policy.

    ``create()`` is the synchronous SDK call on a client built with ``max_retries=0``.
    ``classify(exc)`` returns ``(kind, status)`` with ``kind`` one of the constants above;
    provider exception types stay in the adapter. A call still open after ``deadline_s``
    is abandoned (``on_deadline`` closes its connection) and treated as a timeout, since
    a client timeout bounds each wait for data, not the call (PC1, October 16, 2026).
    Each retry record carries ``usage`` ("none" or "unknown") so the trace shows which
    resends may have been billed. A prompt the provider's safety filter refused
    (``PROMPT_FLAGGED``) is returned as ``refusal_payload()``, marked ``refused_prompt``, so the
    agent loop counts and bounds it as a refusal; without a ``refusal_payload`` it fails
    unbilled."""
    import asyncio

    retries: list[dict] = []
    free, uncertain = list(transport_waits), list(uncertain_waits)
    attempt = 0
    while True:
        attempt += 1
        try:
            if deadline_s is None:
                resp = await asyncio.to_thread(create)
            else:
                resp = await asyncio.wait_for(asyncio.to_thread(create), deadline_s)
        except asyncio.TimeoutError as exc:
            if on_deadline is not None:
                try:
                    on_deadline()
                except Exception:  # noqa: BLE001 — closing an abandoned connection must not end the call
                    pass
            kind, status, error = UNCERTAIN, "deadline", f"call open after {deadline_s:.0f} s, abandoned"
            cause = exc
        except Exception as exc:  # noqa: BLE001 — normalize all provider/transport errors
            kind, status = classify(exc)
            error, cause = f"{type(exc).__name__}: {exc}"[:500], exc
        else:
            if hasattr(resp, "model_dump"):
                return RawProviderResponse(payload=resp.model_dump(), transport_retries=retries)
            # The OpenAI client returns a body labeled as something other than JSON as plain
            # text instead of raising; it reached the provider, so it is sorted as malformed.
            cause = ValueError(f"answer is {type(resp).__name__}, not a response object: {str(resp)[:200]!r}")
            kind, status, error = UNCERTAIN, "malformed", f"{type(cause).__name__}: {cause}"[:500]

        if kind in (NOT_SENT, RATE_LIMITED) and free:
            wait = free.pop(0)
            retries.append({"attempt": attempt, "error": error, "status": status, "usage": "none", "waited_s": wait})
            await asyncio.sleep(wait)
            continue
        if kind == PROMPT_FLAGGED and refusal_payload is not None:
            return RawProviderResponse(payload={**refusal_payload(), "refused_prompt": True, "status_code": status,
                                                "provider_message": str(cause)[:1000]}, transport_retries=retries)
        if kind in (UNCERTAIN, LOST) and uncertain:
            wait = uncertain.pop(0)
            retries.append({"attempt": attempt, "error": error,
                            "status": "connection_lost" if kind == LOST else status,
                            "usage": "unknown", "waited_s": wait})
            await asyncio.sleep(wait)
            continue
        if kind == NOT_SENT:
            note, not_billed = f"connection could not open on {attempt} attempts", True
        elif kind in (RATE_LIMITED, REJECTED, PROMPT_FLAGGED):
            note, not_billed = f"refused before processing on attempt {attempt}", True
        elif kind in (UNCERTAIN, LOST):
            note, not_billed = (f"usage unknown; no answer, a lost connection, a server error or an unreadable "
                                f"answer on {attempt} attempts"), False
        else:
            note, not_billed = "usage unknown", False
        raise ProviderError(f"{label} failed: {cause} ({note})",
                            not_billed=not_billed, transport_retries=retries) from cause


@dataclass
class ModelBackendCapabilities:
    reasoning_kind: str = "none"  # none | thinking | summary
    context_window: int = 200_000
    supports_tools: bool = True
    provider_seed_support: bool = False
    prompt_cache_support: bool = False
    satisfiable_exposures: frozenset[str] = field(default_factory=frozenset)
    # Tool-result visibility modes the adapter can actually produce (M3 §2.1). A
    # contract requesting a mode not listed here is unsatisfiable (refused in
    # confirmatory, stamped exposure_confounded otherwise) — never silently "full".
    tool_result_visibility_modes: frozenset[str] = field(
        default_factory=lambda: frozenset({"full"})
    )


@dataclass
class RawProviderResponse:
    """The provider response dictionary retained before conversion to shared response fields."""

    payload: dict[str, Any]
    # failed attempts the adapter resent before this response arrived, oldest first:
    # [{"attempt", "error", "status", "usage", "waited_s"}]; the gateway records each as
    # model.transport_retry. ``usage`` is "unknown" for an attempt that may have been billed.
    transport_retries: list[dict] = field(default_factory=list)


class ProviderAdapter(Protocol):
    provider_id: str
    capabilities: ModelBackendCapabilities

    def translate(self, req: ModelRequest) -> Any: ...

    async def invoke(self, payload: Any) -> RawProviderResponse: ...

    def normalize(self, raw: RawProviderResponse, req: ModelRequest, raw_ref: str) -> ModelResponse: ...

    def satisfiable_exposures(self) -> set[str]: ...

    def estimate_tokens(self, messages: list[NeutralMessage], tools: list[ToolSpec]) -> int: ...
