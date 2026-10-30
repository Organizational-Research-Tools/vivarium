"""P4/P6: the diagnostics registry's clocked rules, the pack's period-report rule,
the outcome-blind registry, and cross-run search."""

from __future__ import annotations

from fastapi.testclient import TestClient

from oaos2.dashboard import diagnostics, store
from oaos2.dashboard.app import create_app
from oaos2.dashboard.events import load_events
from oaos2.dashboard.reports import ReportStore


def _findings(clocked_run):
    events = load_events(clocked_run["run_dir"])
    detail = store.run_detail(clocked_run["run_dir"], events, reports=ReportStore(clocked_run["runs_root"]))
    return {f["id"]: f for f in diagnostics.diagnose(clocked_run["run_dir"], events, detail)}


def test_clocked_foundation_rules(clocked_run) -> None:
    f = _findings(clocked_run)
    assert f["commit_races"]["severity"] == "warning" and "day 2: fund_integrator ×1" in f["commit_races"]["detail"]
    assert f["compaction_open"]["severity"] == "warning" and "fund_integrator with 1 open" in f["compaction_open"]["detail"]
    assert f["ceiling_days"]["severity"] == "info" and "officer_a: days 2" in f["ceiling_days"]["detail"]
    assert "zero_cost" not in f and "over_cap" not in f
    assert f["capacity.deadline_lapse"]["severity"] == "info"


def test_zero_cost_and_over_cap(build_run) -> None:
    from tests.dashboard.conftest import PASSED_STATUS
    run_dir = build_run("r_zero", status={**PASSED_STATUS, "cost_usd": 0.0},
                        manifest_extra={"extensions": {"cap_usd": 1.0}},
                        extra_events=(("model.invoked", {"agent_id": "A", "payload": {"model_ref": "m"}}),
                                      ("cost.recorded", {"agent_id": "A", "payload": {"cost_usd": 1.5}})))
    events = load_events(run_dir)
    detail = store.run_detail(run_dir, events)
    f = {x["id"]: x for x in diagnostics.diagnose(run_dir, events, detail)}
    assert f["zero_cost"]["severity"] == "serious"
    assert f["over_cap"]["severity"] == "serious" and "$1.50" in f["over_cap"]["title"]


def test_period_report_rule_orders_reports_against_arrivals() -> None:
    from oaos2.tasks.plugins.budget_execution.derived import period_report_ordering

    def env(seq, role, wave):
        return {"event_class": "environment.event", "sequence_number": seq, "agent_id": role,
                "payload": {"environment_event": {"wave_id": wave, "target_role_id": role, "payload": {}}}}

    def commit(seq, cid):
        return {"event_class": "state.committed", "sequence_number": seq,
                "payload": {"state_commitment": {"commitment_id": cid}}}

    early = [commit(1, "exception_report_w1_economy"), env(5, "officer_economy", "wave_1"), env(6, "officer_economy", "wave_1")]
    out = period_report_ordering(None, early, {"manifest": {}})
    assert out and out[0]["id"] == "period_report_early" and out[0]["severity"] == "warning"
    held = [env(5, "officer_economy", "wave_1"), commit(9, "exception_report_w1_economy")]
    out = period_report_ordering(None, held, {"manifest": {}})
    assert out and out[0]["id"] == "period_gate_held" and out[0]["severity"] == "info"
    assert period_report_ordering(None, [commit(1, "office_plan_economy")], {"manifest": {}}) == []


def test_outcome_blind_registry(clocked_run) -> None:
    client = TestClient(create_app(clocked_run["runs_root"]))
    page = client.get("/runs").text
    assert "85.0%" in page
    blind = client.get("/runs", params={"blind": 1}).text
    assert "85.0%" not in blind and "outcome-blind" in blind


def test_search_indexes_and_finds(clocked_run) -> None:
    client = TestClient(create_app(clocked_run["runs_root"]))
    empty = client.get("/search", params={"q": "annex"}).text
    assert "scope is required" in empty
    page = client.get("/search", params={"q": "annex", "lineage": "clock_exp"}).text
    assert "indexed 1" in page and "[annex]" in page
    assert "filing" in page and "thinking" in page and "submitted" in page
    page2 = client.get("/search", params={"q": "gymnasium", "experiment": "clock_exp", "kind": "notice"}).text
    assert "reused 1" in page2 and "notice" in page2 and "[gymnasium]" in page2
    assert (clocked_run["runs_root"] / ".dashboard" / "search.sqlite").exists()
    bad = client.get("/search", params={"q": '"unbalanced', "lineage": "clock_exp"}).text
    assert "query error" in bad
