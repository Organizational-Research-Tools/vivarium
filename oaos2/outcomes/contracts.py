"""Declare required commitments and the condition that closes an outcome.

blocks records dependencies between commitments. Contract validation rejects
cycles, so mutually dependent submissions cannot be declared. Scheduling,
conversation state, and clock deadlines can impose additional execution order;
the dependency graph is not the runtime's only ordering rule."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class InvalidContract(Exception):
    """A malformed OutcomeContract (cyclic blocks, no closure) (M6 §3.1)."""


class ClosureKind(str, Enum):
    ALL_REQUIRED_COMMITTED = "all_required_committed"
    QUORUM_COMMITTED = "quorum_committed"  # Tier-C (needs many_to_* aggregation)
    AGGREGATION_CLOSED = "aggregation_closed"  # Tier-C
    TIMEOUT_THEN_STATE = "timeout_then_state"
    FIRST_TO_THRESHOLD = "first_to_threshold"


@dataclass
class Commitment:
    commitment_id: str
    kind: str  # open registry: artifact_submission, vote_resolved, ...
    payload_schema_ref: str | None = None
    required: bool = True
    committer_roles: list[str] = field(default_factory=list)
    evaluators: list[str] = field(default_factory=list)  # evaluator refs
    blocks: list[str] = field(default_factory=list)  # commitment ids this one depends on
    # Submit-time conformance gate (DESIGN §13 / M7 §2.1 "shape validated in commit()"):
    # the payload's required SHAPE + a bounded retry-with-correction policy, declared as
    # data on the commitment. Empty ⇒ no shape gate (commit accepts any payload).
    submission: dict = field(default_factory=dict)  # {format, min_results, max_retries, ...}
    # Clocked-time metadata (tasks/clock.py owns the schema and binding): which case
    # this slot serves and when it is due — declared here as data so the platform
    # never parses commitment names. Empty ⇒ untimed. {role, case, due_with}
    timing: dict = field(default_factory=dict)
    # Stage-routing metadata (loader validates at load): which review stage a
    # slot plays and whose office it serves — {stage: report|amendment|comment,
    # office}. Routing is NOT timing (audit round 6 P2-3): batched profiles use
    # it without a clock, so it must not ride the temporal schema.
    routing: dict = field(default_factory=dict)


@dataclass
class ClosureCondition:
    kind: str = ClosureKind.ALL_REQUIRED_COMMITTED.value
    quorum: int | None = None
    timeout_seconds: int | None = None
    terminal_state_on_timeout: str | None = None
    threshold: int | None = None


@dataclass
class OutcomeContract:
    outcome_id: str
    commitments: list[Commitment]
    closure_condition: ClosureCondition = field(default_factory=ClosureCondition)

    def commitment(self, commitment_id: str) -> Commitment:
        for c in self.commitments:
            if c.commitment_id == commitment_id:
                return c
        raise KeyError(commitment_id)

    def validate(self) -> None:
        self.validate_blocks_dag()

    def validate_blocks_dag(self) -> None:
        """Reject a cyclic blocks relation at load (M6 §3.1)."""
        graph = {c.commitment_id: list(c.blocks) for c in self.commitments}
        WHITE, GREY, BLACK = 0, 1, 2
        color = {n: WHITE for n in graph}

        def visit(n: str) -> None:
            color[n] = GREY
            for m in graph.get(n, ()):
                if color.get(m, BLACK) == GREY:
                    raise InvalidContract(
                        f"OutcomeContract.blocks contains a cycle through {n} -> {m} — "
                        "no commitment in the cycle could ever satisfy its blockers"
                    )
                if color.get(m, BLACK) == WHITE:
                    visit(m)
            color[n] = BLACK

        for n in graph:
            if color[n] == WHITE:
                visit(n)


def closure_met(condition: ClosureCondition, committed: dict, contract: OutcomeContract) -> bool:
    """True iff the closure condition is satisfied by the committed set (M6 §3.2)."""
    kind = condition.kind
    if kind == ClosureKind.ALL_REQUIRED_COMMITTED.value:
        return all(c.commitment_id in committed for c in contract.commitments if c.required)
    if kind == ClosureKind.FIRST_TO_THRESHOLD.value:
        return len(committed) >= (condition.threshold or 1)
    if kind == ClosureKind.QUORUM_COMMITTED.value:
        return len(committed) >= (condition.quorum or len(contract.commitments))
    if kind == ClosureKind.TIMEOUT_THEN_STATE.value:
        # Closure-by-timeout is driven externally; committing all required still closes.
        return all(c.commitment_id in committed for c in contract.commitments if c.required)
    # aggregation_closed is Tier-C (needs the aggregation plugin).
    return False
