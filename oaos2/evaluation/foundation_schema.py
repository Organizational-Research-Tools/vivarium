"""Check required payload fields and their declared types.

This deterministic validator supports submission checks and schema-only scoring.
It has no task answer key; passing it establishes the checked structure, not the
substantive correctness of the submitted work."""

from __future__ import annotations

from dataclasses import dataclass, field

from oaos2.evaluation.plugin_interface import EvaluatorInputRef, RawEvaluation

# A tiny schema dialect: {field_name: python_type | "any"}.
_TYPE_NAMES = {"str": str, "int": int, "float": (int, float), "bool": bool,
               "list": list, "dict": dict, "any": object}


@dataclass
class FieldSchema:
    required: list[str] = field(default_factory=list)
    types: dict[str, str] = field(default_factory=dict)  # field -> type name


def schema_validate(payload: dict, schema: FieldSchema) -> tuple[bool, list[str]]:
    """Return (ok, problems). Domain-agnostic shape/required/type check."""
    problems: list[str] = []
    for f in schema.required:
        if f not in payload:
            problems.append(f"missing required field {f!r}")
    for f, type_name in schema.types.items():
        if f in payload:
            expected = _TYPE_NAMES.get(type_name, object)
            if not isinstance(payload[f], expected):
                problems.append(f"field {f!r} expected {type_name}")
    return (not problems, problems)


@dataclass
class SchemaEvaluator:
    evaluator_ref: str
    schema: FieldSchema
    kind: str = "schema"

    def evaluate(self, *, payload: dict, commitment=None, input_ref: EvaluatorInputRef | None = None) -> RawEvaluation:
        ok, problems = schema_validate(payload, self.schema)
        return RawEvaluation(
            evaluator_ref=self.evaluator_ref,
            agent_feedback={"passed": ok, "problem_count": len(problems)},
            researcher_diagnostics={"passed": ok, "problems": problems},
            determinism="deterministic",
        )
