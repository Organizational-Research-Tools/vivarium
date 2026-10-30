"""Declare work-transfer shapes and reporting formats.

Contracts describe one or many senders and recipients. HandoffContract fixes
the shape to one_to_one and can restrict sender and recipient roles. It does
not check message kind in permits(). AggregationContract declares fields for
combining contributions but does not implement voting or auctions. Live group
discussion uses communication/conversation.py and coordination procedures."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ContractShape(str, Enum):
    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    MANY_TO_MANY = "many_to_many"


class HandoffFormatKind(str, Enum):
    RAW = "raw"
    STRUCTURED = "structured"
    SUMMARY = "summary"
    STRUCTURED_RATIONALE = "structured_rationale"


@dataclass
class HandoffFormatSpec:
    """How the payload is shaped (content shape only) — itself a treatment (§12.2)."""

    kind: str = HandoffFormatKind.STRUCTURED.value
    schema_ref: str | None = None
    rationale_fields: list[str] = field(default_factory=list)


@dataclass
class CoordinationContract:
    """The closed shape + optional aggregation rule. Profiles specialize it."""

    contract_id: str
    shape: str  # ContractShape
    senders: list[str] = field(default_factory=list)  # role ids
    recipients: list[str] = field(default_factory=list)
    required_fields: frozenset[str] = frozenset()
    aggregation_rule: str | None = None  # set for many_to_* aggregating contracts (Tier-C)
    closure_condition: str | None = None
    retry_policy: dict = field(default_factory=dict)


@dataclass
class HandoffContract(CoordinationContract):
    """The one_to_one stateless payload-transfer profile (Tier A, M6 §1)."""

    format: HandoffFormatSpec = field(default_factory=HandoffFormatSpec)

    def __post_init__(self) -> None:
        self.shape = ContractShape.ONE_TO_ONE.value

    def permits(self, from_role: str, to_role: str, kind: str) -> bool:
        sender_ok = (not self.senders) or from_role in self.senders
        recipient_ok = (not self.recipients) or to_role in self.recipients
        return sender_ok and recipient_ok


@dataclass
class AggregationContract(CoordinationContract):
    """A Tier-C aggregating many_to_* seam (vote / auction / deliberation).

    Schematized so the synthetic gate can instantiate one of each shape; the
    aggregation *logic* is a Tier-C plugin, not foundation code.
    """

    rounds: int | None = None  # auction-style round counter (filled when seam taken up)
    per_round_visibility: str | None = None
