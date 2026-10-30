"""The single-submission default: one agent (or N role-blind agents racing) closes
the sole scored commitment. No admission gates, no handoff channel, no
orchestration — the generic runner machinery (auto-advance duty notices, slot
ceilings, the clock) is everything these arms need."""

from __future__ import annotations

from oaos2.experiments.coordination.base import CoordinationProtocol


class SingleSubmissionProtocol(CoordinationProtocol):
    mode = None  # structurally resolved (no live_coordination.mode)

    def build_chain(self, org_spec, contract) -> list:
        sole = contract.commitments[0].commitment_id  # the single "results" submission
        return [(r, sole) for r in org_spec.roles]
