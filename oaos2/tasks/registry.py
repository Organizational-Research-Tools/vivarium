"""Resolve evaluator IDs from task manifests to registered builder functions.

Configuration selects and parameterizes a scorer; its domain logic lives in a
task plugin. Unknown IDs are refused. A task can reuse existing scorers and
register new ones through the common interface without adding task-name branches
to the experiment runner."""

from __future__ import annotations

from typing import Callable

from oaos2.evaluation.foundation_schema import FieldSchema, SchemaEvaluator
from oaos2.tasks.plugins.paper_replication.numeric_compare import NumericCompareEvaluator


def _build_numeric_compare(spec: dict):
    # `scoring`: "best_of" (lenient multi-path) | "primary_only" (confirmatory/tight).
    return NumericCompareEvaluator(scoring_profile=spec.get("scoring", "best_of"))


def _build_schema(spec: dict):
    return SchemaEvaluator(
        spec.get("ref", "schema_validator"),
        FieldSchema(required=list(spec.get("required", [])), types=dict(spec.get("types", {}))),
    )


# id → builder(spec: dict) -> Evaluator. FOUNDATION entries only (the generic
# schema validator + the calibrated foundation pack): every DOMAIN pack
# registers its own ids from its plugin evaluator module via
# register_evaluator, imported through the manifest's `evaluator_modules:`
# list (probe 2026-08-17 — core enumerates no domain scoring vocabulary).
EVALUATOR_BUILDERS: dict[str, Callable[[dict], object]] = {
    "schema_validator": _build_schema,
    "paper_replication.numeric_compare": _build_numeric_compare,
}

# The ids core itself ships — a manifest referencing anything beyond these must
# declare the plugin module that registers it (registration is process-global,
# so the DECLARATION, not prior-import luck, is the correctness requirement).
FOUNDATION_EVALUATORS: frozenset[str] = frozenset(EVALUATOR_BUILDERS)


# id → the module that registered it (probe round 2, 2026-08-17): the loader
# verifies a manifest's non-foundation ids were registered BY a module that
# manifest itself declares — presence in the process-global dict is never
# provenance, so declaring an unrelated module cannot launder a prior import.
EVALUATOR_PROVENANCE: dict[str, str] = {ref: __name__ for ref in EVALUATOR_BUILDERS}


def register_evaluator(ref: str, builder: Callable[[dict], object]) -> None:
    """Register an evaluator builder under its manifest id (open registry).

    The coordination-registry rule applied to evaluators: idempotent for the
    same builder (plugin modules import repeatedly per sweep), refuses a
    CONFLICTING re-registration — two plugins may not fight over one id.
    Provenance (the builder's defining module) is recorded so loaders can
    verify declaration, not prior-import luck."""
    if not ref:
        raise ValueError("evaluator id must be non-empty")
    existing = EVALUATOR_BUILDERS.get(ref)
    if existing is not None and existing is not builder:
        raise ValueError(f"evaluator id {ref!r} is already registered")
    EVALUATOR_BUILDERS[ref] = builder
    EVALUATOR_PROVENANCE[ref] = getattr(builder, "__module__", "") or ""


class UnknownEvaluator(KeyError):
    """A manifest referenced an evaluator id with no registered plugin."""


def build_evaluator(ref: str, spec: dict | None = None):
    """Resolve an evaluator id (+ its declarative config) to a code plugin instance."""
    try:
        builder = EVALUATOR_BUILDERS[ref]
    except KeyError:
        raise UnknownEvaluator(
            f"no evaluator plugin registered for {ref!r}; register it via "
            "register_evaluator in a plugin module the manifest names in "
            "`evaluator_modules:` (a new task family adds only that module)"
        ) from None
    return builder({"ref": ref, **(spec or {})})
