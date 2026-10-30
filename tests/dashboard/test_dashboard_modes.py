"""Registered experiments and exploratory work are shown apart, by the mode the run
manifest declares (DASHBOARD.md §4.1) — never inferred from a name."""

from __future__ import annotations

from fastapi.testclient import TestClient

from oaos2.dashboard.app import _mode_sections, create_app
from tests.dashboard.conftest import PASSED_STATUS


def _three(build_run) -> None:
    build_run("r_conf", experiment="zz_confirmatory_x", status=PASSED_STATUS,
              manifest_extra={"mode": "confirmatory"})
    build_run("r_pilot", experiment="pc1_smoke", status={**PASSED_STATUS, "passed": False,
                                                          "partial_score": 0.0},
              manifest_extra={"mode": "pilot"})
    build_run("r_nomode", experiment="parity", status=PASSED_STATUS, manifest_extra={"mode": None})


def test_sections_follow_the_declared_mode() -> None:
    rows = [{"mode": "confirmatory", "lineage": "a", "experiment_id": "budget_confirmatory_x", "status": "passed"},
            {"mode": "pilot", "lineage": "b", "experiment_id": "pc1_smoke", "status": "failed_score"},
            {"mode": "calibration", "lineage": "b", "experiment_id": "pc1_cal", "status": "incomplete"},
            {"mode": None, "lineage": "c", "experiment_id": "parity", "status": "unscored"},
            {"mode": "odd", "lineage": "c", "experiment_id": "parity", "status": "unscored"}]
    designs = [{"name": "budget_confirmatory",
                "resolved": {"preregistration_ref": "docs/experiments/budget_execution_prereg.md"}}]
    sec = _mode_sections(rows, designs, {"budget_execution_prereg.md": object()})
    assert (sec["n_registered"], sec["n_exploratory"], sec["n_undeclared"]) == (1, 2, 2)
    reg = sec["registered"][0]
    assert reg["design"] == "budget_confirmatory"  # prefix match on the runner's suffixed id
    assert reg["prereg_href"] == "/study-records/budget_execution_prereg.md" and reg["passed"] == 1
    exp = sec["exploratory"][0]
    assert exp["lineage"] == "b" and exp["modes"] == ["calibration", "pilot"] and exp["incomplete"] == 1
    assert sec["undeclared"][0]["modes"] == ["none", "odd"]


def test_runs_page_marks_registered_and_exploratory_rows(build_run) -> None:
    _three(build_run)
    client = TestClient(create_app(build_run.runs_root))
    html = client.get("/runs").text
    for run_id in ("r_conf", "r_pilot", "r_nomode"):            # one chronological list
        assert run_id in html
    assert "<strong>confirmatory</strong>" in html and "scope: registered experiments" in html
    # No pass/fail across experiments: both runs read completed, with eligibility beside it.
    assert "✓</span>passed" not in html and "○</span>completed" in html and ">eligible<" in html
    registered = client.get("/runs", params={"scope": "registered"}).text
    assert "r_conf" in registered and "r_pilot" not in registered
    lineage = client.get("/runs", params={"lineage": "zz_confirmatory_x"}).text
    assert "no preregistration found in the library" in lineage  # zz_confirmatory_x has no design here
    page = client.get("/experiment/pc1_smoke").text
    assert "Exploratory work" in page and "mode pilot" in page
    page = client.get("/experiment/zz_confirmatory_x").text
    assert "Registered experiment" in page and "mode confirmatory" in page


def test_blind_view_hides_result_verdicts_in_every_section(build_run) -> None:
    _three(build_run)
    client = TestClient(create_app(build_run.runs_root))
    html = client.get("/runs", params={"blind": 1}).text
    assert ">result<" not in html and "✓</span>passed" not in html and "1.000" not in html
