"""Score submitted work and keep public feedback separate from diagnostics.

The built-in kinds are schema, for required structure, and plugin, for task
scoring through the common interface. write_evaluation checks permitted public
field names, string lengths, and forbidden text. It does not enforce feedback
value types or guarantee that approved fields reveal no private information.
Task authors must review the feedback contract and meaning."""

from oaos2.evaluation.foundation_schema import SchemaEvaluator, schema_validate
from oaos2.evaluation.plugin_interface import Evaluator, EvaluatorInputRef, RawEvaluation
from oaos2.evaluation.public_feedback import (
    EvaluationRejected,
    PublicFeedbackSchema,
    write_evaluation,
)
from oaos2.evaluation.registry import EVALUATOR_KIND_REGISTRY

__all__ = [
    "EVALUATOR_KIND_REGISTRY",
    "EvaluationRejected",
    "Evaluator",
    "EvaluatorInputRef",
    "PublicFeedbackSchema",
    "RawEvaluation",
    "SchemaEvaluator",
    "schema_validate",
    "write_evaluation",
]
