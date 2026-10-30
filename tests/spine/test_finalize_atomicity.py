"""Finalize failure-atomicity (probe round 2, 2026-08-17): a dead writer must
not wedge finalize or abort's retry; the archive always ends in an
authoritative terminal (INV-5); a retry that contradicts a written
``run.completed`` supersedes it with a final ``run.failed``; and a failed
finalize leaves a writer-independent FINALIZE_FAILED marker."""

from __future__ import annotations

import asyncio
import json

import pytest

from oaos2.trace.emit import make_event
from oaos2.trace.invariants import InvariantReport, check_inv5
from oaos2.trace.spine import RunSpine


def _spine_events(run_dir):
    p = run_dir / "trace" / "events.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


async def test_dead_writer_does_not_hang_finalize_or_retry(tmp_path) -> None:
    # The probe's critical case: writer crashes with an item still queued —
    # join() must not be awaited forever, and the retry must stamp a terminal.
    spine = RunSpine(tmp_path / "run", run_id="r")

    async def dying_run_loop(queue):
        raise RuntimeError("writer died")

    spine.writer.run_loop = dying_run_loop  # type: ignore[method-assign]
    await spine.start()
    await spine.queue.put_blocking(make_event("run.started", "r"))  # never consumed

    with pytest.raises(RuntimeError, match="writer died"):
        await asyncio.wait_for(spine.finalize("completed"), timeout=10)
    # The failed attempt left a writer-independent floor marker.
    assert (tmp_path / "run" / "trace" / "FINALIZE_FAILED").exists()

    report = await asyncio.wait_for(spine.finalize("failed"), timeout=10)
    # The queued-but-never-appended event is a REAL loss: the report must say so…
    assert not report.ok
    # …but the archive still ends in a terminal record (the probe's core claim).
    events = _spine_events(tmp_path / "run")
    assert events and events[-1]["event_class"] == "run.failed"
    with pytest.raises(RuntimeError, match="already finalized"):
        await spine.finalize("failed")


async def test_completed_terminal_superseded_by_failed_retry(tmp_path) -> None:
    # Probe finding: invariants crash AFTER the completed terminal; the abort
    # retry must not leave the archive standing as "completed".
    import oaos2.trace.spine as spine_mod

    spine = RunSpine(tmp_path / "run", run_id="r")
    await spine.start()
    await spine.emit_event("run.started", payload={})

    real = spine_mod.run_invariants
    calls = {"n": 0}

    def crash_once(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("transient invariant-check failure")
        return real(*args, **kwargs)

    spine_mod.run_invariants = crash_once
    try:
        with pytest.raises(OSError):
            await spine.finalize("completed")
        report = await spine.finalize("failed")
    finally:
        spine_mod.run_invariants = real

    classes = [e["event_class"] for e in _spine_events(tmp_path / "run")
               if e["event_class"].startswith("run.")]
    # completed was already durably written; the retry SUPERSEDES it.
    assert classes[-2:] == ["run.completed", "run.failed"]
    assert report.ok  # INV-5 sanctions exactly this corrective shape


def test_inv5_terminal_shapes(tmp_path) -> None:
    trace = tmp_path / "trace"
    trace.mkdir(parents=True)

    def _write(classes):
        rows = [{"sequence_number": i, "event_class": c, "event_id": f"e{i}"}
                for i, c in enumerate(classes)]
        (trace / "events.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n")

    def _ok(classes):
        _write(classes)
        report = InvariantReport()
        check_inv5(tmp_path, report)
        return report.ok

    assert _ok(["run.started", "run.completed"])
    assert _ok(["run.started", "run.completed", "run.failed"])  # corrective
    assert not _ok(["run.started"])                              # no terminal
    assert not _ok(["run.completed", "turn.started"])            # terminal not last
    assert not _ok(["run.completed", "run.completed"])           # duplicate completeds
    assert not _ok(["run.failed", "run.completed"])              # contradiction ending completed
    assert not _ok(["run.completed", "run.failed", "run.failed"])  # >2 terminals


async def test_concurrent_finalize_is_serialized(tmp_path) -> None:
    spine = RunSpine(tmp_path / "run", run_id="r")
    await spine.start()
    await spine.emit_event("run.started", payload={})
    results = await asyncio.gather(spine.finalize("completed"),
                                   spine.finalize("completed"),
                                   return_exceptions=True)
    oks = [r for r in results if not isinstance(r, BaseException)]
    errs = [r for r in results if isinstance(r, BaseException)]
    assert len(oks) == 1 and len(errs) == 1  # second caller REFUSED, not duplicated
    assert "already finalized" in str(errs[0])
    classes = [e["event_class"] for e in _spine_events(tmp_path / "run")]
    assert classes.count("run.completed") == 1
