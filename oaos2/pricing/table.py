"""The recorded price table used to calculate run costs.

Prices are USD per million input, output, cache-read, or cache-write tokens.
The manifest records its version and content hash. These are configured study
prices, not an automatically refreshed statement of provider pricing. Comparisons
must check the relevant versions and report missing pricing information."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class PriceRow:
    input: float  # USD per Mtok
    output: float
    cache_read: float = 0.0
    cache_write: float = 0.0
    cache_write_by_ttl: dict[str, float] = field(default_factory=dict)
    # Prices by prompt length (Claude Haiku 5.5, October 2026): a request whose prompt (input,
    # cache reads and cache writes together) exceeds ``long_prompt_tokens`` is priced at
    # ``long_prompt``. Unset on every other row, and left out of the table hash when unset,
    # so the hashes of earlier tables do not change.
    long_prompt_tokens: int | None = None
    long_prompt: "PriceRow | None" = None

    def for_prompt(self, prompt_tokens: int) -> "PriceRow":
        if self.long_prompt is not None and self.long_prompt_tokens is not None \
                and prompt_tokens > self.long_prompt_tokens:
            return self.long_prompt
        return self

    def hash_view(self) -> dict:
        d = asdict(self)
        for k in ("long_prompt_tokens", "long_prompt"):
            if d.get(k) is None:
                d.pop(k, None)
        return d


@dataclass(frozen=True)
class PricingTable:
    version: str  # e.g. "2026-06-01"; its HASH enters manifest.json
    rows: dict[str, PriceRow] = field(default_factory=dict)

    def price(self, model_ref: str) -> PriceRow:
        try:
            return self.rows[model_ref]
        except KeyError:
            raise KeyError(
                f"no pricing row for {model_ref!r} in table {self.version!r}"
            ) from None

    def hash(self) -> str:
        payload = {"version": self.version, "rows": {k: v.hash_view() for k, v in sorted(self.rows.items())}}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def foundation_pricing_table() -> PricingTable:
    """A pinned baseline table. The deterministic stub model is priced at zero so a
    domain-empty run records ~$0 (well under the $0.01 cost gate, §22); real models
    carry representative rates. Real runs pin their own table; this is the default."""
    return PricingTable(
        version="2026-09-10",  # lifetime-specific cache-write accounting
        rows={
            # The deterministic stub model — zero cost (bootstrap/CI baseline).
            "stub/deterministic": PriceRow(input=0.0, output=0.0),
            # Published list rates (USD/Mtok, checked 2026-07-06); pinned per run in practice.
            # Anthropic: cache_read = 0.1x input, cache_write = 1.25x input (5-min TTL).
            "anthropic/claude-opus-4-8": PriceRow(input=5.0, output=25.0, cache_read=0.5, cache_write=6.25,
                                               cache_write_by_ttl={"5m": 6.25, "1h": 10.0}),
            "anthropic/claude-sonnet-4-6": PriceRow(input=3.0, output=15.0, cache_read=0.3, cache_write=3.75,
                                                 cache_write_by_ttl={"5m": 3.75, "1h": 6.0}),
            "anthropic/claude-haiku-4-5": PriceRow(input=1.0, output=5.0, cache_read=0.1, cache_write=1.25,
                                                cache_write_by_ttl={"5m": 1.25, "1h": 2.0}),
            # OpenAI auto-caches (no separately billed writes); cached input bills at 0.1x.
            # A zero cache_read would silently under-bill the tokens the adapter nets out
            # of `input` (see adapters/openai.py docstring) — breaking usd-basis parity.
            "openai/gpt-5": PriceRow(input=1.25, output=10.0, cache_read=0.125),
        },
    )


def pricing_table_2026_10_03() -> PricingTable:
    """The foundation rows plus Claude Sonnet 5.5 (list rates checked 2026-10-03 in the
    provider's model guide; 5-minute cache writes 1.25x input, 1-hour 2x). A separate
    version, not an edit of the foundation table: studies already running on that table
    keep one pricing identity across their cells, which the confound check requires."""
    base = foundation_pricing_table()
    return PricingTable(version="2026-10-03", rows={
        **base.rows,
        "anthropic/claude-sonnet-5-5": PriceRow(input=2.0, output=10.0, cache_read=0.2, cache_write=2.5,
                                             cache_write_by_ttl={"5m": 2.5, "1h": 4.0}),
    })


def pricing_table_2026_10_10() -> PricingTable:
    """The 2026-10-03 rows plus Claude Haiku 5.5, and Claude Sonnet 5.5's cache reads
    corrected (list rates checked 2026-10-10 on the provider's pricing page).

    - Haiku 5.5 is priced by prompt length: up to 100,000 tokens, $0.10 input, $0.50 output,
      $0.01 cache reads, $0.125 / $0.20 cache writes (5 minutes / 1 hour); above, five times
      each.
    - Sonnet 5.5's cache reads are 0.05x input ($0.10), not the standard 0.1x the
      2026-10-03 table assumed ($0.20). That table stays as it was, because runs already
      priced on it keep one pricing identity; it overstates their cache-read cost.
    """
    base = pricing_table_2026_10_03()
    long = PriceRow(input=0.50, output=2.50, cache_read=0.05, cache_write=0.625,
                    cache_write_by_ttl={"5m": 0.625, "1h": 1.0})
    return PricingTable(version="2026-10-10", rows={
        **base.rows,
        "anthropic/claude-sonnet-5-5": PriceRow(input=2.0, output=10.0, cache_read=0.1, cache_write=2.5,
                                             cache_write_by_ttl={"5m": 2.5, "1h": 4.0}),
        "anthropic/claude-haiku-5-5": PriceRow(input=0.10, output=0.50, cache_read=0.01, cache_write=0.125,
                                            cache_write_by_ttl={"5m": 0.125, "1h": 0.20},
                                            long_prompt_tokens=100_000, long_prompt=long),
    })


def pricing_table_2026_10_12() -> PricingTable:
    """The 2026-10-10 rows plus the models PC1 tries the supplier-g configuration on (October 12, 2026): OpenAI list
    rates (developers.openai.com/api/docs/pricing, standard tier, prompts up to 272K tokens, read October 12) and
    Together's serverless rates for two open-weight models (its models listing, read October 12; no cached-input
    rate). Rates checked on that day only; a later run checks them again."""
    base = pricing_table_2026_10_10()
    return PricingTable(version="2026-10-12", rows={
        **base.rows,
        "openai/gpt-6-luna": PriceRow(input=0.10, output=0.50, cache_read=0.01),
        "openai/gpt-5-mini": PriceRow(input=0.25, output=2.00, cache_read=0.025),
        # the same models through the Responses API (adapter namespace `openai_responses`), at the same rates
        "openai_responses/gpt-6-luna": PriceRow(input=0.10, output=0.50, cache_read=0.01),
        "openai_responses/gpt-5-mini": PriceRow(input=0.25, output=2.00, cache_read=0.025),
        "together/openai/gpt-oss-120b": PriceRow(input=0.15, output=0.60),
        "together/deepseek-ai/DeepSeek-V4-Flash-0731": PriceRow(input=0.14, output=0.28),
        "together/zai-org/GLM-5.3-Flash": PriceRow(input=0.15, output=0.50),
    })


def pricing_table_2026_10_13() -> PricingTable:
    """The 2026-10-12 rows plus GLM-5.3-Flash through OpenRouter (October 13, 2026): OpenRouter's endpoint listing for
    `z-ai/glm-5.3-flash`, read that day, names one host, Z.AI, at $0.37 input and $1.25 output per million tokens, no
    cached-input rate. Rows with and without the host pinned (`@z-ai`); the adapter reads the pin, the ledger the ref."""
    base = pricing_table_2026_10_12()
    glm = PriceRow(input=0.37, output=1.25)
    return PricingTable(version="2026-10-13", rows={
        **base.rows,
        "openrouter/z-ai/glm-5.3-flash": glm,
        "openrouter/z-ai/glm-5.3-flash@z-ai": glm,
    })


def pricing_table_2026_10_15() -> PricingTable:
    """The 2026-10-13 rows plus the models of PC1's minimal model survey (October 15, 2026): OpenAI list rates
    (developers.openai.com model pages, read that day: gpt-5-nano $0.05/$0.40, cached $0.005; gpt-5.4-nano $0.20/$1.25,
    cached $0.02) and OpenRouter's model listings for the open-weight models (unpinned; a host's own rate may differ;
    no cached-input rate)."""
    base = pricing_table_2026_10_13()
    rows = {
        "openai_responses/gpt-5-nano": PriceRow(input=0.05, output=0.40, cache_read=0.005),
        "openai_responses/gpt-5.4-nano": PriceRow(input=0.20, output=1.25, cache_read=0.02),
        "openrouter/deepseek/deepseek-v4-flash": PriceRow(input=0.09, output=0.18),
        "openrouter/qwen/qwen3.8-flash": PriceRow(input=0.15, output=0.47),
        "openrouter/moonshotai/kimi-k2.6": PriceRow(input=0.65, output=3.41),
        "openrouter/minimax/minimax-m2.7": PriceRow(input=0.30, output=1.20),
        "openrouter/meta-llama/llama-4-maverick": PriceRow(input=0.19, output=0.65),
    }
    return PricingTable(version="2026-10-15", rows={**base.rows, **rows})


def pricing_table_2026_10_16() -> PricingTable:
    """The 2026-10-15 rows plus gpt-5.6-terra (October 16, 2026; PC1 decision probe): $2.00 input, $12.00 output, $0.20
    cached input, as third-party listings gave that day (OpenRouter's "GPT Terra Latest", pricepertoken); OpenAI's own
    page not read. The model id is from the OpenAI models list of that day."""
    base = pricing_table_2026_10_15()
    rows = {
        "openai_responses/gpt-5.6-terra": PriceRow(input=2.00, output=12.00, cache_read=0.20),
        # Open-weight candidates near Sonnet's level, each pinned to one host (OpenRouter's endpoint listing that day;
        # the model's own provider where it serves the model; DeepSeek has none, so two fp8 hosts at the same rate,
        # priced at the higher).
        "openrouter/deepseek/deepseek-v4-pro@baidu,streamlake": PriceRow(input=0.41, output=0.81, cache_read=0.034),
        "openrouter/xiaomi/mimo-v2.6-pro@xiaomi": PriceRow(input=0.43, output=0.87, cache_read=0.004),
        "openrouter/z-ai/glm-5.3@z-ai": PriceRow(input=1.40, output=4.40, cache_read=0.26),
        "openrouter/minimax/minimax-m3@minimax": PriceRow(input=0.30, output=1.20, cache_read=0.06),
        "openrouter/moonshotai/kimi-k3@together": PriceRow(input=3.00, output=15.00, cache_read=0.30),  # Moonshot's own endpoint refused the request shape
    }
    return PricingTable(version="2026-10-16", rows={**base.rows, **rows})


def pricing_table_2026_10_19() -> PricingTable:
    """The 2026-10-10 rows plus three inexpensive models for the G5 model check (list rates checked
    2026-10-19: OpenAI's for GPT-5-mini, OpenRouter's models listing for the other two). OpenAI and
    OpenRouter cache implicitly and bill no separate cache writes. OpenRouter routes to upstream
    providers whose rates can differ from the listing; the row records the listed rate."""
    base = pricing_table_2026_10_10()
    return PricingTable(version="2026-10-19", rows={
        **base.rows,
        "openai/gpt-5-mini": PriceRow(input=0.25, output=2.0, cache_read=0.025),
        "openrouter/qwen/qwen3.8-flash": PriceRow(input=0.15, output=0.47, cache_read=0.016),
        "openrouter/deepseek/deepseek-v4-pro": PriceRow(input=0.434304, output=0.868608, cache_read=0.036192),
    })
