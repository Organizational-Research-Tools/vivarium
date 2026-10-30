"""Property gates for the repaired sweep seams (repair item 7).

These pin the audit-round failure classes end to end, on the CANONICAL
run_sweep path (fake backend + the plugin's perfect-play stub — no Docker,
no spend):

- multi-horizon sweeps land in unique archives with the horizon stamped;
- canonical instrument files are byte-identical after a sweep (sweeps read
  committed variant assets — they never mutate sources);
- distinct horizons are distinct confound-gate factor cells;
- a refused clocked preflight stages nothing (no container, no trace).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from oaos2.experiments.design import ExperimentDesign, ParityPolicy
from oaos2.experiments.runner import run_org_live, run_sweep
from oaos2.library import library_dir
from oaos2.organizations.loader import load_org_spec
from oaos2.tasks.clock import InvalidClockSpec

try:
    from oaos2.docker.backend import FakeContainerBackend
    _HAVE_FAKE = True
except Exception:  # pragma: no cover
    _HAVE_FAKE = False

pytestmark = pytest.mark.skipif(not _HAVE_FAKE, reason="FakeContainerBackend unavailable")

_PACK_DIR = library_dir() / "tasks" / "budget_execution"
_CANONICAL = [_PACK_DIR / "manifest.yaml",
              _PACK_DIR / "assets" / "hidden" / "schedule_unprogrammable.json",
              _PACK_DIR / "assets" / "hidden" / "schedule_programmable.json"]


def _stub():
    from oaos2.tasks.plugins.budget_execution.offline_stub import (
        ClockedPerfectPlayStub,
    )
    return ClockedPerfectPlayStub


def _clock_factor(rounds_total: int, variant: str | None,
                  name: str | None = None) -> dict:
    # The horizon formula is imported from its ONE owner, never restated
    # (audit round 6 P2-4: a local copy is the drift vector the owner kills).
    from oaos2.tasks.plugins.budget_execution.clock_horizon import (
        plan_deadline_rounds,
    )
    return {"name": name or f"r{rounds_total}", "rounds_total": rounds_total,
            "plan_deadline_rounds": plan_deadline_rounds(rounds_total),
            "schedule_variant": variant, "megabatch": False}


async def test_multi_horizon_sweep_unique_archives_and_untouched_sources(tmp_path) -> None:
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in _CANONICAL}
    design = ExperimentDesign(
        name="clock_props", task_pack="budget_execution",
        factors={"org_preset": ["budget_execution_solo_clocked"],
                 "difficulty": ["unprogrammable"],
                 "model": ["stub/deterministic"],
                 "clock": [_clock_factor(24, None), _clock_factor(36, "r36")]},
        mode="calibration", platform_seed=1,
        parity_policy=ParityPolicy(regime="budget_matched"))
    sweep = await run_sweep(design, tmp_path, execution="live",
                            backend=FakeContainerBackend(digest="sha256:fake"),
                            adapter_factory=_stub())
    # Unique archives, horizon stamped, both cells whole (the r24/r36
    # collision was audit round 4 P1-3).
    assert sorted(r.rounds_total for r in sweep.results) == [24, 36]
    run_dirs = {r.run_dir for r in sweep.results}
    assert len(run_dirs) == 2 and all(r.archive_valid for r in sweep.results)
    for r in sweep.results:
        assert (r.run_dir / "manifest.json").is_file()
        assert f"__r{r.rounds_total}__" in r.run_dir.name  # legible variant tag
    # Distinct horizons are distinct factor cells for the confound gate.
    factor_keys = set(sweep.results_by_factor)
    assert len(factor_keys) == 2
    assert any("'r24'" in k for k in factor_keys)
    assert any("'r36'" in k for k in factor_keys)
    # Sweeps read committed variant assets; canonical sources are untouched.
    after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in _CANONICAL}
    assert after == before


async def test_burstiness_variants_at_one_horizon_stay_distinct(
        tmp_path, monkeypatch) -> None:
    """The exact audit-round-5 P1-1 failure shape: TWO burstiness variants at
    the SAME horizon (r24w7 vs r24w3) must stay distinct conditions in every
    aggregation surface — factor cells, headline, parity, run_status — and
    carry diverging apparatus fingerprints. The w3 variant is authored into a
    COPIED library (the canonical one is never touched)."""
    import json
    import os
    import shutil
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[2]
    workdir = tmp_path / "authoring"
    shutil.copytree(repo / "library", workdir / "library")
    stamp = subprocess.run(
        [sys.executable, str(repo / "scripts" / "stamp_budget_clock_schedule.py"),
         "--variant", "r24w3", "--rounds-total", "24", "--wave-rounds", "3"],
        cwd=workdir, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(repo)})
    assert stamp.returncode == 0, stamp.stderr
    monkeypatch.setenv("OAOS2_LIBRARY", str(workdir / "library"))

    design = ExperimentDesign(
        name="clock_burst", task_pack="budget_execution",
        factors={"org_preset": ["budget_execution_solo_clocked"],
                 "difficulty": ["unprogrammable"],
                 "model": ["stub/deterministic"],
                 "clock": [_clock_factor(24, None, name="r24w7"),
                           _clock_factor(24, "r24w3", name="r24w3")]},
        mode="calibration", platform_seed=1,
        parity_policy=ParityPolicy(regime="budget_matched"))
    sweep = await run_sweep(design, tmp_path / "runs", execution="live",
                            backend=FakeContainerBackend(digest="sha256:fake"),
                            adapter_factory=_stub())
    assert len(sweep.results) == 2
    by_label = {r.clock_label: r for r in sweep.results}
    assert set(by_label) == {"r24w7", "r24w3"}
    # Same horizon — the label alone must separate every aggregation surface.
    assert len(set(sweep.results_by_factor)) == 2
    parity = sweep.parity_facts["by_regime"]["budget_matched"]["by_factor"]
    assert len(parity) == 2
    # budget_execution scores archive-side (v2.1) and declares no headline
    # evaluator, so headline_by_factor is empty here; when a pack does produce
    # headline scores the key carries clock_label (same tuple as factor_scores).
    assert all("r24w" in key for key in map(str, parity))
    if sweep.headline_by_factor:
        assert len(set(sweep.headline_by_factor)) == 2
    # Persistence + apparatus identity diverge per cell.
    fingerprints = set()
    for label, r in by_label.items():
        status = json.loads((r.run_dir / "run_status.json").read_text())
        assert status["clock_label"] == label and status["rounds_total"] == 24
        ext = json.loads((r.run_dir / "manifest.json").read_text())["extensions"]
        assert ext["environment_schedule_variant"] == (
            "r24w3" if label == "r24w3" else None)
        fingerprints.add(ext["apparatus_sha256"])
    assert len(fingerprints) == 2  # burstiness IS apparatus identity


async def test_refused_clocked_preflight_stages_nothing(tmp_path) -> None:
    # A mis-authored preset that pins one tier's profile as a bare string is
    # caught by the per-profile tier guard (profile_tiers, estimand correction
    # 2026-08-27) — the per-case slots would not match the cell's schedule.
    backend = FakeContainerBackend(digest="sha256:fake")
    spec = load_org_spec("budget_execution_solo_clocked")
    spec.live_coordination = {"contract_profile": "single_results_clocked"}
    with pytest.raises(InvalidClockSpec):
        await run_org_live(
            spec, tmp_path,
            tier="programmable",  # single_results_clocked is unprogrammable-built
            model_ref="stub/deterministic", task_pack="budget_execution",
            experiment_id="exp_preflight", backend=backend,
            adapter_factory=_stub())
    assert backend.calls == []  # no container ever ran
    assert not list(Path(tmp_path).rglob("events.jsonl"))  # spine never started


async def test_missing_tier_entry_in_profile_mapping_refused(tmp_path) -> None:
    # A tier-keyed contract_profile mapping without the cell's tier fails
    # closed BEFORE the pack loads — never a silent fallback profile.
    backend = FakeContainerBackend(digest="sha256:fake")
    with pytest.raises(ValueError, match="has no entry"):
        await run_org_live(
            load_org_spec("budget_execution_solo_clocked"), tmp_path,
            tier="hard",  # not a budget_execution tier
            model_ref="stub/deterministic", task_pack="budget_execution",
            experiment_id="exp_preflight", backend=backend,
            adapter_factory=_stub())
    assert backend.calls == []
    assert not list(Path(tmp_path).rglob("events.jsonl"))


def test_headline_grouping_separates_clock_labels() -> None:
    """Direct gate on the headline grouping (audit round 7 P2-5): the sweep
    property tests use a pack that scores archive-side, so this exercises
    _headline_facts with synthetic scored cells — two burstiness labels at one
    horizon must produce two headline entries, never one average."""
    from oaos2.experiments.runner import CellResult, _headline_facts

    def _cell(label, score):
        return CellResult(
            preset_id="solo", model_ref="m", closed=True, passed=True,
            label="unassisted", archive_valid=True, scored=True,
            partial_score=score, difficulty="unprogrammable",
            rounds_total=24, clock_label=label)

    by_factor, headline = _headline_facts(
        [_cell("r24w7", 0.9), _cell("r24w3", 0.5)])
    assert len(by_factor) == 2
    scores = {key[4]: value for key, value in by_factor.items()}
    assert scores == {"r24w7": 0.9, "r24w3": 0.5}
    # The flat headline view carries the label too — same horizon, distinct keys.
    assert {k for k in headline} == {"solo|difficulty=unprogrammable|model=m"
                                    "|context=None|clock=r24w7",
                                    "solo|difficulty=unprogrammable|model=m"
                                    "|context=None|clock=r24w3"}
