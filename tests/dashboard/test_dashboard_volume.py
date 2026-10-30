"""P2: broadcast handoffs collapse to one filing, clocked events are first-class
flow items, the flow pages by day, long bodies fetch instead of inlining, and
recorder bookkeeping never reads as a problem."""

from __future__ import annotations

from fastapi.testclient import TestClient

from oaos2.dashboard import events as ev
from oaos2.dashboard.app import create_app


def test_broadcasts_collapse_to_filings(clocked_run) -> None:
    events = ev.load_events(clocked_run["run_dir"])
    n_handoffs = sum(1 for e in events if e["event_class"] == "handoff")
    assert n_handoffs == 8 * 3  # eight filings × three recipients
    items = ev.flow_items(clocked_run["run_dir"], events, "decisions")
    filings = [i for i in items if i["kind"] == "filing"]
    assert len(filings) == 8 and all(i["n"] == 3 for i in filings)
    assert sorted(filings[0]["recipients"]) == ["fund_integrator", "officer_b", "officer_c"]
    assert "FILING office_plan_a → 3 recipients" in filings[0]["title"]
    assert not any(i["kind"] == "handoff" for i in items)
    # the decisions zoom carries a digest, never a body or a folded remainder
    assert all(not i["folded"] and len(i["text"]) <= 201 for i in items if i["kind"] in ("filing", "commit"))


def test_clocked_events_are_first_class_items(clocked_run) -> None:
    events = ev.load_events(clocked_run["run_dir"])
    kinds = {i["kind"] for i in ev.flow_items(clocked_run["run_dir"], events, "decisions")}
    assert {"arrival", "constraint", "intervention", "clock", "capacity", "commit", "filing"} <= kinds
    assert "observed" not in kinds  # observations belong to the reasoning zoom
    everything = ev.flow_items(clocked_run["run_dir"], events, "everything")
    arrivals = [i for i in everything if i["kind"] == "arrival"]
    assert any("NOTICE W1-SITE-A → officer_a · C-S1 · site_closure · wave_1" == i["title"] for i in arrivals)
    observed = [i for i in everything if i["kind"] == "observed"]
    assert any(i["title"].startswith("SAW ") and "environment_event" in i["title"] for i in observed)
    stage = [i for i in everything if i["kind"] == "stage"]
    assert stage and stage[0]["title"].startswith("DUTY ")
    # observations never render as problems, and problems carry a diagnostic finding when one exists
    assert not any(i["kind"] == "problem" for i in everything)


def test_flow_pages_by_day_and_item_route(clocked_run) -> None:
    client = TestClient(create_app(clocked_run["runs_root"]))
    ref = clocked_run["run_ref"]
    page1 = client.get(f"/run/{ref}/flow", params={"level": "decisions"}).text
    assert "Day 0" in page1 and "setup, before the first round" in page1
    assert "one page per day" in page1
    page3 = client.get(f"/run/{ref}/flow", params={"level": "decisions", "page": 3}).text
    assert 'id="day2"' in page3 and "NOTICE W1-SITE-A" in page3 and "INTERVENTION" in page3
    only = client.get(f"/run/{ref}/flow", params={"level": "everything", "day": 3}).text
    assert "CONTEXT COMPACTED" in only and "NOTICE W1-SITE-A" not in only
    # the fetch route serves the full body; the page offers it as a link, never inline
    eid = clocked_run["ids"]["d2_a_h_officer_b"]
    full = client.get(f"/run/{ref}/item/{eid}").text
    assert full.startswith("HANDOFF officer_a → officer_b") and "exception_records" in full
    assert client.get(f"/run/{ref}/item/nope").status_code == 404
    trace = client.get(f"/run/{ref}/trace", params={"view": "full", "day": 4}).text
    assert "capacity.deadline_lapse" in trace and "office_plan_a" not in trace


def test_infrastructure_bookkeeping_is_not_a_problem(build_run) -> None:
    run_dir = build_run("r_infra", extra_events=(
        ("file.reconciliation_mismatch", {"payload": {"path": "/x", "reason": "unseen"}}),
        ("protocol.violation", {"agent_id": "A", "payload": {"reason": "comm_kind_not_permitted"}}),
    ))
    events = ev.load_events(run_dir)
    items = ev.flow_items(run_dir, events, "decisions")
    problems = [i["e"]["event_class"] for i in items if i["kind"] == "problem"]
    assert problems == ["protocol.violation"]
    lanes = ev.swimlane(events)
    assert not any(m["cls"] == "file.reconciliation_mismatch" for m in lanes["marks"])
