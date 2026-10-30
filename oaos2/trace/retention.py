"""Declare how much detail is retained alongside the event record.

The policy controls raw responses, file patches, reasoning content, and agent
view snapshots. It does not authorize dropping event envelopes or causal links.
Consumers must apply these settings and save the downgrade stamps; a policy
object alone does not change storage behavior.

validate_for_mode() requires keep_all raw responses, full_patch file changes,
and full agent snapshots in confirmatory mode. It does not test reasoning_content.
Large or binary files can still lack text patches; see workspace/hashing.py."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class RunMode(str, Enum):
    PILOT = "pilot"
    CALIBRATION = "calibration"
    CONFIRMATORY = "confirmatory"
    EXPLORATORY = "exploratory"


class RawPayloadFidelity(str, Enum):
    KEEP_ALL = "keep_all"
    ON_ERROR = "on_error"
    SAMPLED = "sampled"


class FileChangeFidelity(str, Enum):
    FULL_PATCH = "full_patch"
    HASHES_ONLY = "hashes_only"


class ReasoningFidelity(str, Enum):
    FULL = "full"
    SUMMARY = "summary"
    OFF = "off"


class AgentViewFidelity(str, Enum):
    FULL = "full"
    REFS_ONLY = "refs_only"


class RetentionPolicy(BaseModel):
    """Per-class payload fidelity (M0 §7). Its hash enters ``manifest.json``."""

    model_config = ConfigDict(extra="forbid")

    raw_provider_payloads: RawPayloadFidelity = RawPayloadFidelity.KEEP_ALL
    raw_payload_sample_rate: float | None = None  # set iff raw == sampled
    file_changes: FileChangeFidelity = FileChangeFidelity.FULL_PATCH
    reasoning_content: ReasoningFidelity = ReasoningFidelity.FULL
    agent_view_snapshots: AgentViewFidelity = AgentViewFidelity.FULL
    # interventions / commitments / evaluations are ALWAYS full (claim-bearing);
    # not tunable, so not represented as a field.

    extensions: dict = Field(default_factory=dict)  # namespaced; core never reads

    def validate_for_mode(self, mode: RunMode) -> None:
        """Enforce the confirmatory mode floor (M0 §7).

        Raises ``ValueError`` if a claim-bearing class is below its confirmatory
        floor when ``mode == confirmatory``. Other modes may downgrade freely.
        """
        if mode is not RunMode.CONFIRMATORY:
            return
        problems: list[str] = []
        if self.raw_provider_payloads is not RawPayloadFidelity.KEEP_ALL:
            problems.append(
                "raw_provider_payloads must be keep_all in confirmatory mode "
                "(the exposure-parity audit needs the verbatim payload, §10.2)"
            )
        if self.file_changes is not FileChangeFidelity.FULL_PATCH:
            problems.append(
                "file_changes must be full_patch in confirmatory mode "
                "(outcome-feeding changes are claim-bearing)"
            )
        if self.agent_view_snapshots is not AgentViewFidelity.FULL:
            problems.append("agent_view_snapshots must be full in confirmatory mode")
        if problems:
            raise ValueError(
                "RetentionPolicy violates the confirmatory mode floor (§7): "
                + "; ".join(problems)
            )

    def downgrade_stamps(self) -> dict[str, str]:
        """Per-class fidelity stamps recorded alongside downgraded payloads.

        A lean archive carries these so it can never read as complete (M0 §7
        honesty rule). Only classes actually below max fidelity are stamped.
        """
        stamps: dict[str, str] = {}
        if self.raw_provider_payloads is not RawPayloadFidelity.KEEP_ALL:
            tag = self.raw_provider_payloads.value
            if self.raw_provider_payloads is RawPayloadFidelity.SAMPLED:
                tag = f"sampled@{self.raw_payload_sample_rate}"
            stamps["raw_provider_payloads"] = tag
        if self.file_changes is not FileChangeFidelity.FULL_PATCH:
            stamps["file_changes"] = self.file_changes.value
        if self.reasoning_content is not ReasoningFidelity.FULL:
            stamps["reasoning_content"] = self.reasoning_content.value
        if self.agent_view_snapshots is not AgentViewFidelity.FULL:
            stamps["agent_view_snapshots"] = self.agent_view_snapshots.value
        return stamps
