"""Cost attribution (M3 §3.1, DESIGN §15).

Per-``model.invoked`` attribution against the single pricing table, with an
**open** activity-class registry mapped to a **closed** cost super-class set
(``work | overhead | treatment``) so analysis keeps stable categories without a
frozen vocabulary (DESIGN §5.2). ``cost_if_no_cache_usd`` is nullable — populated
only when the provider reports cached-token counts (never fabricated).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from oaos2.models.types import ModelResponse, TokenSplit
from oaos2.pricing.table import PricingTable
from oaos2.registry import Registry, RegistrySpec


class SuperClass(str, Enum):
    WORK = "work"
    OVERHEAD = "overhead"
    TREATMENT = "treatment"


# Open activity-class registry → closed super-class (DESIGN §15, M3 §3.1). Packs
# extend via inherits_from; core never enumerates the vocabulary inline.
_FOUNDATION_ACTIVITY_CLASSES: dict[str, str] = {
    "work_modeling": SuperClass.WORK.value,
    "coordination_aggregation": SuperClass.WORK.value,
    "informal_coordination": SuperClass.WORK.value,
    "compaction": SuperClass.OVERHEAD.value,
    "retry_after_validation": SuperClass.OVERHEAD.value,
    "culture_context_load": SuperClass.OVERHEAD.value,
    "evaluator_plugin": SuperClass.OVERHEAD.value,
}

ACTIVITY_CLASS_SPEC: RegistrySpec[str] = RegistrySpec(
    registry_id="oaos2.foundation.activity_classes",
    entries=_FOUNDATION_ACTIVITY_CLASSES,
)
ACTIVITY_CLASS_REGISTRY: Registry[str] = ACTIVITY_CLASS_SPEC.resolve()


def super_class_for(activity_class: str, registry: Registry[str] = ACTIVITY_CLASS_REGISTRY) -> str:
    """Map an activity class to its closed cost super-class (validated against the registry)."""
    return registry[activity_class]


@dataclass
class CostRecord:
    model_call_id: str
    cost_usd: float
    token_split: TokenSplit
    cache_hit: bool
    pricing_version: str
    activity_class: str
    cost_super_class: str
    cost_if_no_cache_usd: float | None = None
    extensions: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "model_call_id": self.model_call_id,
            "cost_usd": self.cost_usd,
            "token_split": self.token_split.as_dict(),
            "cache_hit": self.cache_hit,
            "pricing_version": self.pricing_version,
            "activity_class": self.activity_class,
            "cost_super_class": self.cost_super_class,
            "cost_if_no_cache_usd": self.cost_if_no_cache_usd,
        }


def attribute_cost(
    resp: ModelResponse,
    table: PricingTable,
    activity_class: str,
    activity_registry: Registry[str] = ACTIVITY_CLASS_REGISTRY,
) -> CostRecord:
    """Compute the cost of one model response (M3 §3.1). The sole cost computation."""
    u = resp.usage
    row = table.price(resp.model_ref).for_prompt(
        int(u.input or 0) + int(u.cache_read or 0) + int(u.cache_write or 0))
    write_cost = (u.cache_write or 0) * row.cache_write
    if u.cache_write_by_ttl is not None:
        if sum(u.cache_write_by_ttl.values()) != (u.cache_write or 0):
            raise ValueError("cache-write lifetime counts do not match total writes")
        write_cost = sum(count * row.cache_write_by_ttl[ttl]
                         for ttl, count in u.cache_write_by_ttl.items() if count)
    cost = (
        u.input * row.input
        + u.output * row.output
        + (u.cache_read or 0) * row.cache_read
        + write_cost
    ) / 1e6
    if u.input_uncached_equiv is None:
        cost_if_no_cache = None  # provider didn't report the split — never fabricate
    else:
        cost_if_no_cache = (u.input_uncached_equiv * row.input + u.output * row.output) / 1e6
    return CostRecord(
        model_call_id=resp.model_call_id,
        cost_usd=cost,
        token_split=u,
        cache_hit=(u.cache_read or 0) > 0,
        pricing_version=table.version,
        activity_class=activity_class,
        cost_super_class=super_class_for(activity_class, activity_registry),
        cost_if_no_cache_usd=cost_if_no_cache,
    )
