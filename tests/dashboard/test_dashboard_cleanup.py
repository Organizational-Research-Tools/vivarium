"""Removing dead runs (DASHBOARD.md §4.9c): which runs count as dead, which stay, and
that removal moves a run out of the scanned archive unchanged and restore brings it back."""

from __future__ import annotations

import os
import time

import pytest

from oaos2.dashboard import removal, store
from tests.dashboard.conftest import PASSED_STATUS

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from oaos2.dashboard.app import create_app  # noqa: E402


def _age(run_dir, minutes: float) -> None:
    """Make a run's trace look last written ``minutes`` ago."""
    t = time.time() - minutes * 60
    for p in (run_dir / "trace").iterdir():
        if p.is_file():
            os.utime(p, (t, t))


def _row(build_run, run_id):
    return next(r for r in store.list_runs(build_run.runs_root) if r["run_id"] == run_id)


def test_dead_reasons(build_run) -> None:
    build_run("r_pass", status=PASSED_STATUS)
    build_run("r_stall", deadlock=True, outcome=False)
    build_run("r_failed", terminal="failed", outcome=False)
    build_run("r_crash", status=PASSED_STATUS, extra_events=[("agent.failed", {"agent_id": "A", "payload": {}})])
    assert removal.dead_reason(_row(build_run, "r_pass")) is None
    assert "stalled" in removal.dead_reason(_row(build_run, "r_stall"))
    assert "failed" in removal.dead_reason(_row(build_run, "r_failed"))
    assert "collapsed" in removal.dead_reason(_row(build_run, "r_crash"))


def test_unfinished_run_is_dead_only_once_quiet(build_run) -> None:
    rd = build_run("r_killed", terminal="incomplete", outcome=False)
    assert removal.dead_reason(_row(build_run, "r_killed")) is None  # may still be running
    _age(rd, removal.QUIET_MINUTES + 1)
    assert "without finishing" in removal.dead_reason(_row(build_run, "r_killed"))


def test_confirmatory_and_frozen_runs_are_kept(build_run) -> None:
    build_run("r_conf", deadlock=True, outcome=False, manifest_extra={"mode": "confirmatory"})
    dead, protected = removal.removable(_row(build_run, "r_conf"))
    assert dead and "confirmatory" in protected
    row = {**_row(build_run, "r_conf"), "mode": "pilot", "in_frozen_dataset": True}
    assert "frozen" in removal.removable(row)[1]


@pytest.fixture
def client(build_run):
    build_run("r_pass", status=PASSED_STATUS)
    build_run("r_stall", deadlock=True, outcome=False)
    build_run("r_conf", deadlock=True, outcome=False, manifest_extra={"mode": "confirmatory"})
    return TestClient(create_app(build_run.runs_root))


def test_cleanup_page_lists_dead_runs_only(client) -> None:
    html = client.get("/cleanup").text
    assert "r_stall" in html and "r_conf" in html
    assert "r_pass" not in html
    assert "Dead but kept" in html


def test_remove_then_restore_round_trip(client, build_run) -> None:
    root = build_run.runs_root
    ref = _row(build_run, "r_stall")["run_ref"]
    events_before = (root / ref / "trace" / "events.jsonl").read_bytes()

    r = client.post("/cleanup/remove", data={"run_ref": ref}, follow_redirects=False)
    assert r.status_code == 303
    assert not (root / ref).exists()
    moved = root / removal.REMOVED_DIR / ref
    assert (moved / "trace" / "events.jsonl").read_bytes() == events_before  # unchanged
    assert "r_stall" not in [x["run_id"] for x in store.list_runs(root)]
    assert client.get(f"/run/{ref}").status_code == 404
    assert [x["run_ref"] for x in removal.list_removed(root)] == [ref]

    r = client.post("/cleanup/restore", data={"run_ref": ref}, follow_redirects=False)
    assert r.status_code == 303
    assert (root / ref / "trace" / "events.jsonl").read_bytes() == events_before
    assert removal.list_removed(root) == []
    assert "r_stall" in [x["run_id"] for x in store.list_runs(root)]


def test_remove_refuses_live_good_and_protected_runs(client, build_run) -> None:
    for run_id in ("r_pass", "r_conf"):
        ref = _row(build_run, run_id)["run_ref"]
        assert client.post("/cleanup/remove", data={"run_ref": ref}).status_code == 400
        assert (build_run.runs_root / ref).exists()
    assert client.post("/cleanup/remove", data={"run_ref": "../outside"}).status_code == 400


def test_run_page_offers_removal_for_a_dead_run(client, build_run) -> None:
    assert "Remove this run" in client.get(f"/run/{_row(build_run, 'r_stall')['run_ref']}").text
    assert "Remove this run" not in client.get(f"/run/{_row(build_run, 'r_pass')['run_ref']}").text
    conf = client.get(f"/run/{_row(build_run, 'r_conf')['run_ref']}").text
    assert "Dead run" in conf and "Remove this run" not in conf
