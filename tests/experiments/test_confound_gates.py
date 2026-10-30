"""Confound gates for a defensible comparison (DESIGN §15, §10.2, §19; M3 §2.1, M7 §4).

usd-basis parity across cells is only meaningful if the cost basis and the exposure
are held constant. These tests pin the gates confound_check must enforce beyond the
model-snapshot check: identical pricing-table (version + hash), identical
cache-breakpoint policy across live cells, and — in confirmatory mode — refusal of any
exposure-confounded cell. They also pin that a violation is reported with detail, not
just a boolean.
"""

from __future__ import annotations

import pytest

from oaos2.experiments.runner import CellResult
from oaos2.organizations.confound_check import ConfoundViolation, confound_check


def _cell(preset: str, **kw) -> CellResult:
    """A closed, archive-valid cell with sane parity defaults; override per test."""
    base = dict(
        closed=True, passed=False, label="unassisted", archive_valid=True,
        pricing_table_version="2026-06-01", pricing_table_hash="sha256:aaa",
        cache_policy_fingerprint="fp_live", exposure_confounded=False,
        runtime="raw_api",  # synthetic LIVE cells; the gate fail-closes on unstamped
    )
    base.update(kw)
    return CellResult(preset_id=preset, model_ref="anthropic/claude-sonnet-4-6", **base)


def test_baseline_two_cells_pass() -> None:
    confound_check([_cell("single_agent"), _cell("pipeline")], mode="confirmatory")


def test_closed_but_unscored_cell_is_refused() -> None:
    with pytest.raises(ConfoundViolation, match="did not close/score"):
        confound_check([_cell("single_agent"), _cell("pipeline", scored=False)],
                       mode="confirmatory")


def test_pricing_table_version_mismatch_is_refused() -> None:
    cells = [_cell("single_agent"), _cell("pipeline", pricing_table_version="2026-07-01")]
    with pytest.raises(ConfoundViolation, match="pricing-table version"):
        confound_check(cells, mode="confirmatory")


def test_pricing_table_hash_mismatch_is_refused() -> None:
    # Same declared version, but the table was edited in place → different hash.
    cells = [_cell("single_agent"), _cell("pipeline", pricing_table_hash="sha256:bbb")]
    with pytest.raises(ConfoundViolation, match="pricing-table hash"):
        confound_check(cells, mode="confirmatory")


def test_cache_breakpoint_policy_mismatch_is_refused() -> None:
    cells = [_cell("single_agent"), _cell("pipeline", cache_policy_fingerprint="fp_other")]
    with pytest.raises(ConfoundViolation, match="cache-breakpoint policy"):
        confound_check(cells, mode="confirmatory")


def test_offline_cells_with_no_cache_policy_are_exempt() -> None:
    # Offline cells make no model calls → carry None; all-None must NOT trip the gate.
    cells = [_cell("single_agent", cache_policy_fingerprint=None),
             _cell("pipeline", cache_policy_fingerprint=None)]
    confound_check(cells, mode="confirmatory")


def test_exposure_confounded_refused_in_confirmatory_but_allowed_in_pilot() -> None:
    cells = [_cell("single_agent"), _cell("pipeline", exposure_confounded=True)]
    with pytest.raises(ConfoundViolation, match="exposure-confounded"):
        confound_check(cells, mode="confirmatory")
    # Pilot/calibration run the cell stamped-confounded (the confound is on the archive).
    confound_check(cells, mode="pilot")


def test_confound_check_returns_intervention_facts() -> None:
    facts = confound_check([_cell("single_agent"), _cell("pipeline")], mode="confirmatory")
    assert isinstance(facts, dict)
    assert "intervention_rates" in facts and "recorded_rate_gap" in facts


def test_non_raw_api_runtime_barred_in_confirmatory() -> None:
    bad = _cell("pipeline")
    bad.runtime = "tool_runner"  # not the permitted raw_api loop (DESIGN §10.1/§24)
    with pytest.raises(ConfoundViolation, match="raw_api"):
        confound_check([_cell("single_agent"), bad], mode="confirmatory")
    # Outside confirmatory the runtime guard does not fire.
    confound_check([_cell("single_agent"), bad], mode="pilot")


def test_unstamped_runtime_fail_closes_in_confirmatory() -> None:
    # A cell with no runtime stamp (legacy/synthetic/offline-stub) must be BARRED —
    # a gate that passes on a missing field is author discipline, not enforcement.
    unstamped = _cell("pipeline", runtime=None)
    with pytest.raises(ConfoundViolation, match="unstamped"):
        confound_check([_cell("single_agent"), unstamped], mode="confirmatory")
    offline = _cell("pipeline", runtime="offline_stub")  # run_one's stamp
    with pytest.raises(ConfoundViolation, match="raw_api"):
        confound_check([_cell("single_agent"), offline], mode="confirmatory")


async def test_confirmatory_single_cell_requires_preregistration(tmp_path) -> None:
    # A lone confirmatory run_org_live must be bound to an existing prereg document —
    # previously only design-loaded sweeps were checked.
    from oaos2.experiments.runner import run_org_live
    from oaos2.organizations.presets import single_agent

    with pytest.raises(ValueError, match="preregistration_ref"):
        await run_org_live(single_agent(), tmp_path, tier="hard", mode="confirmatory",
                           experiment_id="exp_conf")
    with pytest.raises(FileNotFoundError, match="preregistration_ref"):
        await run_org_live(single_agent(), tmp_path, tier="hard", mode="confirmatory",
                           experiment_id="exp_conf",
                           preregistration_ref=str(tmp_path / "missing.md"))
    draft = tmp_path / "draft.md"
    draft.write_text("> STATUS: **DRAFT**\n")
    with pytest.raises(ValueError, match="STATUS: FINAL"):
        await run_org_live(single_agent(), tmp_path, tier="hard", mode="confirmatory",
                           experiment_id="exp_conf", preregistration_ref=str(draft))


async def test_treatment_defining_outside_declared_treatment_refused(tmp_path) -> None:
    from oaos2.kernel.run_dir import RunDir
    from oaos2.trace.spine import RunSpine

    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = RunSpine(rd.root, run_id="run1")
    await spine.start()
    await spine.emit_event("intervention.recorded", agent_id="a1",
                           payload={"kind": "forced_handoff", "class": "treatment_defining"})
    await spine.finalize("completed")
    offending = _cell("pipeline")
    offending.run_dir = rd.root  # archive carries a treatment_defining intervention, no declared treatment
    with pytest.raises(ConfoundViolation, match="treatment_defining"):
        confound_check([_cell("single_agent"), offending], mode="confirmatory")


def test_legacy_cells_without_parity_fields_still_checked_on_model_only() -> None:
    # Duck-typed callers may pass minimal results lacking the new fields; the older
    # model/archive/closure checks must still apply and the new ones simply skip.
    a = CellResult("single_agent", "m", True, True, "unassisted", True)
    b = CellResult("pipeline", "m2", True, True, "unassisted", True)  # different model
    with pytest.raises(ConfoundViolation, match="model snapshot"):
        confound_check([a, b], mode="confirmatory")


async def test_run_sweep_reports_confound_violation_detail(tmp_path, monkeypatch) -> None:
    # When a sweep's cells are confounded, the SweepResult carries the specific reason,
    # not just confound_ok=False (so the researcher sees WHY).
    from oaos2.experiments import runner as runner_mod
    from oaos2.experiments.design import ExperimentDesign

    design = ExperimentDesign(
        name="x.detail", task_pack="paper_replication",
        factors={"org_preset": ["single_agent", "pipeline"], "difficulty": ["hard"]},
        replications=1, mode="confirmatory", preregistration_ref="library/experiments/first_experiment_preregistration.md",
    )

    # Force a confound: make the two offline cells disagree on pricing-table version.
    real_run_one = runner_mod.run_one
    seen = {"n": 0}

    async def fake_run_one(*args, **kw):
        r = await real_run_one(*args, **kw)
        seen["n"] += 1
        if seen["n"] == 2:
            r.pricing_table_version = "2026-99-99"  # second cell drifts
        return r

    monkeypatch.setattr(runner_mod, "run_one", fake_run_one)
    sweep = await runner_mod.run_sweep(design, tmp_path, execution="offline", replications=1)
    assert not sweep.confound_ok
    assert sweep.confound_violation and "pricing-table version" in sweep.confound_violation


# --- mechanical (format/marker) interventions excluded from recorded-rate gap (T1.4) --- #

async def _cell_with_interventions(tmp_path, name, kinds):
    """A real archive-backed cell emitting intervention.recorded events of the given kinds."""
    from oaos2.kernel.run_dir import RunDir
    from oaos2.trace.spine import RunSpine
    rd = RunDir.create(tmp_path, "e", "p", name)
    spine = RunSpine(rd.root, run_id=name)
    await spine.start()
    c = await spine.emit_event("run.started", payload={})
    for kind in kinds:
        c = await spine.emit_event("intervention.recorded", caused_by=c,
                                   payload={"kind": kind, "class": "recorded"})
    await spine.finalize("completed")
    return _cell(name, run_dir=rd.root)


async def test_recorded_rate_gap_excludes_mechanical_interventions(tmp_path) -> None:
    # single_agent: 1 substantive recorded; pipeline: 3 MECHANICAL (submission-conformance)
    # recorded. The gap must see substantive parity (1 vs 0), not be inflated to 3 by the
    # benign shape-correction nudges.
    sa = await _cell_with_interventions(tmp_path / "sa", "single_agent", ["researcher_nudge"])
    pl = await _cell_with_interventions(tmp_path / "pl", "pipeline",
                                        ["submission_nonconformant_retry"] * 3)
    facts = confound_check([sa, pl], mode="pilot")
    assert facts["recorded_rate_gap"] == 1  # substantive: 1 (sa) vs 0 (pl), NOT 3
    assert facts["mechanical_recorded_rates"]["pipeline"] == 3
    assert facts["substantive_recorded_rates"]["single_agent"] == 1


async def test_intervention_reporting_preserves_every_replication(tmp_path) -> None:
    rep1 = await _cell_with_interventions(
        tmp_path / "rep1", "single_agent", ["researcher_nudge"])
    rep2 = await _cell_with_interventions(
        tmp_path / "rep2", "single_agent", ["researcher_nudge"] * 3)
    pipeline = await _cell_with_interventions(tmp_path / "pipeline", "pipeline", [])
    facts = confound_check([rep1, rep2, pipeline], mode="pilot")

    per_cell = facts["intervention_rates"]
    assert len(per_cell) == 3
    assert sorted(v["recorded"] for v in per_cell.values()
                  if v["preset_id"] == "single_agent") == [1, 3]
    sa = facts["intervention_rates_by_preset"]["single_agent"]
    assert sa["n_cells"] == 2 and sa["totals"]["recorded"] == 4
    assert facts["substantive_recorded_rates"]["single_agent"] == 2
    assert facts["recorded_rate_gap"] == 2


def test_capacity_check_uses_every_replication() -> None:
    from oaos2.organizations.confound_check import single_agent_capacity_check
    grouped = {
        "single_agent": [_cell("single_agent", passed=False),
                         _cell("single_agent", passed=True)],
        "context_expanded_single_agent": [_cell("context_expanded_single_agent", passed=False),
                                           _cell("context_expanded_single_agent", passed=False)],
    }
    with pytest.raises(ConfoundViolation, match="single_agent_passes.*1"):
        single_agent_capacity_check(grouped)
