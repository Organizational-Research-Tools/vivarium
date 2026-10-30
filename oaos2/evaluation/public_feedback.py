"""Validate public feedback fields and retain private scoring diagnostics separately.

write_evaluation permits only allowed_fields, limits selected string lengths,
and rejects normalized forbidden substrings in top-level string values. Despite
the legacy name token_caps, limits are characters, measured with len().

The function does not validate feedback value types, recursively inspect nested
values, or prevent information encoded in allowed values. Exact text checks do
not catch paraphrases. This is a limited output check, not proof against answer-key
leakage; task feedback design needs its own review."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from oaos2.trace.records import EvaluationRecord


class EvaluationRejected(Exception):
    """Public feedback contains a disallowed field, overlong string, or restricted text."""


@dataclass
class PublicFeedbackSchema:
    allowed_fields: frozenset[str] = frozenset()
    token_caps: dict[str, int] = field(default_factory=dict)  # field -> maximum characters for string values (legacy field name)
    forbidden_substrings: frozenset[str] = frozenset()  # restricted text; matching normalizes case and whitespace


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def write_evaluation(
    *,
    raw,
    public_schema: PublicFeedbackSchema,
    outcome_id: str,
    commitment_id: str,
) -> EvaluationRecord:
    """Check public feedback and retain separate researcher diagnostics.

    Reject disallowed top-level keys. For string values, enforce the configured
    character limits and check forbidden substrings after normalizing case and
    whitespace. token_caps is a legacy name: these limits count characters.
    Value types and nested content are not validated here."""
    af = dict(raw.agent_feedback)
    illegal = set(af.keys()) - set(public_schema.allowed_fields)
    if illegal:
        raise EvaluationRejected(f"agent_feedback has disallowed keys: {sorted(illegal)}")
    for f, cap in public_schema.token_caps.items():
        if f in af and isinstance(af[f], str) and len(af[f]) > cap:
            raise EvaluationRejected(f"agent_feedback field {f!r} exceeds token cap {cap}")
    if public_schema.forbidden_substrings:
        for f, v in af.items():
            if isinstance(v, str):
                norm = _normalize(v)
                for secret in public_schema.forbidden_substrings:
                    if _normalize(secret) and _normalize(secret) in norm:
                        raise EvaluationRejected(
                            f"agent_feedback field {f!r} contains a forbidden (answer-key) substring"
                        )
    return EvaluationRecord(
        evaluation_id=_new_id(),
        commitment_ref=commitment_id,
        outcome_id=outcome_id,  # group-by-outcome link on the canonical record (M6 §5)
        evaluator_ref=raw.evaluator_ref,
        evaluator_kind="schema" if raw.evaluator_ref.startswith("schema") else "plugin",
        # Persist the determinism signal the confirmatory gate relies on (M6 §5) —
        # previously computed on RawEvaluation but dropped from the archived record.
        determinism=getattr(raw, "determinism", "deterministic"),
        agent_feedback=af,  # → delivered to the agent
        researcher_diagnostics=dict(raw.researcher_diagnostics),  # → NEVER to agents
    )


def _new_id() -> str:
    from oaos2.ulid import new_ulid

    return new_ulid()
