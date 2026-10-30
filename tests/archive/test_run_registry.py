"""Run registry (DESIGN §17.3): classify every run's disposition from the trace
(completed/stalled/incomplete/failed) and merge the persisted score."""

from __future__ import annotations

import json
from pathlib import Path

from oaos2.archive import disposition, render_run_registry, run_record, scan_runs, write_registry
from oaos2.kernel.run_dir import RunDir
from oaos2.trace.spine import RunSpine


async def _run(tmp_path, run_id, *, terminal="completed", deadlock=False, agent_failed=False,
               wind_down=False, outcome=True, status=None) -> Path:
    rd = RunDir.create(tmp_path / "runs", "exp", "pack", run_id)
    rd.manifest_path.write_text(json.dumps({"run_id": run_id, "experiment_id": "exp",
                                            "organization_id": "pipeline", "mode": "pilot"}))
    spine = RunSpine(rd.root, run_id=run_id)
    await spine.start()
    c = await spine.emit_event("run.started", payload={"run_id": run_id})
    c = await spine.emit_event("turn.completed", agent_id="A", turn_id="A.t1", caused_by=c,
                               payload={"result": "finish_turn"})
    if agent_failed:
        await spine.emit_event("agent.failed", agent_id="A", caused_by=c, payload={"error": "boom"})
    if wind_down:
        await spine.emit_event("clock.wind_down", caused_by=c,
                               payload={"from_round": 10, "to_round": 12,
                                        "reason": "outcome open"})
    if deadlock:
        await spine.emit_event("run.deadlock_timeout", caused_by=c, payload={"timeout_s": 1})
    if outcome:
        await spine.emit_event("outcome.closed", caused_by=c, payload={"outcome_id": "main"})
    await spine.finalize("completed" if terminal != "failed" else "causality_violation")
    if terminal == "incomplete":
        # Faithfully simulate a killed/canceled run: the events were flushed but no
        # terminal record exists (the process died before finalize) — strip it.
        for name in ("events.jsonl", "infra.jsonl"):
            f = rd.root / "trace" / name
            if f.exists():
                kept = [ln for ln in f.read_text().splitlines()
                        if '"run.completed"' not in ln and '"run.failed"' not in ln]
                f.write_text("\n".join(kept) + ("\n" if kept else ""))
    if status is not None:
        (rd.root / "run_status.json").write_text(json.dumps(status))
    return rd.root


async def test_passed_run(tmp_path) -> None:
    await _run(tmp_path, "r_pass", status={"passed": True, "partial_score": 1.0,
                                           "archive_valid": True, "cost_usd": 2.1, "preset_id": "pipeline"})
    rec = run_record(tmp_path / "runs" / "exp" / "pack" / "r_pass")
    assert rec["status"] == "passed" and rec["partial_score"] == 1.0 and not rec["irregular"]


async def test_failed_score_run(tmp_path) -> None:
    await _run(tmp_path, "r_fail", status={"passed": False, "partial_score": 0.5, "archive_valid": True})
    rec = run_record(tmp_path / "runs" / "exp" / "pack" / "r_fail")
    assert rec["status"] == "failed_score"  # ran fine, did not succeed


async def test_explicitly_unscored_is_not_a_failed_score(tmp_path) -> None:
    await _run(tmp_path, "r_deferred", status={"scored": False, "passed": False,
                                                "partial_score": None, "archive_valid": True})
    rec = run_record(tmp_path / "runs" / "exp" / "pack" / "r_deferred")
    assert rec["status"] == "unscored" and rec["scored"] is False


async def test_unscored_when_no_outcome_or_status(tmp_path) -> None:
    await _run(tmp_path, "r_unscored", outcome=False, status=None)
    rec = run_record(tmp_path / "runs" / "exp" / "pack" / "r_unscored")
    assert rec["status"] == "unscored"


async def test_stalled_run(tmp_path) -> None:
    await _run(tmp_path, "r_stall", deadlock=True, outcome=False)
    rec = run_record(tmp_path / "runs" / "exp" / "pack" / "r_stall")
    assert rec["status"] == "stalled"


async def test_incomplete_run_no_terminal_record(tmp_path) -> None:
    await _run(tmp_path, "r_killed", terminal="incomplete")
    rec = run_record(tmp_path / "runs" / "exp" / "pack" / "r_killed")
    assert rec["status"] == "incomplete" and rec["disposition"] == "incomplete"


async def test_clock_wind_down_marks_run_censored_without_derived_report(tmp_path) -> None:
    await _run(tmp_path, "r_censored", wind_down=True, outcome=False)
    rec = run_record(tmp_path / "runs" / "exp" / "pack" / "r_censored")
    assert rec["censored"] is True


async def test_run_failed_terminal_is_irregular(tmp_path) -> None:
    await _run(tmp_path, "r_broken", terminal="failed", agent_failed=True)
    rec = run_record(tmp_path / "runs" / "exp" / "pack" / "r_broken")
    assert rec["status"] == "run_failed" and rec["irregular"] is True


async def test_disposition_pure_archive(tmp_path) -> None:
    root = await _run(tmp_path, "r_disp")
    d = disposition(root)
    assert d["disposition"] == "completed" and d["terminal"] == "run.completed"


async def test_scan_and_render_registry(tmp_path) -> None:
    await _run(tmp_path, "r1", status={"passed": True, "partial_score": 1.0, "archive_valid": True})
    await _run(tmp_path, "r2", deadlock=True, outcome=False)
    await _run(tmp_path, "r3", terminal="incomplete")
    rows = scan_runs(tmp_path / "runs")
    assert len(rows) == 3
    statuses = {r["run_id"]: r["status"] for r in rows}
    assert statuses == {"r1": "passed", "r2": "stalled", "r3": "incomplete"}
    table = render_run_registry(tmp_path / "runs")
    assert "passed" in table and "stalled" in table and "incomplete" in table
    counts = write_registry(tmp_path / "runs", jsonl=tmp_path / "reg.jsonl", csv_path=tmp_path / "reg.csv")
    assert counts == {"passed": 1, "stalled": 1, "incomplete": 1}
    assert len((tmp_path / "reg.jsonl").read_text().splitlines()) == 3
