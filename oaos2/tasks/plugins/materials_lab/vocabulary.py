"""The testing-firm wording of PC1 (`2026-10-10-supplier-k`; the PI, October 10, 2026).

Claude Haiku 5.5's safety classifier refused G4's agents on the laboratory wording of the same search
(category "bio"), so PC1's participants become six testing firms in the client's certification program, each
with one test bench. With ``vocabulary: testing`` in a preset, the runtime's own words reach the firms through
:func:`reword`: tool results of this pack, the start note, and the notices, results and reminders the pool
pushes. Agents' posts and notes are never reworded; nor is anything on the researcher channel except the
texts the events record as shown. The start materials (role packet, preset texts, tool descriptions) are
written for the firms by hand in the ``pc1_testing`` pack; this function is the runtime's share and a net
under them.

The map is the PI's: specimens become test cases; a qualification panel, a certification run; an exploratory
reading, a quick run; qualified, certified; a recipe, a design; a formulation module or additive package, a
design component; an instrument, a test bench; a laboratory, a firm. "Supplier variant" stays. The runtime's
own speaker, "[laboratory]", becomes "[program office]".

Without the preset setting nothing changes, so earlier versions read as before.
"""
from __future__ import annotations

import re

VOCABULARIES = ("", "testing")

# Old words a firm must never read under the testing wording; the scripted check of supplier-k scans every
# text an agent receives for them (tests/tasks/test_pc1_testing_wording.py).
OLD_WORDS = re.compile(r"laborator|\blabs?\b|\blab_|specimen|panel|recipe|qualif|instrument|formulation|additive"
                       r"|exploratory", re.I)

# (pattern, replacement), applied in order; longer phrases first so that a later, shorter rule never meets
# a phrase an earlier rule has already rewritten. Patterns are case-insensitive; the first letter's case is kept.
_RULES: list[tuple[str, str]] = [
    (r"\[laboratory\]", "[program office]"),
    (r"\[lab\]", "[program office]"),
    (r"\blab_info\b", "firm_info"),
    (r"\bresearch credits?\b", "certification credits"),
    (r"\bobservation units\b", "test units"),  # the firms' budget of runs; the observation period keeps its name
    (r"\bobservation unit\b", "test unit"),
    (r"\bqualification program\b", "certification program"),
    (r"\ban exploratory reading\b", "a quick run"),
    (r"\bexploratory readings\b", "quick runs"),
    (r"\bexploratory reading\b", "quick run"),
    (r"\ban exploratory\b", "a quick"),
    (r"\bexploratory\b", "quick"),
    (r"\ba qualification panel\b", "a certification run"),
    (r"\bqualification panels\b", "certification runs"),
    (r"\bqualification panel\b", "certification run"),
    (r"\bfull panels\b", "full certification runs"),
    (r"\bfull panel\b", "full certification run"),
    (r"\bpanels\b", "certification runs"),
    (r"\bpanel\b", "certification run"),
    (r"\bqualification specimens\b", "certification test cases"),
    (r"\bspecimens\b", "test cases"),
    (r"\bspecimen\b", "test case"),
    (r"\bunqualified\b", "uncertified"),
    (r"\bqualifications\b", "certifications"),
    (r"\bqualification\b", "certification"),
    (r"\bqualifiable\b", "certifiable"),
    (r"\bqualifying\b", "certifying"),
    (r"\bqualified\b", "certified"),
    (r"\bqualifies\b", "certifies"),
    (r"\bqualify\b", "certify"),
    (r"\ban additive package\b", "a design component"),
    (r"\badditive packages?\b", "design component"),
    (r"\bformulation modules\b", "design components"),
    (r"\bformulation module\b", "design component"),
    (r"\bformulation notes\b", "design notes"),
    (r"\bformulations\b", "designs"),
    (r"\bformulation\b", "design"),
    (r"\bmodules\b", "design components"),
    (r"\bmodule\b", "design component"),
    (r"\brecipes\b", "designs"),
    (r"\brecipe\b", "design"),
    (r"\ban instrument\b", "a test bench"),
    (r"\binstrument owners\b", "test bench operators"),
    (r"\binstruments\b", "test benches"),
    (r"\binstrument\b", "test bench"),
    (r"\blaboratories'", "firms'"),
    (r"\blaboratories\b", "firms"),
    (r"\blaboratory's\b", "firm's"),
    (r"\blaboratory\b", "firm"),
    (r"\blabs'", "firms'"),
    (r"\blab's\b", "firm's"),
    (r"\blabs\b", "firms"),
    (r"\blab\b", "firm"),
]
_COMPILED = [(re.compile(p, re.I), r) for p, r in _RULES]


def _keep_case(replacement: str):
    def sub(m: re.Match) -> str:
        found = m.group(0)
        if found[:1].isupper() and replacement[:1].islower():
            return replacement[:1].upper() + replacement[1:]
        if found[:1] == "[" and found[1:2].isupper():
            return "[" + replacement[1:2].upper() + replacement[2:]
        return replacement
    return sub


def reword(text: str, vocabulary: str = "testing") -> str:
    """The runtime's text in ``vocabulary``; unchanged for the default (laboratory) wording."""
    if not vocabulary or not text:
        return text
    if vocabulary != "testing":
        raise ValueError(f"materials_lab: unknown vocabulary {vocabulary!r}")
    for pattern, replacement in _COMPILED:
        text = pattern.sub(_keep_case(replacement), text)
    return text


def pack_for(live_coordination: dict) -> str:
    """The task pack a materials-lab preset runs in: the testing firms' pack (tool names, descriptions, role
    packet) for the testing vocabulary, the materials lab otherwise."""
    return "pc1_testing" if (live_coordination or {}).get("vocabulary") == "testing" else "materials_lab"
