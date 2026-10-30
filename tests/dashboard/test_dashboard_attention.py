"""Run conditions are kept apart from archive notes (DASHBOARD.md §4.9a): a run page
shows what happened in the run, Record holds what changed around it, lists carry one
attention marker, and a large archive opens on its lineages."""

from __future__ import annotations

from fastapi.testclient import TestClient

from oaos2.dashboard import app as app_module
from oaos2.dashboard import attention
from oaos2.dashboard.app import create_app
from tests.dashboard.conftest import PASSED_STATUS


def test_conditions_are_recorded_facts_and_notes_are_archive_facts() -> None:
    record = {"status": "passed", "censored": True, "irregular": False}
    assert [c["key"] for c in attention.run_conditions(record)] == ["censored"]
    assert [c["key"] for c in attention.run_conditions({"status": "stalled"})] == ["unfinished"]
    assert attention.run_conditions({"status": "failed_score"}) == []  # a task result, not a condition

    failing = {"source": "error", "error": "PackError: current asset does not match run manifest"}
    assert attention.report_state(record, "current", {"source": "file", "error": None})["kind"] == "ok"
    assert attention.report_state(record, "stale_materials", failing)["kind"] == "not_recomputable"
    assert attention.report_state({"status": "incomplete"}, "stale_materials", failing)["kind"] == "unfinished"
    assert attention.report_state(record, "current", failing)["kind"] == "error"

    report = attention.report_state(record, "stale_materials", failing)
    notes = attention.archive_notes(record, "stale_materials", ["manifest changed"], report, source_dirty=True)
    assert [n["key"] for n in notes] == ["stale_materials", "source_dirty", "report_not_recomputable"]
    assert notes[0]["detail"] == ["manifest changed"] and failing["error"] in notes[2]["detail"]


def test_list_marker_ignores_archive_notes() -> None:
    stale = {"status": "passed", "provenance": "stale_materials", "source_dirty": True,
             "report_source": "error", "report_error": "drift"}
    assert attention.row_attention(stale) == []
    assert attention.row_attention({**stale, "provenance": "current"}) == ["report error"]
    assert attention.row_attention({"status": "run_failed", "irregular": True}) == ["irregular", "run failed"]


def test_material_versions_count_distinct_saved_pins() -> None:
    rows = [{"task_manifest_sha256": "a", "reference_sha256": "r"},
            {"task_manifest_sha256": "a", "reference_sha256": "r"},
            {"task_manifest_sha256": "b", "reference_sha256": "r"},
            {"task_manifest_sha256": None, "reference_sha256": "r"}]
    assert attention.material_versions(rows) == [
        {"field": "task_manifest_sha256", "label": "task manifest", "versions": [2, 1]}]
    assert attention.material_versions(rows[:2]) == []


def test_run_page_has_lines_not_banners_and_record_explains(build_run) -> None:
    build_run("r_old", experiment="exp_a", status=PASSED_STATUS,
              manifest_extra={"mode": "pilot", "extensions": {"source_dirty": True}})
    client = TestClient(create_app(build_run.runs_root))
    html = client.get("/runs").text
    ref = html.split('href="/run/')[1].split('"')[0]
    page = client.get(f"/run/{ref}").text
    assert 'class="banner' not in page
    assert "About the archive:" in page and "uncommitted source" in page and "details in Record" in page
    record = client.get(f"/run/{ref}/record").text
    assert 'id="archive-notes"' in record and "Launched from uncommitted code" in record


def test_large_archives_open_on_lineages_with_scope_and_attention(build_run, monkeypatch) -> None:
    build_run("r_conf", experiment="zz_confirmatory_x", status=PASSED_STATUS,
              manifest_extra={"mode": "confirmatory"})
    build_run("r_pilot", experiment="pc1_smoke", status=PASSED_STATUS, manifest_extra={"mode": "pilot"})
    client = TestClient(create_app(build_run.runs_root))
    assert "Studies and lineages" not in client.get("/runs").text          # a small archive lists every run
    monkeypatch.setattr(app_module, "INDEX_THRESHOLD", 0)
    index = client.get("/runs").text
    assert "Studies and lineages" in index and "list every run" in index
    assert "observed / horizon" not in index                    # the index lists no run table
    assert 'title="one run: opens it"' in index and "latest run" in index  # one click to a run
    assert "r_conf" in client.get("/runs", params={"flat": 1}).text
    registered = client.get("/runs", params={"scope": "registered", "flat": 1}).text
    assert "r_conf" in registered and "r_pilot" not in registered
    assert "r_conf" not in client.get("/runs", params={"attn": 1}).text  # nothing recorded to read first


def test_unfinished_runs_go_idle_after_two_days_without_touching_the_archive(tmp_path) -> None:
    import os
    import time

    from oaos2.dashboard import store
    trace = tmp_path / "run" / "trace"
    trace.mkdir(parents=True)
    stream = trace / "events.jsonl"
    stream.write_text("")
    fresh = store.apply_idle({"status": "incomplete"}, tmp_path / "run")
    assert fresh["status"] == "incomplete" and fresh["idle_minutes"] == 0
    old = time.time() - 3 * 86400
    os.utime(stream, (old, old))
    idle = store.apply_idle({"status": "incomplete"}, tmp_path / "run")
    assert idle["status"] == "idle" and idle["recorded_status"] == "incomplete"
    assert store.apply_idle({"status": "passed"}, tmp_path / "run") == {"status": "passed"}
    assert "unfinished" in [c["key"] for c in attention.run_conditions(idle)]


def test_an_idle_confirmatory_run_no_longer_holds_the_list_blind() -> None:
    rows = [{"mode": "confirmatory", "status": "idle", "experiment_id": "e", "lineage": "l"},
            {"mode": "confirmatory", "status": "passed", "experiment_id": "e", "lineage": "l"}]
    assert app_module._registry_reading_rows(rows)[1] is False
    rows[0]["status"] = "incomplete"
    assert app_module._registry_reading_rows(rows)[1] is True


def test_declared_studies_fold_lineages_and_nothing_is_inferred(tmp_path) -> None:
    import pytest

    from oaos2.dashboard import studies
    path = tmp_path / "studies.yaml"
    assert studies.load_studies(path) == []
    path.write_text("studies:\n  - id: pc1\n    title: PC1\n    lineages: ['pc1', 'pc1_*']\n")
    declared = studies.load_studies(path)
    assert studies.study_of("pc1_rivalry_rival_s5", declared)["id"] == "pc1"
    assert studies.study_of("pc10_other", declared) is None and studies.study_of(None, declared) is None
    lineage = lambda name, latest: {"lineage": name, "n": 1, "attention": 0, "posts": 2, "passed": 0,  # noqa: E731
                                    "failed_score": 1, "cost_usd": 1.5, "modes": ["pilot"], "packs": ["p"],
                                    "scopes": ["exploratory"], "first_day": "2026-09-16",
                                    "last_day": "2026-09-17", "latest": latest}
    index = app_module._study_index([lineage("pc1_a", 3.0), lineage("zeta", 2.0), lineage("pc1_b", 1.0)],
                                    declared, {})
    assert [(g["kind"], g.get("study") or g["lineage"]) for g in index] == [("study", "pc1"), ("lineage", "zeta")]
    assert index[0]["n"] == 2 and index[0]["cost_usd"] == 3.0 and len(index[0]["members"]) == 2
    path.write_text("studies:\n  - id: pc1\n    lineages: pc1_*\n")
    with pytest.raises(ValueError):
        studies.load_studies(path)


def test_runs_are_listed_by_start_time_with_the_run_link_first(build_run) -> None:
    from oaos2.dashboard.app import _run_time, _when
    early = {"run_id": "org__cell__rep00__01M1C39R8M4KGH3DCHPWRV7YBT"}
    late = {"run_id": "org__cell__rep00__01M2P55J68EAWH6F29RVR2J71A"}
    assert _run_time(early) < _run_time(late) and _when(_run_time(late)).startswith("2026-09-1")
    assert _run_time({"run_id": "anthropic_0", "run_dir": "/nonexistent"}) is None
    build_run("r_one", experiment="exp_a", status=PASSED_STATUS, manifest_extra={"mode": "pilot"})
    html = TestClient(create_app(build_run.runs_root)).get("/runs").text
    table = html[html.index("<tbody>"):]
    assert table.index("/story") < table.index("chip")          # when and run come before status
    assert "order: newest first" in html and "order: oldest first" in html
