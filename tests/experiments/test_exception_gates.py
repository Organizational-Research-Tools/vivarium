"""Exception filing + disposal conformance gates (platform_theory_audit.md §11.1).

Both gates are data-declared on the commitment's ``submission`` format and judge
shape only: whether a filed exception is GENUINE stays oracle-side, and the
disposal gate is the anti-smoothing closure discipline — an exception cannot
dissolve; it must be repaired (with a named repair), referred, or dismissed for
a stated reason.
"""

from __future__ import annotations

from oaos2.outcomes.conformance import check_conformance


def _record(rid: str = "X1", **overrides) -> dict:
    base = {
        "exception_id": rid,
        "trigger_refs": [f"N-{rid}"],
        "affected_scopes": ["office/parks", "office/roads"],
        "summary": "joint vendor allocation invalidated",
    }
    base.update(overrides)
    return base


_FILING_FMT = {"format": "structured", "exception_records": {"field": "exception_records"}}


# --- filing gate ------------------------------------------------------------ #

def test_filing_accepts_records_and_explicit_empty() -> None:
    ok, problems = check_conformance({"exception_records": [_record()]}, _FILING_FMT)
    assert ok and not problems
    ok_empty, _ = check_conformance({"exception_records": []}, _FILING_FMT)
    assert ok_empty  # "no exceptions this wave" is a legal observable act


def test_filing_rejects_missing_field_and_bad_shape() -> None:
    ok, problems = check_conformance({}, _FILING_FMT)
    assert not ok and any("exception_records" in p for p in problems)
    ok2, problems2 = check_conformance(
        {"exception_records": [_record(trigger_refs=[])]}, _FILING_FMT)
    assert not ok2 and any("trigger_refs" in p for p in problems2)


def test_filing_min_records_binds() -> None:
    fmt = {"format": "structured",
           "exception_records": {"field": "exception_records", "min_records": 1}}
    ok, problems = check_conformance({"exception_records": []}, fmt)
    assert not ok and any("at least 1" in p for p in problems)


# --- disposal gate ---------------------------------------------------------- #

_DISPOSAL_FMT = {
    "format": "structured",
    "record_dispositions_cover": {
        "field": "exception_dispositions",
        "source_prefix": "exception_report_",
    },
}
_COMMITTED = {
    "exception_report_w1_parks": {"exception_records": [_record("X1"), _record("X2")]},
    "exception_report_w1_roads": {"exception_records": []},
    "initial_plan": {"allocation": {}},
}


def test_disposal_requires_one_entry_per_filed_record() -> None:
    payload = {"exception_dispositions": {
        "X1": {"disposition": "repaired", "repair_ref": "repair_w1"},
    }}
    ok, problems = check_conformance(payload, _DISPOSAL_FMT, committed=_COMMITTED)
    assert not ok and any("'X2'" in p for p in problems)


def test_disposal_full_coverage_passes() -> None:
    payload = {"exception_dispositions": {
        "X1": {"disposition": "repaired", "repair_ref": "repair_w1"},
        "X2": {"disposition": "dismissed", "reason": "duplicate of X1 after the wave-1 notice"},
    }}
    ok, problems = check_conformance(payload, _DISPOSAL_FMT, committed=_COMMITTED)
    assert ok and not problems


def test_disposal_repaired_must_name_repair_and_others_need_reasons() -> None:
    payload = {"exception_dispositions": {
        "X1": {"disposition": "repaired"},
        "X2": {"disposition": "referred"},
    }}
    ok, problems = check_conformance(payload, _DISPOSAL_FMT, committed=_COMMITTED)
    assert not ok
    assert any("repair_ref" in p for p in problems)
    assert any("requires a stated reason" in p for p in problems)


def test_disposal_rejects_unknown_ids() -> None:
    payload = {"exception_dispositions": {
        "X1": {"disposition": "repaired", "repair_ref": "repair_w1"},
        "X2": {"disposition": "dismissed", "reason": "stale"},
        "X9": {"disposition": "dismissed", "reason": "never filed"},
    }}
    ok, problems = check_conformance(payload, _DISPOSAL_FMT, committed=_COMMITTED)
    assert not ok and any("unknown exception ids" in p and "X9" in p for p in problems)


def test_convergent_filing_owes_one_disposition() -> None:
    # Two offices filing the SAME case id is the brief's instruction, not an error:
    # one disposition covers both filings (external audit 2026-08-09 blocker 1 — the
    # earlier duplicate-id refusal deadlocked every compliant split-exception run).
    committed = dict(_COMMITTED)
    committed["exception_report_w1_roads"] = {"exception_records": [
        _record("X1", trigger_refs=["N-X1-ROADS"])]}
    payload = {"exception_dispositions": {
        "X1": {"disposition": "repaired", "repair_ref": "repair_w1"},
        "X2": {"disposition": "dismissed", "reason": "stale"},
    }}
    ok, problems = check_conformance(payload, _DISPOSAL_FMT, committed=committed)
    assert ok, problems


def test_repair_changes_bounded_to_own_office() -> None:
    import importlib
    importlib.import_module("oaos2.tasks.plugins.budget_execution.submission_gates")
    fmt = {"format": "structured",
           "changes_own_scope": {"field": "changes", "office_field": "office"}}
    from oaos2.outcomes.contracts import Commitment
    commitment = Commitment('repair_economy', 'artifact_submission',
                            routing={'office': 'economy'})
    ok, _ = check_conformance(
        {"office": "economy", "changes": [{"program": "economy_main_street", "amount": 6}]},
        fmt, commitment=commitment)
    assert ok
    ok2, problems = check_conformance(
        {"office": "economy", "changes": [{"program": "health_maternal", "amount": 6}]},
        fmt, commitment=commitment)
    assert not ok2 and any("outside your office" in p for p in problems)
    ok3, _ = check_conformance({"office": "economy", "changes": []}, fmt, commitment=commitment)
    assert ok3  # the legal no-op survives


def test_disposal_vocabulary_is_declarable() -> None:
    fmt = {
        "format": "structured",
        "record_dispositions_cover": {
            "field": "exception_dispositions",
            "source_prefix": "exception_report_",
            "valid_dispositions": ["resolved", "escalated"],
            "repaired_label": "resolved",
        },
    }
    committed = {"exception_report_w1": {"exception_records": [_record("X1")]}}
    ok, _ = check_conformance(
        {"exception_dispositions": {"X1": {"disposition": "resolved", "repair_ref": "r1"}}},
        fmt, committed=committed)
    assert ok
    ok2, problems = check_conformance(
        {"exception_dispositions": {"X1": {"disposition": "repaired", "repair_ref": "r1"}}},
        fmt, committed=committed)
    assert not ok2 and any("resolved" in p for p in problems)


def test_v14_disposition_gate_requires_a_declared_option_letter() -> None:
    # Study CH1: membership in the participant-visible label set only — which letter
    # is RIGHT never enters the gate, so this feedback cannot leak the key.
    import oaos2.tasks.plugins.budget_execution.submission_gates as gates
    spec = {"case_id": "C-S14", "valid_dispositions": ["repaired", "referred"],
            "repair_ref_allow": ["disposition_cs14"], "option_ids": ["A", "B", "C"],
            "require_option_id": True}
    ok_payload = {"case_id": "C-S14", "disposition": "repaired",
                  "repair_ref": "disposition_cs14", "selected_option_id": "b"}
    assert gates.case_disposition(spec, ok_payload, None) == []
    problems = gates.case_disposition(spec, {**ok_payload, "selected_option_id": "D"}, None)
    assert problems and "selected_option_id" in problems[0] and "['A', 'B', 'C']" in problems[0]
    problems = gates.case_disposition(spec, {k: v for k, v in ok_payload.items()
                                             if k != "selected_option_id"}, None)
    assert problems and "selected_option_id" in problems[0]
    # referred / dismissed owe a reason, not a letter
    assert gates.case_disposition(spec, {"case_id": "C-S14", "disposition": "referred",
                                         "reason": "needs the fund"}, None) == []
    # stage-1 specs (no option_ids) are untouched
    legacy = {k: v for k, v in spec.items() if k not in ("option_ids", "require_option_id")}
    assert gates.case_disposition(legacy, {k: v for k, v in ok_payload.items()
                                           if k != "selected_option_id"}, None) == []
