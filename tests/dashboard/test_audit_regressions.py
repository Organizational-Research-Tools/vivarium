"""Research-facing regressions: spend caps, blind views, caches and config edits."""
from __future__ import annotations

import csv
import io

import pytest
from fastapi.testclient import TestClient

from oaos2.dashboard import workbench
from oaos2.dashboard.app import create_app
from oaos2.dashboard.search import SearchIndex
from tests.dashboard.conftest import PASSED_STATUS


@pytest.mark.parametrize("cap", ["nan", "inf", "-inf", "1e309", "0", "-1", ""])
def test_live_post_rejects_unbounded_or_nonpositive_cap(tmp_path, monkeypatch, cap):
    monkeypatch.setattr(workbench, "list_library", lambda: {"experiments": [{"name": "synthetic"}]})
    def forbidden_launch(*args, **kwargs):
        pytest.fail("invalid cap reached launch")
    monkeypatch.setattr(workbench, "launch", forbidden_launch)
    client = TestClient(create_app(tmp_path))
    response = client.post("/launch", data={"design": "synthetic", "execution": "live",
                                           "confirm": "RUN LIVE", "cap_usd": cap})
    assert response.status_code == 400
    assert "finite, positive" in response.text


@pytest.mark.parametrize("cap", [None, float("nan"), float("inf"), 0, -1])
def test_direct_live_launch_rejects_invalid_cap_before_subprocess(tmp_path, monkeypatch, cap):
    def forbidden_process(*args, **kwargs):
        pytest.fail("invalid cap reached subprocess")
    monkeypatch.setattr(workbench.subprocess, "Popen", forbidden_process)
    with pytest.raises((ValueError, TypeError)):
        workbench.launch(tmp_path, design="synthetic", execution="live", cap_usd=cap)
    assert not (tmp_path / ".dashboard").exists()


def test_blind_registry_masks_statuses_and_csv_before_filtering(build_run):
    for run_id, passed in (("done_a", True), ("done_b", False)):
        build_run(run_id, experiment="study", org="finished_arm",
                  status={**PASSED_STATUS, "passed": passed, "partial_score": 0.87654321},
                  manifest_extra={"mode": "confirmatory"})
    build_run("ongoing", experiment="study", org="other_arm", terminal="incomplete",
              outcome=False, manifest_extra={"mode": "confirmatory"})
    build_run("unrelated", experiment="other", status=PASSED_STATUS)
    client = TestClient(create_app(build_run.runs_root))
    params = {"experiment": "study", "organization": "finished_arm", "status": "passed"}
    response = client.get("/runs", params=params)
    assert response.status_code == 200
    html = response.text
    assert "outcome-blind" in html
    assert "done_a" in html and "done_b" in html
    assert '</span>passed' not in html and '</span>failed_score' not in html
    assert 'value="passed"' not in html and 'value="failed_score"' not in html
    assert 'status=passed' not in html and 'status=failed_score' not in html
    assert 'name="blind" value="1"' in html
    assert 'href="/runs?blind=1"' in html
    assert '/cases?mode=blind' in html
    exported = list(csv.DictReader(io.StringIO(client.get("/registry.csv", params=params).text)))
    assert {row["run_id"] for row in exported} == {"done_a", "done_b"}
    for row in exported:
        assert row["status"] == "completed"
        assert row["passed"] == row["partial_score"] == row["retained_fraction"] == ""
    # A separate, completed study retains its normal explicitly selected reading view.
    open_rows = list(csv.DictReader(io.StringIO(client.get("/registry.csv", params={"experiment": "other"}).text)))
    assert open_rows[0]["partial_score"] == "1.0"
    blind_rows = list(csv.DictReader(io.StringIO(client.get("/registry.csv", params={"experiment": "other", "blind": 1}).text)))
    assert blind_rows[0]["partial_score"] == ""


@pytest.mark.parametrize("relative", ["captured/agents/a/correspondence/letter.json",
                                      "captured/submitted/final.json", "submitted/final.json"])
def test_search_tracks_indexed_files_without_pack_renderer(build_run, relative):
    run_dir = build_run("searchable")  # synthetic pack intentionally has no report renderer
    index = SearchIndex(build_run.runs_root)
    rows = [{"run_dir": str(run_dir), "run_ref": "exp/pack/searchable"}]
    assert index.ensure(rows, lambda _: []) == {"indexed": 1, "reused": 0}
    path = run_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"text": "oldneedle"}')
    assert index.ensure(rows, lambda _: [])["indexed"] == 1
    assert len(index.query("oldneedle", [str(run_dir)])) == 1
    path.write_text('{"text": "replacementneedle"}')
    assert index.ensure(rows, lambda _: [])["indexed"] == 1
    assert not index.query("oldneedle", [str(run_dir)])
    assert len(index.query("replacementneedle", [str(run_dir)])) == 1
    assert index.ensure(rows, lambda _: []) == {"indexed": 0, "reused": 1}
    path.unlink()
    assert index.ensure(rows, lambda _: [])["indexed"] == 1
    assert not index.query("replacementneedle", [str(run_dir)])


def test_task_edit_validates_all_declared_profiles_without_legacy_default(tmp_path, monkeypatch):
    lib = tmp_path / "library"
    task = lib / "tasks" / "custom"
    task.mkdir(parents=True)
    monkeypatch.setenv("OAOS2_LIBRARY", str(lib))
    manifest = """pack_id: custom
task_id: custom
prompts: {}
evaluators: {schema_validator: {}}
public_feedback: {schema_id: custom, allowed_fields: [], forbidden_substrings: []}
contracts:
  single_results:
    commitments: [{id: final, committer_roles: [solo], evaluator: schema_validator}]
  specialized:
    commitments: [{id: final, committer_roles: [solo], evaluator: schema_validator}]
"""
    path = task / "manifest.yaml"
    path.write_text(manifest)
    edited = manifest + "\n# A valid editorial change\n"
    ok, msg = workbench.save_validated("tasks/custom/manifest.yaml", edited)
    assert ok, msg
    assert path.read_text() == edited
    invalid = edited.replace("  specialized:\n    commitments:", "  specialized:\n    misspelled_commitments:")
    ok, msg = workbench.save_validated("tasks/custom/manifest.yaml", invalid)
    assert not ok and "REVERTED" in msg
    assert path.read_text() == edited


def test_role_scopes_are_resolved_and_displayed_not_marked_ignored(tmp_path, monkeypatch):
    lib = tmp_path / "library"
    orgs = lib / "organizations"
    orgs.mkdir(parents=True)
    monkeypatch.setenv("OAOS2_LIBRARY", str(lib))
    (orgs / "scoped.yaml").write_text("""preset_id: scoped
roles:
  - role_id: solo
    plays: [solo]
    packet_scopes: [health, housing]
""")
    org = workbench.list_library()["organizations"][0]
    assert org["resolved"]["roles"][0]["packet_scopes"] == ["health", "housing"]
    assert "roles[].packet_scopes" not in org["ignored_keys"]
    page = TestClient(create_app(tmp_path / "runs")).get("/library")
    assert "additional notice scopes: health, housing" in page.text


def test_org_edit_rejects_invalid_structure_and_preserves_previous_file(tmp_path, monkeypatch):
    lib = tmp_path / "library"
    orgs = lib / "organizations"
    orgs.mkdir(parents=True)
    monkeypatch.setenv("OAOS2_LIBRARY", str(lib))
    path = orgs / "tiny.yaml"
    original = "preset_id: tiny\nroles:\n  - role_id: solo\n    plays: [solo]\n"
    path.write_text(original)
    invalid = original + "topology:\n  channels:\n    - {from_role: solo, to_role: absent}\n"
    ok, message = workbench.save_validated("organizations/tiny.yaml", invalid)
    assert not ok and "unknown role" in message
    assert path.read_text() == original
    from oaos2.organizations.loader import load_org_spec
    assert load_org_spec("tiny").roles[0].role_id == "solo"
