"""The registered derived-report seam (archive/renderers.py): a pack report is
written by render_archive beside the foundation files, isolated so a renderer
failure never costs the transcripts, and byte-identical on re-render."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oaos2.archive.export import render_archive
from oaos2.archive.renderers import (
    DerivedRenderer,
    derived_renderer_for,
    load_pack_report_file,
    register_derived_renderer,
    render_pack_report,
    report_text,
    unregister_derived_renderer,
)
from oaos2.archive.transcript import events_in_order
from oaos2.kernel.run_dir import RunDir
from oaos2.trace.spine import RunSpine


async def _archive(tmp_path: Path, pack: str) -> Path:
    rd = RunDir.create(tmp_path / "runs", "exp", pack, "r1")
    rd.manifest_path.write_text(json.dumps({"run_id": "r1", "experiment_id": "exp",
                                            "organization_id": "o", "mode": "pilot",
                                            "task_pack_id": pack}))
    spine = RunSpine(rd.root, run_id="r1")
    await spine.start()
    c = await spine.emit_event("run.started", payload={"run_id": "r1"})
    await spine.emit_event("clock.round", caused_by=c, payload={"round_no": 1, "rounds_total": 2})
    await spine.emit_event("outcome.closed", caused_by=c, payload={"outcome_id": "main"})
    await spine.finalize("completed")
    return rd.root


def _counting(pack: str, *, fail: bool = False) -> DerivedRenderer:
    def render(run_dir: Path, events: list[dict]) -> dict:
        if fail:
            raise RuntimeError("pins drifted")
        return {"n_events": len(events), "rounds": [e["payload"]["round_no"] for e in events
                                                    if e["event_class"] == "clock.round"]}

    return DerivedRenderer(pack_id=pack, filename=f"{pack}_trace.json", render=render,
                           summary=lambda r: {"retained_fraction": 1.0 / r["n_events"]})


@pytest.fixture
def pack():
    name = "seampack"
    unregister_derived_renderer(name)
    yield name
    unregister_derived_renderer(name)


async def test_render_archive_writes_registered_report_and_is_deterministic(tmp_path, pack) -> None:
    register_derived_renderer(_counting(pack))
    run = await _archive(tmp_path, pack)
    first = {f.name: f.read_bytes() for f in render_archive(run).iterdir()}
    assert f"{pack}_trace.json" in first and "clean.txt" in first and "metrics.json" in first
    second = {f.name: f.read_bytes() for f in render_archive(run).iterdir()}
    assert first == second
    report = load_pack_report_file(run)
    assert report["rounds"] == [1]
    # the file is exactly what the in-memory render serializes to — one serialization path
    out = render_pack_report(run, events_in_order(run))
    assert out["source"] == "rendered" and report_text(out["report"]) == (run / "derived" / f"{pack}_trace.json").read_text()
    assert derived_renderer_for(pack).identity.startswith("sha256:")


async def test_failing_renderer_is_isolated_and_named(tmp_path, pack) -> None:
    register_derived_renderer(_counting(pack, fail=True))
    run = await _archive(tmp_path, pack)
    derived = render_archive(run)
    for f in ("clean.txt", "full.txt", "agent_centric.txt", "file_lineage.txt", "metrics.json"):
        assert (derived / f).exists(), f"foundation file {f} lost to a pack failure"
    assert not (derived / f"{pack}_trace.json").exists()
    err = (derived / f"RENDER_ERROR.{pack}_trace.json.txt").read_text()
    assert pack in err and "pins drifted" in err
    out = render_pack_report(run, events_in_order(run))
    assert out["source"] == "error" and "pins drifted" in out["error"] and out["report"] is None


async def test_unregistered_pack_renders_nothing_extra(tmp_path) -> None:
    run = await _archive(tmp_path, "nopack")
    names = {f.name for f in render_archive(run).iterdir()}
    assert names == {"clean.txt", "full.txt", "agent_centric.txt", "file_lineage.txt", "metrics.json"}
    assert render_pack_report(run, events_in_order(run))["source"] is None


async def test_registry_row_falls_back_to_a_render_at_head(tmp_path, pack) -> None:
    from oaos2.archive.registry import run_record
    register_derived_renderer(_counting(pack))
    run = await _archive(tmp_path, pack)
    row = run_record(run)
    assert row["report_source"] == "rendered" and row["retained_fraction"] == pytest.approx(1 / 4)
    assert row["report_identity"].startswith("sha256:")
    assert not (run / "derived").exists() or not list((run / "derived").iterdir())  # the registry never writes
    render_archive(run)
    assert run_record(run)["report_source"] == "file"
