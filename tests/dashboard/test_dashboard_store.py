"""Dashboard data layer: store accessors + the rebuildable registry cache."""

from __future__ import annotations

import json

import oaos2.dashboard.cache as cache_mod
from oaos2.dashboard import RegistryCache, arm_summary, filter_rows, list_runs, resolve_run_dir, run_detail
from oaos2.dashboard.store import facet_values
from tests.dashboard.conftest import PASSED_STATUS


def test_list_runs_rows_and_refs(build_run) -> None:
    build_run("r_pass", status=PASSED_STATUS)
    build_run("r_stall", deadlock=True, outcome=False)
    rows = list_runs(build_run.runs_root)
    assert [r["run_id"] for r in rows] == ["r_pass", "r_stall"]
    assert {r["run_id"]: r["status"] for r in rows} == {"r_pass": "passed", "r_stall": "stalled"}
    assert all(r["run_ref"] == f"exp/pack/{r['run_id']}" for r in rows)


def test_resolve_run_dir_containment(build_run) -> None:
    build_run("r1", status=PASSED_STATUS)
    root = build_run.runs_root
    assert resolve_run_dir(root, "exp/pack/r1") == (root / "exp" / "pack" / "r1").resolve()
    assert resolve_run_dir(root, "exp/pack/nope") is None          # not a run
    assert resolve_run_dir(root, "exp/pack") is None               # a dir, but no trace
    assert resolve_run_dir(root, "") is None                       # the root itself
    assert resolve_run_dir(root, "../..") is None                  # escape attempt
    assert resolve_run_dir(root, "exp/pack/r1/../../..") is None   # resolved escape attempt


def test_run_detail_scored_run(build_run) -> None:
    rd = build_run("r_pass", status=PASSED_STATUS)
    d = run_detail(rd)
    assert d["record"]["status"] == "passed"
    assert d["run_status"]["partial_score"] == 1.0
    assert d["manifest"]["organization_id"] == "pipeline"
    assert d["metrics"]["event_count"] > 0
    assert d["disposition"]["disposition"] == "completed"
    assert d["audit_classes"] == {}  # nothing irregular in this trace


def test_run_detail_killed_run_still_renders(build_run) -> None:
    rd = build_run("r_killed", terminal="incomplete", outcome=False)
    d = run_detail(rd)
    assert d["record"]["status"] == "incomplete"
    assert d["run_status"] is None and d["derived_files"] == []


def test_audit_classes_surface_trouble(build_run) -> None:
    rd = build_run("r_stall", deadlock=True, outcome=False)
    assert "run.deadlock_timeout" in run_detail(rd)["audit_classes"]


def test_filter_rows_facets_and_arms(build_run) -> None:
    pins = {"extensions": {"research_setup_sha256": "sha256:shared-setup"}}
    build_run("r_pass", status=PASSED_STATUS, manifest_extra=pins)
    build_run("r_fail", status={**PASSED_STATUS, "passed": False, "partial_score": 0.5, "cost_usd": 1.9},
              manifest_extra=pins)
    build_run("r_other", org="single_agent", outcome=False)
    rows = list_runs(build_run.runs_root)
    assert [r["run_id"] for r in filter_rows(rows, status="passed")] == ["r_pass"]
    assert [r["run_id"] for r in filter_rows(rows, organization="pipeline")] == ["r_fail", "r_pass"]
    assert [r["run_id"] for r in filter_rows(rows, q="OTH")] == ["r_other"]  # case-insensitive
    facets = facet_values(rows)
    assert facets["organization"] == ["pipeline", "single_agent"]
    assert "passed" in facets["status"]

    arms = arm_summary(filter_rows(rows, organization="pipeline"))
    assert len(arms) == 1
    a = arms[0]
    assert a["n_runs"] == 2 and a["n_passed"] == 1
    assert abs(a["mean_partial_score"] - 0.75) < 1e-9
    assert abs(a["total_cost_usd"] - 4.0) < 1e-9


# --- cache: memoized, invalidated, pruned, disposable ----------------------- #

def _counting(monkeypatch):
    calls = {"n": 0}
    real = cache_mod.run_record

    def counted(rd):
        calls["n"] += 1
        return real(rd)

    monkeypatch.setattr(cache_mod, "run_record", counted)
    return calls


def test_cache_reuses_unchanged_rows(build_run, monkeypatch) -> None:
    build_run("r1", status=PASSED_STATUS)
    build_run("r2", outcome=False)
    calls = _counting(monkeypatch)
    cache = RegistryCache(build_run.runs_root)
    first = cache.scan()
    assert calls["n"] == 2
    second = cache.scan()
    assert calls["n"] == 2  # nothing changed → no recompute
    assert second == first


def test_cache_invalidates_on_source_change(build_run, monkeypatch) -> None:
    rd = build_run("r1", status=PASSED_STATUS)
    cache = RegistryCache(build_run.runs_root)
    assert cache.scan()[0]["partial_score"] == 1.0
    calls = _counting(monkeypatch)
    (rd / "run_status.json").write_text(json.dumps({**PASSED_STATUS, "partial_score": 0.25}))
    assert cache.scan()[0]["partial_score"] == 0.25 and calls["n"] == 1


def test_cache_prunes_deleted_runs(build_run) -> None:
    import shutil

    rd = build_run("r1", status=PASSED_STATUS)
    build_run("r2", status=PASSED_STATUS)
    cache = RegistryCache(build_run.runs_root)
    assert len(cache.scan()) == 2
    shutil.rmtree(rd)
    assert [r["run_id"] for r in cache.scan()] == ["r2"]


def test_cache_corrupt_db_is_rebuilt(build_run) -> None:
    build_run("r1", status=PASSED_STATUS)
    cache = RegistryCache(build_run.runs_root)
    cache.scan()
    cache.db_path.write_text("not a sqlite file")  # disposable by contract
    assert [r["run_id"] for r in cache.scan(rebuild=False)] == ["r1"]


def test_cache_rebuild_flag_recomputes(build_run, monkeypatch) -> None:
    build_run("r1", status=PASSED_STATUS)
    cache = RegistryCache(build_run.runs_root)
    cache.scan()
    calls = _counting(monkeypatch)
    cache.scan(rebuild=True)
    assert calls["n"] == 1


def test_concurrent_cache_instances_do_not_delete_each_others_database(build_run) -> None:
    from concurrent.futures import ThreadPoolExecutor

    for i in range(6):
        build_run(f"r{i}", status=PASSED_STATUS)
    caches = [RegistryCache(build_run.runs_root), RegistryCache(build_run.runs_root)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda c: c.scan(), caches))
    assert [len(rows) for rows in results] == [6, 6]
    assert caches[0].db_path.is_file()
