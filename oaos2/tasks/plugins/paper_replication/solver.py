"""Deterministic offline solver (M7 §2 stub) — pack-specific plugin CODE.

The Tier-A deterministic runtime used by the OFFLINE four-arm framework gate (no
model, no spend): a *specialized* committer produces the calibrated correct
results (read from the hidden reference — host-side, never agent-visible); a
*generalist* produces results degraded beyond tolerance. The submitted payload is
the flat result dict the real ``numeric_compare`` scores, so the structural
comparison + capacity check run end-to-end deterministically. A real run uses the
host-owned ``ModelAgentBehavior`` instead.
"""

from __future__ import annotations

from oaos2.tasks.plugins.paper_replication.numeric_compare import load_reference


def correct_results() -> dict[str, float]:
    """The calibrated 17 results, read from the hidden reference (host-side only)."""
    ref = load_reference()
    return {r["name"]: r["value"] for r in ref["results"] if r.get("value") is not None}


def produce_milestone_payload(milestone_id: str, specialized: bool) -> dict:
    """Specialization → implementation correctness (the offline framework gate)."""
    if milestone_id == "spec_v1":
        return {"analysis_plan": "replicate Tables 1/3/4/5 of the lab study",
                "outcome_vars": list(correct_results().keys())}
    # The scored numeric submission — `implementation_v1` (decomposed) OR `results`
    # (single-submission). Both carry the final numbers, so the offline arms score on
    # the SAME quantity regardless of contract profile: specialized → correct, generalist
    # → degraded beyond tolerance.
    if milestone_id in ("implementation_v1", "results"):
        c = correct_results()
        return dict(c) if specialized else {k: (v * 5 + 10) for k, v in c.items()}
    return {"review": "ok"}  # review_v1 (optional)
