"""Convenience wrappers for loading named library experiment recipes.

Current recipes live in library/experiments/, not in this package. Study status
and launch requirements are documented in docs/experiments/README.md."""

from oaos2.experiments.designs.first_experiment import (
    FIRST_EXPERIMENT_ARMS,
    first_experiment_design,
)

__all__ = ["FIRST_EXPERIMENT_ARMS", "first_experiment_design"]
