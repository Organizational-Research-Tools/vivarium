"""Register and select procedures for coordinating work among roles.

Importing this package registers common staged, pipeline, and default procedures.
Task-specific procedures register when the declared protocol_module is imported.
The runner uses the interface exported here, rather than branching on task names."""

from oaos2.experiments.coordination.base import (
    CoordinationContext,
    CoordinationProtocol,
    RoleHooks,
    is_structurally_decomposed,
    make_inbound_handler,
    register_coordination_protocol,
    resolve_coordination_protocol,
    role_commitment_seq,
    stub_missing,
)
from oaos2.experiments.coordination.default import SingleSubmissionProtocol
from oaos2.experiments.coordination.pipeline import PipelineProtocol
from oaos2.experiments.coordination.staged import StagedCollectiveProtocol

# The budget archetypes (deliberative / hierarchical) are TASK plugins now
# (probe 2026-08-17): awards, amendment rotations, and the audit ask are budget
# semantics, so they live in oaos2/tasks/plugins/budget_allocation/coordination.py
# and register when a budget preset's declared ``protocol_module`` is imported.

__all__ = [
    "CoordinationContext",
    "CoordinationProtocol",
    "PipelineProtocol",
    "RoleHooks",
    "SingleSubmissionProtocol",
    "StagedCollectiveProtocol",
    "is_structurally_decomposed",
    "make_inbound_handler",
    "register_coordination_protocol",
    "resolve_coordination_protocol",
    "role_commitment_seq",
    "stub_missing",
]
