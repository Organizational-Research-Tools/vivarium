"""Synthetic PC1 run folders for the batch and readout tests: the files those scripts read, nothing else."""

from __future__ import annotations

import json
from pathlib import Path


def make_run(exp_dir: Path, *, model_ref: str = "together/zai-org/GLM-5.3-Flash",
             preset: str = "pc1_supplier_g_xmodel3", seed: int = 14, end_reason: str | None = "scheduled",
             terminal: str | None = "run.completed", failed_reason: str | None = None, archive_valid: bool = True,
             status: bool = True, report: bool = True, work_events: list[dict] | None = None,
             late_events: list[dict] | None = None, reports: list[dict] | None = None,
             objections: dict | None = None, refused: int = 0, cost: float = 1.0) -> Path:
    """An experiment folder ``<exp>/materials_lab/<run_id>/`` with a trace, status and derived report.

    ``work_events`` are written before the observation period starts, ``late_events`` after it."""
    run_dir = Path(exp_dir) / "materials_lab" / "run_01"
    (run_dir / "trace").mkdir(parents=True)
    (run_dir / "derived").mkdir()
    (run_dir / "manifest.json").write_text("{}")
    events = list(work_events or [])
    if end_reason is not None:
        events.append({"event_class": "observation_period.started", "payload": {"reason": end_reason}})
    events += list(late_events or [])
    if terminal is not None:
        events.append({"event_class": terminal, "payload": {"reason": failed_reason} if failed_reason else {}})
    with (run_dir / "trace" / "events.jsonl").open("w") as fh:
        for i, e in enumerate(events):
            fh.write(json.dumps({"sequence_number": i, **e}) + "\n")
    if status:
        (run_dir / "run_status.json").write_text(json.dumps({
            "archive_valid": archive_valid, "closed": True, "cost_usd": cost, "model_ref": model_ref,
            "preset_id": preset}))
    if report:
        (run_dir / "derived" / "materials_lab_report.json").write_text(json.dumps({
            "end_reason": end_reason, "instance_seed": seed,
            "restricted_use": {"reports": list(reports or [])},
            "objections": objections or {"by_report": {}, "n_objected_by_concern": 0},
            "refusals": {"refused": refused, "share": 0.0, "ended_the_run": end_reason == "refusals_exceeded"}}))
    return run_dir


def unknown_usage() -> dict:
    return {"event_class": "model.invocation_failed", "payload": {"usage_status": "unknown", "error": "timeout"}}
