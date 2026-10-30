"""Evaluator-kind registry (M6 §4, DESIGN §14).

The foundation ships exactly two evaluator *kinds* — ``schema`` and ``plugin`` —
as an open registry over the closed plugin-interface shape. Advanced evaluators
(``numeric``, ``simulation``, ``rubric``, ``manual``) are task-pack plugins that
register as ``plugin`` kind; no core enum grows when a task type is added.
"""

from __future__ import annotations

from oaos2.registry import Registry, RegistrySpec

_FOUNDATION_EVALUATOR_KINDS: dict[str, str] = {
    "schema": "domain-agnostic shape/required-field validation",
    "plugin": "delegates to a task-pack evaluator via the §5.3 contract",
}

EVALUATOR_KIND_SPEC: RegistrySpec[str] = RegistrySpec(
    registry_id="oaos2.foundation.evaluator_kinds", entries=_FOUNDATION_EVALUATOR_KINDS
)
EVALUATOR_KIND_REGISTRY: Registry[str] = EVALUATOR_KIND_SPEC.resolve()
