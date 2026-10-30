"""Organization settings, permissions, and scheduling policies.

Organization files specify roles, communication paths, rights, and how ready
agents are admitted to work. Policies return admitted agent IDs from a state
snapshot. The concurrent runtime applies that decision and dependency overrides;
clocked_rounds additionally enforces experiment-defined work periods."""

from oaos2.organizations.confound_check import (
    ConfoundViolation,
    confound_check,
    single_agent_capacity_check,
)
from oaos2.organizations.presets import (
    ALL_PRESETS,
    context_expanded_single_agent,
    pipeline,
    role_blind_ensemble,
    single_agent,
)
from oaos2.organizations.scheduler import (
    SCHEDULER_POLICIES,
    SchedulerPolicy,
    free_policy,
    manager_dispatch_policy,
    round_robin_policy,
    sequential_policy,
)
from oaos2.organizations.spec import OrganizationSpec, Role

__all__ = [
    "ALL_PRESETS",
    "ConfoundViolation",
    "OrganizationSpec",
    "Role",
    "SCHEDULER_POLICIES",
    "SchedulerPolicy",
    "confound_check",
    "context_expanded_single_agent",
    "free_policy",
    "manager_dispatch_policy",
    "pipeline",
    "role_blind_ensemble",
    "round_robin_policy",
    "sequential_policy",
    "single_agent",
    "single_agent_capacity_check",
]
