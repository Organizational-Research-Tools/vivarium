"""Common request, response, tool, and usage data types for model calls.

The agent loop and pricing code use these dataclasses instead of provider-specific
objects. Adapters translate formats. The gateway records model.invoked,
model.responded, and cost.recorded events with links to retained response data;
these in-memory types are distinct from archive record schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# --- messages / blocks ----------------------------------------------------- #


class BlockKind(str, Enum):
    TEXT = "text"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    THINKING = "thinking"  # exposed only where capability-gated (M3 §2.1)


@dataclass
class NeutralBlock:
    """One content block. ``provider_opaque`` is a blind passthrough (M3 §1).

    Some provider artifacts (notably Anthropic signed ``thinking`` blocks) must be
    echoed back *verbatim* on the next request or the conversation breaks. The
    loop never inspects ``provider_opaque``; the adapter re-emits it untouched
    when re-serializing history. (Distinct from ``raw_provider_response_ref``,
    which is the whole-payload forensic ref — different jobs.)
    """

    kind: str
    text: str = ""
    tool_name: str | None = None
    tool_call_id: str | None = None
    arguments: dict | None = None
    provider_opaque: dict | None = None  # carried back blindly; never inspected


@dataclass
class NeutralMessage:
    role: str  # system | user | assistant | tool
    blocks: list[NeutralBlock] = field(default_factory=list)


@dataclass
class ToolSpec:
    """Neutral tool spec; the adapter renders it to each provider's schema dialect."""

    name: str
    description: str
    parameters_schema: dict = field(default_factory=dict)  # JSON-schema (neutral)


@dataclass
class SamplingParams:
    temperature: float = 1.0
    top_p: float | None = None
    max_output_tokens: int = 1024
    stop: list[str] = field(default_factory=list)
    platform_seed: int | None = None


class ReasoningKind(str, Enum):
    NONE = "none"
    THINKING = "thinking"  # raw signed reasoning (Anthropic)
    SUMMARY = "summary"  # reasoning summaries only (OpenAI)


@dataclass
class ReasoningRequest:
    kind: str = ReasoningKind.NONE.value
    budget_tokens: int | None = None


@dataclass
class CachePolicy:
    """Cache-breakpoint placement. PINNED into the manifest hash + a confound gate
    (M3 §3.1): differing placement changes cache hit rate → realized usd → silently
    breaks usd-basis parity."""

    breakpoints: list[str] = field(default_factory=list)  # prefix markers marked cacheable
    # Per-breakpoint lifetime override ("1h"; provider default 5m). Longer-lived entries
    # must PRECEDE shorter-lived ones in prompt order (provider constraint), so overrides
    # belong on static-prefix markers, never the rolling tail. Cost-bearing like placement
    # (write premium 2x vs 1.25x; cross-cell reads at 0.1x) → part of the fingerprint.
    ttl_overrides: dict[str, str] = field(default_factory=dict)

    def fingerprint(self) -> str:
        import hashlib
        import json

        # Overrides fold in only when present, so pre-TTL policies keep the fingerprints
        # already pinned in archived manifests.
        spec = [self.breakpoints, self.ttl_overrides] if self.ttl_overrides else self.breakpoints
        return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()


# --- request --------------------------------------------------------------- #


@dataclass
class ModelRequest:
    call_id: str  # ULID; becomes model_call_id on every event
    model_ref: str  # e.g. "anthropic/claude-opus-4-8" (pinned snapshot, §19)
    messages: list[NeutralMessage]
    tools: list[ToolSpec] = field(default_factory=list)
    sampling: SamplingParams = field(default_factory=SamplingParams)
    reasoning: ReasoningRequest = field(default_factory=ReasoningRequest)
    cache: CachePolicy = field(default_factory=CachePolicy)


# --- response -------------------------------------------------------------- #


@dataclass
class TokenSplit:
    input: int = 0
    output: int = 0
    cache_read: int | None = None
    cache_write: int | None = None
    reasoning: int | None = None
    # All input, including cache reads and writes, repriced at the full input rate.
    # basis (M3 §3.1). None on providers that don't report the split.
    input_uncached_equiv: int | None = None
    cache_write_by_ttl: dict[str, int] | None = None  # reported writes by lifetime

    def as_dict(self) -> dict:
        return {
            "input": self.input,
            "output": self.output,
            "cache_read": self.cache_read,
            "cache_write": self.cache_write,
            "reasoning": self.reasoning,
            "input_uncached_equiv": self.input_uncached_equiv,
            **({"cache_write_by_ttl": self.cache_write_by_ttl}
               if self.cache_write_by_ttl is not None else {}),
        }


@dataclass
class RealizedReasoning:
    kind: str = ReasoningKind.NONE.value
    requested_budget: int | None = None
    realized_tokens: int | None = None


@dataclass
class ExposureRealized:
    """What ACTUALLY reached the loop (recorded on model.responded, M3 §2.1)."""

    thinking_trace_to_agent: bool = False
    reasoning_tokens_to_agent: bool = False
    tool_result_visibility: str = "full"
    scratchpad_persistence: bool = False
    exposure_confounded: bool = False  # stamped in pilot/calibration crossed cells

    def as_dict(self) -> dict:
        return {
            "thinking_trace_to_agent": self.thinking_trace_to_agent,
            "reasoning_tokens_to_agent": self.reasoning_tokens_to_agent,
            "tool_result_visibility": self.tool_result_visibility,
            "scratchpad_persistence": self.scratchpad_persistence,
            "exposure_confounded": self.exposure_confounded,
        }


# Closed normalized stop-reason set (M3 §2 divergence table).
class StopReason(str, Enum):
    END_TURN = "end_turn"
    TOOL_USE = "tool_use"
    MAX_TOKENS = "max_tokens"
    STOP_SEQUENCE = "stop_sequence"
    REFUSAL = "refusal"
    ERROR = "error"


STOP_REASONS: frozenset[str] = frozenset(s.value for s in StopReason)


@dataclass
class ModelResponse:
    model_call_id: str
    model_ref: str
    stop_reason: str  # one of STOP_REASONS (closed set)
    content_blocks: list[NeutralBlock] = field(default_factory=list)
    usage: TokenSplit = field(default_factory=TokenSplit)
    realized_reasoning: RealizedReasoning = field(default_factory=RealizedReasoning)
    realized_exposure: ExposureRealized = field(default_factory=ExposureRealized)
    latency_ms: int = 0
    raw_provider_response_ref: str = ""  # ref to verbatim payload (raw/<hash>)
    cost_usd: float = 0.0  # filled by the cost core, not the adapter
    response_event_id: str | None = None  # host trace event used by the next action
