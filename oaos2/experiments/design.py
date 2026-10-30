"""Declare a study's factors, replications, mode, and comparison-resource policy.

A factor is a setting varied between conditions; a cell is one combination of
factor values. ExperimentDesign supplies the runner's expansion settings.
ParityPolicy declares which resource is matched and which comparison group
uses that limit. Validation and execution checks live in the loader and runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParityPolicy:
    basis: str = "usd"  # supported bases: usd or tokens (shared output tokens)
    regime: str = "both"  # budget_matched | unconstrained | both
    # Save the per-cell dollar cap with the study. None leaves it to the launcher.
    # The cap can affect behavior before exhaustion through budget-pressure messages.
    cap_usd: float | None = None
    cap_tokens: int | None = None  # shared realized output-token cap when basis=tokens
    # Keep tokens available for final submission by limiting non-final work to
    # cap minus reserve. This does not guarantee completion or a correct answer.
    reserve_tokens: int = 20000

    def validate(self) -> None:
        """Reject unknown policies before expanding the number and cost of cells."""
        if self.basis not in ("usd", "tokens"):
            raise ValueError(f"unsupported parity basis {self.basis!r}")
        if self.regime not in ("budget_matched", "unconstrained", "both"):
            raise ValueError(f"unsupported parity regime {self.regime!r}")

    def resolve_regimes(self, base_cap_usd: float, unconstrained_factor: float = 3.0):
        """Return the requested regime names and dollar limits before execution.

        budget_matched uses base_cap_usd. unconstrained uses that cap multiplied
        by unconstrained_factor, so it still has a spending ceiling. both returns
        both groups. Token-budget construction uses resolve_budgets()."""
        self.validate()
        matched = ("budget_matched", base_cap_usd)
        unconstrained = ("unconstrained", base_cap_usd * unconstrained_factor)
        if self.regime == "budget_matched":
            return [matched]
        if self.regime == "unconstrained":
            return [unconstrained]
        return [matched, unconstrained]  # "both"

    def resolve_budgets(self, *, base_cap_usd: float,
                        base_cap_tokens: int | None = None,
                        unconstrained_factor: float = 3.0):
        """Return regime budgets for the selected parity basis.

        USD remains a safety ceiling in token-matched runs; the experimental cap is
        the one shared output-token ledger across all agents and coordination calls.
        """
        self.validate()
        if self.basis == "usd":
            return [(name, {"cap_usd": cap, "cap_output_tokens": None})
                    for name, cap in self.resolve_regimes(base_cap_usd, unconstrained_factor)]
        if self.basis != "tokens":
            raise ValueError(f"unsupported parity basis {self.basis!r}")
        tokens = base_cap_tokens if base_cap_tokens is not None else self.cap_tokens
        if tokens is None or int(tokens) <= 0:
            raise ValueError("token-matched parity requires a positive cap_tokens")
        matched = ("budget_matched", {"cap_usd": base_cap_usd,
                                      "cap_output_tokens": int(tokens),
                                      "final_reserve_tokens": int(self.reserve_tokens)})
        unconstrained = ("unconstrained", {"cap_usd": base_cap_usd * unconstrained_factor,
                                           "cap_output_tokens": int(tokens * unconstrained_factor),
                                           "final_reserve_tokens": int(self.reserve_tokens)})
        if self.regime == "budget_matched":
            return [matched]
        if self.regime == "unconstrained":
            return [unconstrained]
        return [matched, unconstrained]


@dataclass
class ExperimentDesign:
    """The settings used to expand a study into repeated runs.

    Combine a task pack with factor values, resource policy, and research-evidence
    references. Library recipes live in library/experiments/. Launch scripts can
    change settings in memory; config/resolved_sweep.json records the actual plan
    used for each run."""

    name: str = "unnamed"
    task_pack: str = "paper_replication"
    factors: dict[str, list] = field(default_factory=dict)  # org_preset:[...], difficulty:[...], model:[...]
    replications: int = 1
    mode: str = "pilot"  # pilot | calibration | confirmatory
    parity_policy: ParityPolicy = field(default_factory=ParityPolicy)
    platform_seed: int = 0
    preregistration_ref: str | None = None  # required when mode == confirmatory (§19)
    source_ref: Path | None = None  # canonical YAML when loaded from the library
    # References to evidence required before a confirmatory launch, such as
    # capacity calibration for the requested model and task conditions.
    confirmatory_evidence: dict = field(default_factory=dict)

    def validate(self) -> None:
        """Check execution mode, resource policy, and required study references."""
        from oaos2.trace.retention import RunMode
        RunMode(self.mode)
        self.parity_policy.validate()
        if self.mode == "confirmatory" and not self.preregistration_ref:
            raise ValueError("confirmatory mode requires a preregistration_ref (§19)")
        if self.parity_policy.basis == "tokens" and not self.parity_policy.cap_tokens:
            raise ValueError("token-matched parity requires cap_tokens")
