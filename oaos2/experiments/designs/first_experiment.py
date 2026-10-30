"""Load the historical paper-replication design from the experiment library.

The recipe is library/experiments/first_experiment.yaml; its preregistration
records the original hypotheses, control arms, and analysis requirements. This
wrapper does not make that study current or authorize another execution."""

from __future__ import annotations

from oaos2.experiments.design import ExperimentDesign
from oaos2.experiments.loader import load_design

FIRST_EXPERIMENT_ARMS = [
    "single_agent",
    "pipeline",
    "role_blind_ensemble",
    "context_expanded_single_agent",
]
PREREGISTRATION_REF = "library/experiments/first_experiment_preregistration.md"
DESIGN_NAME = "first_experiment"


def first_experiment_design() -> ExperimentDesign:
    """Load the canonical first-experiment design from the library (M7)."""
    return load_design(DESIGN_NAME)
