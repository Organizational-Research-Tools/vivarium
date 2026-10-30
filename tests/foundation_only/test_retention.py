"""RetentionPolicy tests (M0 §7): mode floor + recorded downgrades."""

from __future__ import annotations

import pytest

from oaos2.trace.retention import (
    AgentViewFidelity,
    FileChangeFidelity,
    RawPayloadFidelity,
    ReasoningFidelity,
    RetentionPolicy,
    RunMode,
)


def test_default_policy_passes_confirmatory_floor() -> None:
    RetentionPolicy().validate_for_mode(RunMode.CONFIRMATORY)  # no raise


def test_confirmatory_floor_rejects_lean_claim_bearing_classes() -> None:
    lean = RetentionPolicy(
        raw_provider_payloads=RawPayloadFidelity.ON_ERROR,
        file_changes=FileChangeFidelity.HASHES_ONLY,
        agent_view_snapshots=AgentViewFidelity.REFS_ONLY,
    )
    with pytest.raises(ValueError):
        lean.validate_for_mode(RunMode.CONFIRMATORY)
    # But a pilot may downgrade freely.
    lean.validate_for_mode(RunMode.PILOT)


def test_downgrade_stamps_record_what_was_used() -> None:
    lean = RetentionPolicy(
        raw_provider_payloads=RawPayloadFidelity.SAMPLED,
        raw_payload_sample_rate=0.1,
        reasoning_content=ReasoningFidelity.SUMMARY,
    )
    stamps = lean.downgrade_stamps()
    assert stamps["raw_provider_payloads"] == "sampled@0.1"
    assert stamps["reasoning_content"] == "summary"
    # Full policy stamps nothing (a complete archive carries no downgrade marks).
    assert RetentionPolicy().downgrade_stamps() == {}
