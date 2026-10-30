"""The competition study's coding sheets (data/competition-9.2/coding/) are as screened and labelled, and withhold the
reasoning text, the coders' notes and the passages."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

CODING = Path(__file__).resolve().parents[2] / "data" / "competition-9.2" / "coding"
TOP = {"README.md", "manifest.sha256"}


def _keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


def test_every_file_matches_the_checksum_list():
    listed = dict(reversed(line.split("  ", 1)) for line in (CODING / "manifest.sha256").read_text().splitlines())
    present = {p.relative_to(CODING).as_posix() for p in CODING.rglob("*") if p.is_file()}
    assert present - TOP == set(listed)
    assert all(hashlib.sha256((CODING / rel).read_bytes()).hexdigest() == d for rel, d in listed.items())


def test_the_sheets_keep_only_their_codes_and_screened_quotations():
    for name in ("first_coding.json", "second_coding.json"):
        sheet = json.loads((CODING / name).read_text())
        assert not _keys(sheet) & {"notes", "thinking", "unverified_quotes", "text", "excerpt"}
        for run in sheet.values():
            for lab in run["labs"].values():
                assert set(lab["_meta"]) <= {"model"}
                withheld = [item for item in (lab["E"], lab["F"], *lab["H"]["public"], *lab["N"]) if item.get("quote_withheld")]
                assert all(item["quote"] is None for item in withheld)


def test_no_passage_and_no_reasoning_excerpt_is_released():
    names = {p.name for p in CODING.rglob("*.json")}
    assert not {n for n in names if "packet" in n or n == "deciders.json"}
    excerpts = json.loads((CODING / "test_reading" / "t1_public_excerpts.json").read_text())
    assert excerpts and {e["kind"] for e in excerpts} == {"post", "send_note"}


def test_the_screens_found_nothing_and_the_readme_carries_the_notice():
    screens = json.loads((CODING / "screen.json").read_text())["screens"]
    assert screens and not any(screens.values())
    readme = (CODING / "README.md").read_text()
    assert "**Not for model training.**" in readme and "## Terms of use" in readme and "## AI-generated content" in readme
    assert not [p for p in CODING.rglob("*") if p.is_file() and b"/Users/" in p.read_bytes()]
