"""Codebooks are versioned data with definitions; the budget codebook loads and
validates; a bad entry fails loudly; deductive predicates evaluate over design labels."""

from __future__ import annotations

import pytest

from oaos2.annotations.codebook import (
    CodebookError,
    load_all_codebooks,
    load_codebook,
    predicate_matches,
)


def test_budget_codebook_loads_with_definitions() -> None:
    books = {b["pack_id"]: b for b in load_all_codebooks()}
    book = books["budget_execution"]
    assert "error" not in book and book["sha256"].startswith("sha256:")
    refs = {c["ref"] for c in book["codes"]}
    assert {"reading.read.v1", "mech.fan_in.v1", "fail.lateral_working.v1",
            "verdict.classifier_artifact.v1", "locus.own_case_officer.v1"} <= refs
    fan_in = next(c for c in book["codes"] if c["ref"] == "mech.fan_in.v1")
    assert fan_in["origin"] == "deductive" and fan_in["schema"].namespace == "mech"
    assert fan_in["schema"].arity == "group" and "apex" in fan_in["definition"]
    assert predicate_matches(fan_in["predicate"], {"design.cell.form": "budget_execution_vertical_clocked"}) is True
    assert predicate_matches(fan_in["predicate"], {"design.cell.form": "budget_execution_solo_clocked"}) is False
    assert predicate_matches({}, {}) is None


def test_bad_codebook_entries_fail_loudly(tmp_path) -> None:
    p = tmp_path / "codebook.yaml"
    p.write_text("pack_id: x\ncodes:\n  - ref: nope\n    definition: d\n")
    with pytest.raises(CodebookError):
        load_codebook(p)
    p.write_text("pack_id: x\ncodes:\n  - ref: a.b.v1\n")
    with pytest.raises(CodebookError):
        load_codebook(p)
    p.write_text("pack_id: x\ncodes:\n  - ref: a.b.v1\n    definition: d\n  - ref: a.b.v1\n    definition: d\n")
    with pytest.raises(CodebookError):
        load_codebook(p)
    p.write_text("pack_id: x\ncodes:\n  - ref: a.b.v1\n    definition: d\n    origin: guess\n")
    with pytest.raises(CodebookError):
        load_codebook(p)
