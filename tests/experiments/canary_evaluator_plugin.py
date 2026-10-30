"""A NOVEL evaluator registered entirely OUTSIDE core — the open-registry canary.

The task manifest names this module via ``evaluator_modules``; importing it
registers the id with the open evaluator registry (``tasks/registry.py``), so a
new scoring family is a manifest line + this plugin — zero core diff (the
``submission_gates`` pattern, applied to evaluators)."""

from __future__ import annotations

from oaos2.evaluation.foundation_schema import FieldSchema, SchemaEvaluator
from oaos2.tasks.registry import register_evaluator


def build_canary_evaluator(spec: dict):
    return SchemaEvaluator("canary.score", FieldSchema(
        required=list(spec.get("required", [])), types={}))


register_evaluator("canary.score", build_canary_evaluator)
