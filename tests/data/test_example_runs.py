"""The competition study's example runs (data/competition-9.2/example_runs/) are as reviewed, labelled, and open
in the dashboard's run discovery."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from oaos2.archive.registry import discover_run_dirs

RUNS = Path(__file__).resolve().parents[2] / "data" / "competition-9.2" / "example_runs"
TOP = {"README.md", "REVIEW.md", "REVIEW.json", "manifest.sha256"}


def _listed() -> dict[str, str]:
    out = {}
    for line in (RUNS / "manifest.sha256").read_text().splitlines():
        digest, _, rel = line.partition("  ")
        out[rel] = digest
    return out


def test_every_file_matches_the_checksum_list():
    listed = _listed()
    present = {p.relative_to(RUNS).as_posix() for p in RUNS.rglob("*") if p.is_file()
               and ".dashboard" not in p.relative_to(RUNS).parts}
    assert present - TOP == set(listed)
    assert all(hashlib.sha256((RUNS / rel).read_bytes()).hexdigest() == d for rel, d in listed.items())
    assert max((RUNS / rel).stat().st_size for rel in present) < 50 * 1024 * 1024


def test_ten_labelled_runs_without_raw_responses_or_reasoning_text():
    folders = sorted(p for p in RUNS.iterdir() if p.is_dir() and p.name.startswith("pc1_x7b_"))
    assert len(folders) == 10
    for run in folders:
        assert "AI-generated" in (run / "MODELS.md").read_text()
        assert not list(run.rglob("raw"))
        for events in run.glob("*/*/trace/events.jsonl"):
            for line in events.read_text().splitlines():
                e = json.loads(line)
                assert not (e.get("event_class") == "reasoning.step" and "thinking" in (e.get("payload") or {}))
    readme = (RUNS / "README.md").read_text()
    assert "**Not for model training.**" in readme and "## Terms of use" in readme


def test_no_local_paths():
    assert not [p for p in RUNS.rglob("*") if p.is_file() and b"/Users/" in p.read_bytes()]


def test_the_dashboard_finds_every_run():
    assert len(discover_run_dirs(RUNS)) == 10
