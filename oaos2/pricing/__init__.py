"""Price model usage and track each run's shared budget.

PricingTable supplies the recorded prices; attribute_cost applies them to reported
usage. CostLedger tracks completed usage and reservations for calls in progress.
Offline stub calls cost zero. Activity names map to work, overhead, or treatment
categories so reports can distinguish why resources were used."""

from oaos2.pricing.table import PriceRow, PricingTable, foundation_pricing_table
from oaos2.pricing.attribution import (
    ACTIVITY_CLASS_REGISTRY,
    CostRecord,
    SuperClass,
    attribute_cost,
    super_class_for,
)
from oaos2.pricing.ledger import CostCapWouldBreach, CostLedger, TokenCapWouldBreach

__all__ = [
    "ACTIVITY_CLASS_REGISTRY",
    "CostCapWouldBreach", "TokenCapWouldBreach",
    "CostLedger",
    "CostRecord",
    "PriceRow",
    "PricingTable",
    "SuperClass",
    "attribute_cost",
    "foundation_pricing_table",
    "super_class_for",
]
