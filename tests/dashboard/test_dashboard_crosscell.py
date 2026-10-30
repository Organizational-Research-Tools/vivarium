"""P1/P6: the days ledger, the item × cell matrix with coverage and the work queue,
and the lineage facet."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from oaos2.dashboard.app import create_app
from tests.dashboard.conftest import _make_clocked


def test_days_ledger(clocked_run) -> None:
    client = TestClient(create_app(clocked_run["runs_root"]))
    ref = clocked_run["run_ref"]
    page = client.get(f"/run/{ref}/days").text
    assert "Roles × days" in page and "horizon 6 days" in page and "2 calls per role per day" in page
    assert "officer_a" in page and "fund_integrator" in page
    assert "wave 1" in page and "initial plan" in page and "final plan" in page
    assert "⏱" in page  # a fuse expires on day 4
    assert 'flow?level=decisions&agent=officer_a&day=2' in page
    assert "✉" in page and "◆" in page and "⚡" in page and "⟲" in page
    from oaos2.dashboard.ledger import build_ledger
    from oaos2.archive.design import run_design
    from oaos2.archive.items import build_items
    from oaos2.dashboard.events import load_events
    events = load_events(clocked_run["run_dir"])
    L = build_ledger(events, run_design(clocked_run["run_dir"]), build_items(clocked_run["run_dir"], events)["items"])
    row_a = next(r for r in L["rows"] if r["role"] == "officer_a")
    day2 = row_a["cells"][[d["day"] for d in L["days"]].index(2)]
    assert day2["calls"] == 2 and day2["arrivals"] == ["C-S1"] and day2["filings"] == ["exception_report_cs1_a"]
    day5 = row_a["cells"][[d["day"] for d in L["days"]].index(5)]
    assert day5 is None  # idle is idle
    assert next(d for d in L["days"] if d["day"] == 4)["fuses"] == ["C-S1", "C-S3"]
    # the clock's own record: lapsed deadlines by day, and no wind-down in this run
    assert L["n_lapses"] >= 1 and any("C-S3" in x for d in L["days"] for x in d["lapses"])
    assert "⌛" in page and L["wind_down"] is None and "Censored" not in page


def test_days_ledger_marks_a_wind_down() -> None:
    from oaos2.dashboard.ledger import build_ledger
    events = [{"event_class": "clock.round", "event_id": f"r{d}", "sequence_number": d,
               "payload": {"round_no": d, "rounds_total": 4}} for d in (1, 2)]
    events += [{"event_class": "model.invoked", "event_id": "m", "sequence_number": 3, "agent_id": "a",
                "payload": {}},
               {"event_class": "clock.wind_down", "event_id": "w", "sequence_number": 4,
                "payload": {"from_round": 2, "to_round": 4, "reason": "outcome open"}}]
    L = build_ledger(events, {}, [])
    assert L["wind_down"]["from"] == 2 and L["wind_down"]["reason"] == "outcome open"
    assert [d["wound"] for d in L["days"]] == [False, False, True, True]


def test_matrix_queue_and_coverage(clocked_run) -> None:
    second = asyncio.run(_make_clocked(clocked_run["runs_root"], "r_clock_lat2"))
    client = TestClient(create_app(clocked_run["runs_root"]))
    page = client.get("/experiment/clock_exp/cases").text
    assert "items across cells" in page and "C-S1" in page and "C-S3" in page
    assert page.count("r_clock_lat") >= 2
    assert "Work queue" in page and "exception_unresolved" in page  # C-S3 lapsed in both cells → queue
    # mark C-S3 as read in the first cell (reading.read.v1 ships with the codebook) → leaves the queue
    from oaos2.dashboard import cases
    from oaos2.dashboard.events import load_events
    d = cases.case_dossier(clocked_run["run_dir"], clocked_run["run_ref"], load_events(clocked_run["run_dir"]),
                           {"task_pack_id": "clockpack", "extensions": {}}, None, "C-S3")
    r = client.post(f"/run/{clocked_run['run_ref']}/annotate", data={
        "label_schema_ref": "reading.read.v1", "event_ids": ",".join(d["annotate_ids"]) or "x",
        "note": "", "mode": "blind", "item_id": "C-S3"}, follow_redirects=False)
    assert r.status_code in (303, 400)  # C-S3 has no filings/disposition → no events to span; that's a 400
    d1 = cases.case_dossier(clocked_run["run_dir"], clocked_run["run_ref"], load_events(clocked_run["run_dir"]),
                            {"task_pack_id": "clockpack", "extensions": {}}, None, "C-S1")
    r = client.post(f"/run/{clocked_run['run_ref']}/annotate", data={
        "label_schema_ref": "reading.read.v1", "event_ids": ",".join(d1["annotate_ids"]),
        "note": "", "mode": "blind", "item_id": "C-S1"}, follow_redirects=False)
    assert r.status_code == 303
    page = client.get("/experiment/clock_exp/cases", params={"by": "rep"}).text
    assert '<span class="r">r</span>' in page and "by <strong>replicate</strong>" in page
    blind = client.get("/experiment/clock_exp/cases", params={"mode": "blind"}).text
    assert "Work queue" not in blind and "exception_unresolved" not in blind and '<span class="r">r</span>' in blind
    assert second["run_dir"].exists()


def test_lineage_facet(clocked_run, build_run) -> None:
    build_run("r_plain")
    client = TestClient(create_app(clocked_run["runs_root"]))
    page = client.get("/runs", params={"lineage": "clock_exp"}).text
    assert "r_clock_lat" in page and "r_plain" not in page
    assert 'name="lineage"' in page
