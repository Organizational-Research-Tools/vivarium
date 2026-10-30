"""Deterministic exception-lifecycle projection (platform_theory_audit.md §11.4).

Queues, coverage joins, and latencies are derived from a synthetic trace — pure
data in, pure data out, byte-identical on re-derivation.
"""

from __future__ import annotations

import pytest

from oaos2.archive.exceptions import ExceptionProjectionError, derive_exception_dataset


def _commit(cid: str, seq: int, agent: str = "a1") -> dict:
    return {
        "event_class": "state.committed",
        "sequence_number": seq,
        "role_id": f"role_{agent}",
        "payload": {"state_commitment": {"commitment_id": cid, "agent_id": agent}},
    }


def _env(wave: str, packet: str, seq: int) -> dict:
    return {
        "event_class": "environment.event",
        "sequence_number": seq,
        "payload": {"environment_event": {"wave_id": wave, "packet_id": packet}},
    }


_SCHEDULE = {
    "schema_version": 1,
    "waves": [{
        "wave_id": "wave_1",
        "trigger_commitment_id": "initial_plan",
        "packets": [{
            "packet_id": "p1",
            "target_scopes": ["office/parks"],
            "payload": {"notice_id": "N-7", "notice": "vendor halt"},
            "classification": {
                "rule_coverage": "exception",
                "refs": ["N-7"],
                "expected_scopes": ["office/parks", "office/roads"],
            },
        }],
    }],
}

_EVENTS = [
    _commit("initial_plan", 2),
    _env("wave_1", "p1", 5),
    _commit("exception_report_w1_parks", 8, agent="parks"),
    _commit("revised_plan_w1", 10),
    _commit("repair_w1", 12, agent="integrator"),
]

_SUBMITTED = {
    "initial_plan": {"allocation": {}},
    "exception_report_w1_parks": {"exception_records": [
        {"exception_id": "X1", "trigger_refs": ["N-7"],
         "affected_scopes": ["office/roads", "office/parks"],
         "rule_ref": None, "summary": "joint vendor allocation invalid"},
        {"exception_id": "X2", "trigger_refs": ["N-UNKNOWN"],
         "affected_scopes": ["office/parks"], "summary": "never disposed"},
    ]},
    "revised_plan_w1": {"allocation": {"parks": 1}},
    "repair_w1": {"exception_dispositions": {
        "X1": {"disposition": "repaired", "repair_ref": "revised_plan_w1"},
        "X9": {"disposition": "dismissed", "reason": "orphan"},
    }},
}


def test_lifecycle_joins_oracle_and_measures_boundaries() -> None:
    data = derive_exception_dataset(
        _EVENTS, _SUBMITTED, source_prefix="exception_report_", schedule=_SCHEDULE)
    rows = {row["exception_id"]: row for row in data["lifecycle"]}
    x1 = rows["X1"]
    assert x1["filed_commitment_id"] == "exception_report_w1_parks"
    assert x1["filed_by"] == "parks"
    assert x1["matched_wave_ids"] == ["wave_1"]
    assert x1["oracle_rule_coverage"] == "exception"
    assert x1["oracle_expected_scopes"] == ["office/parks", "office/roads"]
    assert x1["affected_scopes"] == ["office/parks", "office/roads"]  # sorted
    # delivery seq 5 -> filing seq 8: one boundary (the filing commit itself)
    assert x1["detection_boundaries"] == 1
    # filing seq 8 -> disposal seq 12: revised_plan_w1 + repair_w1
    assert x1["closure_boundaries"] == 2
    assert x1["disposition"] == "repaired" and x1["repair_ref"] == "revised_plan_w1"

    x2 = rows["X2"]
    assert x2["disposition"] is None and x2["closure_boundaries"] is None
    assert x2["oracle_rule_coverage"] is None  # unmatched ref cannot be classified


def test_pending_series_and_summary() -> None:
    data = derive_exception_dataset(
        _EVENTS, _SUBMITTED, source_prefix="exception_report_", schedule=_SCHEDULE)
    series = {row["commitment_id"]: row for row in data["pending_series"]}
    assert series["initial_plan"]["pending_count"] == 0
    assert series["exception_report_w1_parks"]["pending_ids"] == ["X1", "X2"]
    assert series["revised_plan_w1"]["pending_count"] == 2
    assert series["repair_w1"]["pending_ids"] == ["X2"]  # X1 closed at this boundary

    summary = data["summary"]
    assert summary["n_filed"] == 2 and summary["n_disposed"] == 1
    assert summary["unresolved_ids"] == ["X2"]
    assert summary["by_disposition"] == {"repaired": 1}
    assert summary["by_oracle_coverage"] == {"rule_covered": 0, "exception": 1, "unjoined": 1}
    assert summary["max_pending"] == 2
    assert summary["mean_closure_boundaries"] == 2.0
    assert summary["unmatched_trigger_refs"] == ["N-UNKNOWN"]
    assert summary["orphan_disposition_ids"] == ["X9"]


def test_projection_is_deterministic_and_join_free_without_schedule() -> None:
    once = derive_exception_dataset(_EVENTS, _SUBMITTED, source_prefix="exception_report_")
    twice = derive_exception_dataset(_EVENTS, _SUBMITTED, source_prefix="exception_report_")
    assert once == twice
    x1 = next(r for r in once["lifecycle"] if r["exception_id"] == "X1")
    assert x1["oracle_rule_coverage"] is None  # no schedule -> no oracle claim
    assert once["summary"]["unmatched_trigger_refs"] == []  # nothing to mismatch


def test_ambiguous_schedule_refs_fail_loudly() -> None:
    schedule = {
        "waves": [{"wave_id": "w", "packets": [
            {"packet_id": "a", "classification": {"rule_coverage": "exception", "refs": ["N-7"]}},
            {"packet_id": "b", "classification": {"rule_coverage": "exception", "refs": ["N-7"]}},
        ]}],
    }
    with pytest.raises(ExceptionProjectionError, match="ambiguous"):
        derive_exception_dataset(_EVENTS, _SUBMITTED, schedule=schedule)


def test_duplicate_filings_first_wins() -> None:
    events = _EVENTS + [_commit("exception_report_w2_parks", 14, agent="parks")]
    submitted = dict(_SUBMITTED)
    submitted["exception_report_w2_parks"] = {"exception_records": [
        {"exception_id": "X1", "trigger_refs": ["N-7"],
         "affected_scopes": ["office/parks"], "summary": "refiled"}]}
    data = derive_exception_dataset(
        events, submitted, source_prefix="exception_report_", schedule=_SCHEDULE)
    assert data["summary"]["n_filed"] == 2  # X1 not double-counted
    assert data["summary"]["duplicate_filings"][0]["exception_id"] == "X1"
