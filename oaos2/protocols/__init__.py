"""Describe work transfers, reporting formats, and extraction markers.

CoordinationContract specifies senders, recipients, and completion conditions.
HandoffFormatSpec describes the transferred payload. MarkerPolicy describes
text markers for an optional extraction helper. These declarations are separate
from the runtime procedures in experiments/coordination/. Check the caller
before treating a declared field as an enforced behavior."""

from oaos2.protocols.coordination import (
    AggregationContract,
    ContractShape,
    CoordinationContract,
    HandoffContract,
    HandoffFormatSpec,
)
from oaos2.protocols.markers import MarkerExtraction, MarkerPolicy, extract_handoff

__all__ = [
    "AggregationContract",
    "ContractShape",
    "CoordinationContract",
    "HandoffContract",
    "HandoffFormatSpec",
    "MarkerExtraction",
    "MarkerPolicy",
    "extract_handoff",
]
