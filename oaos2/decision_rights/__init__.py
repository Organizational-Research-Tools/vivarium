"""Declare role permissions and validate their registered names.

Runtime callers enforce may_submit_milestones and may_accept_handoffs_from.
review_authority_over is validated and recorded metadata; no current action
checks it to permit a review, override, or veto. A registry accepts additional
names, but callers must implement their meaning and enforcement. Registering
a right alone does not make it an effective experimental control."""

from oaos2.decision_rights.registry import (
    COLLABORATION_DEFAULT_RIGHTS,
    DecisionRights,
    DecisionRightsRegistry,
    UnknownDecisionRight,
)

__all__ = [
    "COLLABORATION_DEFAULT_RIGHTS",
    "DecisionRights",
    "DecisionRightsRegistry",
    "UnknownDecisionRight",
]
