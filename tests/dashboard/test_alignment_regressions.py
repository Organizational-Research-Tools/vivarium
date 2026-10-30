"""Keep scientific condition identity and research claims intact in reader views."""
from copy import deepcopy
import json

from fastapi.testclient import TestClient
import pytest

from oaos2.dashboard import glossary, store
from oaos2.dashboard.app import create_app
from tests.dashboard.conftest import PASSED_STATUS


def _row(**changes):
    return dict(run_id="r1", experiment_id="study", organization_id="vertical",
                task_pack_id="pack", difficulty="programmable", clock_label="r16w3c4",
                model_ref="provider/model-a", role_model_refs={"officer": "provider/model-a"},
                mode="confirmatory", research_setup_sha256="sha256:setup-a",
                task_manifest_sha256="sha256:manifest-a", retained_fraction=1.0,
                scored=True, status="passed", **changes)


def test_condition_means_preserve_the_requirement_interaction():
    rows = []
    for org, tier, value in [("vertical", "programmable", 1.0),
                             ("vertical", "unprogrammable", 0.4),
                             ("lateral", "programmable", 0.7),
                             ("lateral", "unprogrammable", 0.7)]:
        row = _row()
        row.update(organization_id=org, difficulty=tier, retained_fraction=value)
        rows.append(row)
    before = deepcopy(rows)
    summaries = store.arm_summary(rows)
    means = {(r["organization_id"], r["difficulty"]): r["mean_retained"] for r in summaries}
    assert len(means) == 4
    interaction = (means["lateral", "unprogrammable"] - means["vertical", "unprogrammable"]
                   - means["lateral", "programmable"] + means["vertical", "programmable"])
    assert interaction == pytest.approx(0.6)
    assert rows == before


@pytest.mark.parametrize("changed", [
    {"model_ref": "provider/model-b"},
    {"role_model_refs": {"officer": "provider/model-b"}},
    {"mode": "pilot"},
    {"task_manifest_sha256": "sha256:manifest-b"},
    {"research_setup_sha256": "sha256:setup-b"},
    {"hidden_reference_sha256s": {"key": "sha256:new-answer"}},
    {"environment_schedule_sha256": "sha256:new-schedule"},
    {"clock_spec": {"calls_per_day": 32}},
    {"cap_output_tokens": 1000},
])
def test_summary_never_pools_distinct_saved_conditions(changed):
    first = _row()
    second = {**first, "run_id": "r2", **changed}
    # Both versions may share the same broad provenance category.
    first["provenance"] = second["provenance"] = "stale_materials"
    assert len(store.arm_summary([first, second])) == 2


def test_repetitions_pool_by_identity_without_dropping_failed_outcomes():
    first = _row()
    second = {**first, "run_id": "r2", "retained_fraction": 0.0,
              "status": "failed_score", "censored": True}
    summary, = store.arm_summary([first, second])
    assert summary["n_runs"] == 2 and summary["n_censored"] == 1
    assert summary["mean_retained"] == 0.5
    assert store.arm_summary([second, first]) == [summary]
    first.pop("research_setup_sha256")
    second.pop("research_setup_sha256")
    # A matching task manifest alone does not identify the complete setup.
    summaries = store.arm_summary([first, second])
    assert len(summaries) == 2 and all(not row["setup_pinned"] for row in summaries)


def test_cached_pins_reach_condition_table_and_blinding(build_run):
    for number, tier in enumerate(("programmable", "unprogrammable")):
        build_run(f"r{number}", experiment="study", org="vertical", status=PASSED_STATUS,
                  manifest_extra={"mode": "confirmatory", "extensions": {
                      "difficulty": tier, "research_setup_sha256": f"sha256:setup-{number}",
                      "environment_schedule_sha256": f"sha256:schedule-{number}",
                      "clock_spec": {"calls_per_day": 4}, "cap_output_tokens": 12345}})
    client = TestClient(create_app(build_run.runs_root))
    for _ in range(2):  # initial scan and cached rows must carry the same identity
        response = client.get("/runs", params={"experiment": "study"})
        assert response.status_code == 200
        summaries = store.arm_summary(store.list_runs(build_run.runs_root))
        assert {row["difficulty"] for row in summaries} == {"programmable", "unprogrammable"}
        assert all(row["material_pins"]["cap_output_tokens"] == 12345 for row in summaries)
        assert "Exploratory condition summaries" in response.text
        assert "registered exclusions and interaction tests are not applied" in response.text
        assert 'href="/study-records"' in response.text
        for number in (0, 1):
            assert f"sha256:setup-{number}" in response.text
    blind = client.get("/runs", params={"experiment": "study", "blind": 1})
    assert "outcome-blind" in blind.text
    assert "Exploratory condition summaries" not in blind.text
    assert "sha256:setup-0" not in blind.text
    assert "1.000" not in blind.text


def test_provenance_legend_uses_shared_definitions(build_run, monkeypatch):
    build_run("r", status=PASSED_STATUS)
    definitions = {key: f"Shared definition for {key}." for key in glossary.PROVENANCE_HELP}
    monkeypatch.setattr(glossary, "PROVENANCE_HELP", definitions)
    response = TestClient(create_app(build_run.runs_root)).get("/runs")
    for definition in definitions.values():
        assert definition in response.text
    assert "which results are REAL" not in response.text
    assert "never an arm result" not in response.text


def test_study_records_are_read_only_escaped_and_catalogue_bounded(tmp_path, monkeypatch):
    import oaos2.dashboard.app as app_module
    document = tmp_path / "example_prereg.md"
    original = "# Example preregistration\n\nDRAFT\n<script>alert('unsafe')</script>\n"
    document.write_text(original)
    monkeypatch.setattr(app_module, "_study_documents", lambda: {document.name: document})
    client = TestClient(create_app(tmp_path / "runs"))
    listing = client.get("/study-records")
    assert f'href="/study-records/{document.name}"' in listing.text
    response = client.get(f"/study-records/{document.name}")
    assert response.status_code == 200 and "DRAFT" in response.text
    assert "<script>alert" not in response.text and "&lt;script&gt;" in response.text
    assert client.get("/study-records/AGENTS.md").status_code == 404
    assert client.get("/study-records/%2e%2e%2fAGENTS.md").status_code == 404
    assert document.read_text() == original


def test_old_registry_cache_refreshes_for_new_setup_pins(build_run):
    import sqlite3
    from oaos2.dashboard.cache import RegistryCache, _CACHE_VERSION
    run_dir = build_run("cached", status=PASSED_STATUS,
                        manifest_extra={"extensions": {"research_setup_sha256": "sha256:setup"}})
    cache = RegistryCache(build_run.runs_root)
    cache.scan()
    with sqlite3.connect(cache.db_path) as con:
        con.execute(f"PRAGMA user_version = {_CACHE_VERSION - 1}")
        con.execute("UPDATE runs SET row_json = ?", (json.dumps({"run_dir": str(run_dir)}),))
    row, = cache.scan()
    assert row["research_setup_sha256"] == "sha256:setup"
