"""The dashboard serves only this computer, keeps a run's files inside the run, restores a removed run only
under runs/, and works on a runs folder it cannot write (security and usability audits, October 29, 2026)."""
from __future__ import annotations

import os
import stat

import pytest
from fastapi.testclient import TestClient

from oaos2.dashboard.app import create_app


def _run(root):
    run = root / "s" / "e" / "pack" / "r1"
    (run / "trace").mkdir(parents=True)
    (run / "trace" / "events.jsonl").write_text("")
    (run / "derived").mkdir()
    return run


def test_a_request_must_name_this_computer(tmp_path):
    c = TestClient(create_app(tmp_path))
    assert c.get("/runs").status_code == 200
    assert c.get("/runs", headers={"host": "127.0.0.1:8722"}).status_code == 200
    assert c.get("/runs", headers={"host": "attacker.example:8722"}).status_code == 403


def test_a_change_from_another_sites_page_is_refused(tmp_path):
    c = TestClient(create_app(tmp_path))
    foreign = {"origin": "https://attacker.example"}
    assert c.post("/library/edit", data={"rel": "organizations/x.yaml", "content": "x"}, headers=foreign).status_code == 403
    assert c.post("/annotations/schema", data={}, headers={"referer": "https://attacker.example/p"}).status_code == 403


def test_a_link_out_of_the_run_folder_is_not_served(tmp_path):
    secret = tmp_path / "outside.txt"
    secret.write_text("secret")
    runs = tmp_path / "runs"
    run = _run(runs)
    os.symlink(secret, run / "derived" / "metrics.json")
    c = TestClient(create_app(runs))
    assert c.get("/run/s/e/pack/r1/derived/metrics.json").status_code == 404


def test_a_removed_run_is_restored_only_under_runs(tmp_path):
    from oaos2.dashboard.removal import restore_run
    runs = tmp_path / "runs"
    removed = runs / ".removed" / "R"
    (removed / "trace").mkdir(parents=True)
    (removed / "trace" / "events.jsonl").write_text("")
    with pytest.raises(FileNotFoundError):
        restore_run(runs, "sub/../../.removed/R")
    assert removed.exists()


def test_a_read_only_runs_folder_still_opens(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    runs = tmp_path / "runs"
    _run(runs)
    runs.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        c = TestClient(create_app(runs))
        assert c.get("/runs").status_code == 200
        assert not (runs / ".dashboard").exists() and (tmp_path / "cache" / "vivarium-dashboard").is_dir()
    finally:
        runs.chmod(stat.S_IRWXU)
