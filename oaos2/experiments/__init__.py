"""Load experiment recipes, execute repeated conditions, and check comparisons.

The runner combines task packs, organizations, models, and declared resource
limits. Pre-run confirmatory checks, result-level confound checks, and provider
comparison probes answer different questions. None grants spending permission."""

from oaos2.experiments.design import ExperimentDesign, ParityPolicy
from oaos2.experiments.designs.first_experiment import first_experiment_design
from oaos2.experiments.parity import (
    TraceRun,
    behavioral_equivalence,
    run_conformance_trace,
)
from oaos2.experiments.runner import (
    CellResult,
    SweepResult,
    run_one,
    run_paper_replication_live,
    run_sweep,
)
# Org structure + validity gates now live under organizations/ (DESIGN §23); re-exported
# here for convenience since the experiment runner composes them.
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
from oaos2.organizations.spec import OrganizationSpec, Role

__all__ = [
    "ALL_PRESETS",
    "CellResult",
    "ConfoundViolation",
    "ExperimentDesign",
    "OrganizationSpec",
    "ParityPolicy",
    "Role",
    "SweepResult",
    "TraceRun",
    "behavioral_equivalence",
    "confound_check",
    "context_expanded_single_agent",
    "first_experiment_design",
    "pipeline",
    "role_blind_ensemble",
    "run_conformance_trace",
    "run_one",
    "run_paper_replication_live",
    "run_sweep",
    "single_agent",
    "single_agent_capacity_check",
]
