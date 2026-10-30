"""Foundation-only / zero-diff boundary (DESIGN §4.1, §5.5, §22).

Core knows files, messages, agents, outcomes, evaluators, events, validators,
runs — never domain logic. Domain semantics live in task packs (``oaos2.tasks``)
and experiment config (``oaos2.experiments``). This test enforces the dependency
direction mechanically: **no core module may import ``oaos2.tasks`` or
``oaos2.experiments``.** If a future task family forced such an import, a seam
would be missing — the zero-diff gate would (correctly) fail here.
"""

from __future__ import annotations

import pathlib
import re

CORE_PACKAGES = [
    "trace", "kernel", "communication", "protocols", "outcomes", "evaluation",
    "models", "pricing", "docker", "workspace", "organizations",
]
FORBIDDEN = re.compile(r"\bimport\s+oaos2\.(tasks|experiments)\b|\bfrom\s+oaos2\.(tasks|experiments)\b")

_ROOT = pathlib.Path(__file__).resolve().parents[2] / "oaos2"


def test_core_does_not_import_domain() -> None:
    offenders: list[str] = []
    for pkg in CORE_PACKAGES:
        for py in (_ROOT / pkg).rglob("*.py"):
            text = py.read_text()
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if FORBIDDEN.search(line):
                    offenders.append(f"{py.relative_to(_ROOT)}:{i}: {stripped}")
    assert not offenders, "core modules import domain packages:\n" + "\n".join(offenders)


def test_top_level_root_modules_are_domain_free() -> None:
    # registry.py and ulid.py are pure foundation primitives.
    for name in ("registry.py", "ulid.py"):
        text = (_ROOT / name).read_text()
        assert "oaos2.tasks" not in text and "oaos2.experiments" not in text


def test_config_library_is_data_outside_the_engine() -> None:
    # Experiment CONFIG (task packs, org specs, designs) is declarative DATA in a
    # committed ``library/`` beside the engine — NOT inside the ``oaos2/`` package and
    # NOT a Python import. A config-building tool writes files there; loaders read them.
    from oaos2.library import library_dir

    lib = library_dir()
    repo = _ROOT.parent
    assert lib == repo / "library" or lib.is_absolute()  # default beside oaos2/, or overridden
    # Default library is a sibling of oaos2/, never under it (config ≠ code).
    if "OAOS2_LIBRARY" not in __import__("os").environ:
        assert lib.parent == repo and lib.name == "library"
        assert _ROOT not in lib.parents
    # There is no importable ``library`` package — it is pure data, never imported.
    assert not (_ROOT / "library").exists()


def test_orchestration_carries_no_pack_commitment_semantics() -> None:
    # Widened boundary (structural repair 2026-08-16, item 7): the import gate
    # above cannot see a pack's SEMANTICS smuggled into shared orchestration as
    # string literals — the clock adoption did exactly that (the runner parsed
    # disposition_*/office_plan_*/exception_report_* commitment names) and the
    # gate stayed green. Commitment meaning now rides declared metadata
    # (Commitment.timing, bound by oaos2/tasks/clock.py); pack-specific names
    # may appear ONLY in that pack's plugin and in config/data.
    # Quoted literals only: a pack's commitment NAME appearing as a string in
    # shared code is the smell (prefix parsing, hardcoded ids); generic
    # vocabulary in identifiers (e.g. a `disposition_id` binding map) is fine.
    # The budget_allocation feedback slots (domain_report_*/draft_comment_*/
    # amendment_*) joined the gate when their runner dispatch moved onto timing
    # metadata (b17cc92; widened in 01596df); `amendment_` is matched only in
    # its smell forms (bare prefix, f-string prefix, full slot id) because the
    # pack's legitimate shared vocabulary — amendment_timeout_s,
    # amendment_unavailable, amendment_id, amendment_dispositions,
    # amendment_rotation — shares the prefix.
    pack_literals = re.compile(
        r"""["'](disposition_|exception_report_|office_plan_|revised_plan_w1"""
        r"""|initial_plan|final_plan|operational_amendments|case_disposition"""
        r"""|changes_own_scope|domain_report_|draft_comment_"""
        r"""|amendment_(?:["'{]|economy|health|housing|infrastructure"""
        r"""|environment|workforce))""")
    # outcomes/ scans too (audit round 8 P1-2): the budget gate vocabulary
    # that sat in conformance.py for weeks is exactly what this gate missed.
    shared = [_ROOT / "experiments", _ROOT / "agents", _ROOT / "tasks",
              _ROOT / "outcomes"]
    plugin_root = _ROOT / "tasks" / "plugins"
    offenders: list[str] = []
    for base in shared:
        for py in base.rglob("*.py"):
            if plugin_root in py.parents:
                continue  # a plugin OWNS its pack's semantics
            for i, line in enumerate(py.read_text().splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if pack_literals.search(line):
                    offenders.append(f"{py.relative_to(_ROOT)}:{i}: {stripped}")
    assert not offenders, (
        "pack commitment names appear in shared orchestration (declare timing "
        "metadata instead):\n" + "\n".join(offenders))


def test_no_module_imports_a_library_package() -> None:
    # Nothing in the engine may ``import library`` — config is read via loaders (file
    # I/O against ``library_dir()``), not as code. Guards the data/code seam.
    bad = re.compile(r"^\s*(from|import)\s+library\b")
    offenders = [
        f"{py.relative_to(_ROOT)}"
        for py in _ROOT.rglob("*.py")
        for line in py.read_text().splitlines()
        if bad.match(line)
    ]
    assert not offenders, "engine imports a 'library' package (config must be data):\n" + "\n".join(offenders)
