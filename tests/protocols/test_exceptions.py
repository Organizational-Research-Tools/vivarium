"""Task-generic ExceptionRecord schema (platform_theory_audit.md §11.1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from oaos2.protocols.exceptions import (
    ExceptionRecord,
    ExceptionReport,
    validate_exception_records,
)


def _record(**overrides) -> dict:
    base = {
        "exception_id": "X1",
        "trigger_refs": ["N-7"],
        "affected_scopes": ["office/parks", "office/roads"],
        "summary": "delivery halt makes the shared vendor allocation invalid",
    }
    base.update(overrides)
    return base


def test_valid_record_and_empty_report() -> None:
    record = ExceptionRecord(**_record())
    assert record.rule_ref is None  # uncovered claim is the default
    assert ExceptionReport(records=[]).records == []  # "no exceptions" is a legal act


def test_rule_ref_is_optional_but_nonempty() -> None:
    assert ExceptionRecord(**_record(rule_ref="R3")).rule_ref == "R3"
    with pytest.raises(ValidationError):
        ExceptionRecord(**_record(rule_ref="   "))


def test_identity_and_reference_shape_enforced() -> None:
    with pytest.raises(ValidationError):
        ExceptionRecord(**_record(exception_id="  "))
    with pytest.raises(ValidationError):
        ExceptionRecord(**_record(trigger_refs=[]))
    with pytest.raises(ValidationError):
        ExceptionRecord(**_record(trigger_refs=["N-7", "N-7"]))
    with pytest.raises(ValidationError):
        ExceptionRecord(**_record(affected_scopes=["office/parks", " "]))
    with pytest.raises(ValidationError):  # closed shape: no smuggled fields
        ExceptionRecord(**_record(oracle_note="leak"))


def test_report_rejects_duplicate_ids() -> None:
    with pytest.raises(ValidationError):
        ExceptionReport(records=[_record(), _record(summary="other")])


def test_validate_helper_returns_problems_not_raises() -> None:
    assert validate_exception_records([]) == []
    assert validate_exception_records([_record()]) == []
    problems = validate_exception_records([_record(trigger_refs=[])])
    assert problems and all(isinstance(p, str) for p in problems)
    assert validate_exception_records({"not": "a list"})
    # problem text is shape-only: never mentions oracle classification
    joined = " ".join(problems)
    assert "rule_covered" not in joined and "oracle" not in joined
