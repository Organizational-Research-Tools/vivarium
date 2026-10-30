"""Dashboard web app: registry page, run overview, derived-file serving, 404s.

Skips cleanly when the ``dashboard`` extra (fastapi) isn't installed — the data
layer has its own stdlib-only tests."""

from __future__ import annotations

import json

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402  (needs the importorskip above)

from oaos2.dashboard.app import create_app  # noqa: E402
from tests.dashboard.conftest import PASSED_STATUS  # noqa: E402


@pytest.fixture
def client(build_run):
    build_run("r_pass", status=PASSED_STATUS)
    build_run("r_stall", deadlock=True, outcome=False)
    build_run("r_killed", terminal="incomplete", outcome=False)
    return TestClient(create_app(build_run.runs_root))


def test_runs_page_lists_every_run(client) -> None:
    html = client.get("/runs").text
    for run_id in ("r_pass", "r_stall", "r_killed"):
        assert run_id in html
    for status in ("passed", "stalled", "incomplete"):
        assert status in html


def test_plain_language_guide_has_progressive_depths(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    for label in ("1 minute · the idea", "5 minutes · the experiment",
                  "15 minutes · how to trust it"):
        assert label in html
    for claim in ("Experiments with organizations of AI agents", "Where each study's status lives",
                  "Keep observations separate from interpretations", 'id="gtable"'):
        assert claim in html
    # the archive table comes first; the explanation follows it
    assert html.index('id="gtable"') < html.index("How the platform works")
    # No study is restated on the front door: status lives in the study records.
    assert "CH1" not in html and 'href="/study-records"' in html
    assert 'href="/library"' in html and 'href="/runs"' in html


def test_navigation_separates_overview_and_runs(client) -> None:
    html = client.get("/").text
    assert 'href="/"' in html and 'href="/runs"' in html
    assert client.get("/guide", follow_redirects=False).headers["location"] == "/"


def test_runs_page_filters(client) -> None:
    html = client.get("/runs", params={"status": "passed"}).text
    assert "r_pass" in html and "r_stall" not in html
    html = client.get("/runs", params={"q": "kill"}).text
    assert "r_killed" in html and "r_pass" not in html


def test_run_page_shows_pins_and_score(client) -> None:
    r = client.get("/run/exp/pack/r_pass")
    assert r.status_code == 200
    assert "1.000" in r.text                       # partial score
    assert "budget_matched" in r.text
    record = client.get("/run/exp/pack/r_pass/record").text
    assert "anthropic/claude-haiku-4-5" in record  # run_status model pin lives on Record


def test_run_page_renders_killed_run(client) -> None:
    r = client.get("/run/exp/pack/r_killed")
    assert r.status_code == 200 and "incomplete" in r.text


def test_unknown_run_is_404(client) -> None:
    assert client.get("/run/exp/pack/nope").status_code == 404
    assert client.get("/run/exp").status_code == 404  # a dir, not a run


def test_derived_file_whitelist(client, build_run) -> None:
    derived = build_run.runs_root / "exp" / "pack" / "r_pass" / "derived"
    derived.mkdir()
    (derived / "clean.txt").write_text("the clean transcript")
    (derived / "secret.txt").write_text("nope")
    ok = client.get("/run/exp/pack/r_pass/derived/clean.txt")
    assert ok.status_code == 200 and ok.text == "the clean transcript"
    assert client.get("/run/exp/pack/r_pass/derived/secret.txt").status_code == 404
    assert client.get("/run/exp/pack/r_pass/derived/full.txt").status_code == 404  # allowed name, absent


def test_clocked_unscored_run_is_integrated_across_views(build_run) -> None:
    status = {**PASSED_STATUS, "scored": False, "passed": False, "partial_score": None,
              "clock_label": "r16w3", "rounds_total": 16,
              "preset_id": "budget_execution_solo_clocked"}
    rd = build_run(
        "r_clock", experiment="clock_density", org="budget_execution_solo_clocked",
        pack="budget_execution", status=status,
        manifest_extra={"extensions": {
            "clock_spec": {"rounds_total": 16, "calls_per_day": 8,
                           "schedule_variant": "r16w3", "megabatch": True},
            "environment_schedule_variant": "r16w3",
            "contract_profile": "single_results_clocked",
            "source_commit": "abc123", "source_dirty": False,
            "apparatus_sha256": "sha256:apparatus",
        }},
        extra_events=(("clock.round", {"payload": {"round_no": 14,
                                                      "rounds_total": 16}}),))
    derived = rd / "derived"
    derived.mkdir()
    (derived / "budget_execution_trace.json").write_text(json.dumps({"summary": {
        "retained_fraction": 0.808995, "retained_benefit": 226.53,
        "baseline_benefit": 263.515, "all_plans_valid": True, "max_pending": 14,
        "n_choice_wrong": 1, "n_choice_undetermined": 2,
        "delivery_outcomes": {"exception_repaired": 11, "exception_unresolved": 2,
                              "covered_unhandled": 4},
        "clock": {"final_round": 14, "n_fuse_lapses": 0, "n_late_repairs": 0,
                  "n_agent_failures": 0, "wind_down": None,
                  "megabatch": {"solo": {"max_per_round": 4}}},
    }}))
    client = TestClient(create_app(build_run.runs_root))

    overview = client.get("/").text
    assert 'id="gtable"' in overview and "retained 80.9%" in overview
    registry = client.get("/runs", params={"clock": "r16w3"}).text
    # an unscored run is a completed run; no verdict is implied either way
    assert "r_clock" in registry and "○</span>completed" in registry
    assert "✕</span>failed_score" not in registry
    detail = client.get("/run/clock_density/budget_execution/r_clock").text
    assert "Clock &amp; capacity" in detail and "Dynamic budget outcomes" in detail
    assert "11" in detail and "2" in detail
    assert "abc123" in client.get("/run/clock_density/budget_execution/r_clock/record").text
