"""Declare outcome requirements, accept commitments, and classify assistance.

OutcomeContract defines when work is complete. OutcomeCoordinator.commit writes
accepted StateCommitment records through the host-controlled submission path.
The assistance label follows recorded contributing interventions; task scoring is
performed through evaluation/ and registered task scorers."""

from oaos2.outcomes.contracts import (
    ClosureCondition,
    ClosureKind,
    Commitment,
    InvalidContract,
    OutcomeContract,
    closure_met,
)
from oaos2.outcomes.commit import OutcomeCoordinator
from oaos2.outcomes.label import label_outcome

__all__ = [
    "ClosureCondition",
    "ClosureKind",
    "Commitment",
    "InvalidContract",
    "OutcomeContract",
    "OutcomeCoordinator",
    "closure_met",
    "label_outcome",
]
