"""The interface for task-specific scoring.

An evaluator receives declared keyword inputs including a submitted payload and
returns RawEvaluation. That result separates intended agent feedback from private
researcher diagnostics. write_evaluation applies the public-feedback checks.
The runner handles evaluator failure and records it; this interface alone does
not emit events or impose the deferred evaluator-specific spending cap."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class EvaluatorInputRef:
    """A host-side reference to the hidden reference/answer key (NEVER agent-visible)."""

    ref: str  # e.g. a hidden-zone path
    content_hash: str | None = None


@dataclass
class RawEvaluation:
    """An evaluator's full output, before the diagnostic split (M6 §4.1)."""

    evaluator_ref: str
    agent_feedback: dict  # candidate public feedback (whitelisted at write time)
    researcher_diagnostics: dict  # full detail; never delivered to agents
    determinism: str = "deterministic"  # deterministic | stochastic(seeded) | stochastic
    extensions: dict = field(default_factory=dict)


class Evaluator(Protocol):
    evaluator_ref: str
    kind: str  # "schema" | "plugin"

    def evaluate(
        self, *, payload: dict, commitment, input_ref: EvaluatorInputRef | None
    ) -> RawEvaluation: ...
