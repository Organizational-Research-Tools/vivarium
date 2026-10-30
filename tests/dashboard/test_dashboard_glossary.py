"""The plain-language layer: every gh() term used in templates exists in the
glossary, and chips/labels explain themselves on hover."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from oaos2.dashboard import glossary

TEMPLATES = Path(__file__).resolve().parents[2] / "oaos2" / "dashboard" / "templates"


def test_every_gh_term_is_defined() -> None:
    used = set()
    for tpl in TEMPLATES.glob("*.html"):
        # gh("term") and gh("term", "label") — first arg is the glossary key
        used |= set(re.findall(r'gh\(\s*"([^"]+)"', tpl.read_text()))
    used.discard("pivot.axis")  # dynamic key, resolved at render time
    missing = sorted(t for t in used if t not in glossary.GLOSSARY)
    assert not missing, f"templates reference undefined glossary terms: {missing}"


def test_glossary_texts_are_plain_prose() -> None:
    for source in (glossary.GLOSSARY, glossary.STATUS_HELP,
                   glossary.PROVENANCE_HELP, glossary.SEVERITY_HELP):
        for term, text in source.items():
            assert text and len(text) > 15, f"{term!r} needs a real explanation"
            assert "§" not in text, f"{term!r}: no spec refs in user-facing text"


HOVER_LIMIT = 160  # a hover is one or two short sentences; longer text belongs in the page's panel


def test_hovers_stay_short_and_pages_have_one_reading_panel() -> None:
    for source in (glossary.GLOSSARY, glossary.STATUS_HELP,
                   glossary.PROVENANCE_HELP, glossary.SEVERITY_HELP):
        for term, text in source.items():
            assert len(text) <= HOVER_LIMIT, f"{term!r}: {len(text)} chars; move detail to the page panel"
    inline = re.compile(r'help\(\s*(?:"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')\s*,\s*'
                        r'("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')\s*\)')
    for tpl in TEMPLATES.glob("*.html"):
        text = tpl.read_text()
        for m in inline.finditer(text):
            assert len(m.group(1)) - 2 <= HOVER_LIMIT, f"{tpl.name}: hover too long: {m.group(1)[:60]}"
        assert text.count("{% call howto(") <= 1, f"{tpl.name}: one reading panel per page"


def test_chip_help_covers_every_value() -> None:
    from oaos2.dashboard.app import STATUS_CHIP
    from oaos2.dashboard.provenance import PROVENANCE_CHIP
    assert set(STATUS_CHIP) <= set(glossary.STATUS_HELP)
    assert set(PROVENANCE_CHIP) <= set(glossary.PROVENANCE_HELP)
    assert {"critical", "serious", "warning", "info"} <= set(glossary.SEVERITY_HELP)


fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from oaos2.dashboard.app import create_app  # noqa: E402


def test_chips_and_labels_self_explain(rich_run) -> None:
    client = TestClient(create_app(rich_run["runs_root"]))
    html = client.get("/runs").text
    # status + provenance chips carry their definitions
    assert glossary.STATUS_HELP["completed"][:30] in html  # no pass/fail across experiments
    assert glossary.PROVENANCE_HELP["superseded"][:30] in html
    # run overview: pins + outcome terms come from the one glossary
    run_html = client.get(f"/run/{rich_run['run_ref']}").text
    for term in ("disposition", "commitments"):
        assert glossary.GLOSSARY[term][:25] in run_html, term
    record_html = client.get(f"/run/{rich_run['run_ref']}/record").text
    for term in ("reference", "derived views"):
        assert glossary.GLOSSARY[term][:25] in record_html, term
    # flow legend explains the colors in plain words
    flow_html = client.get(f"/run/{rich_run['run_ref']}/flow").text
    assert "private reasoning before acting" in flow_html
    # severity chips explain the trust tiers on the audit page
    audit_html = client.get(f"/run/{rich_run['run_ref']}/audit").text
    assert glossary.SEVERITY_HELP["warning"][:20] in audit_html
