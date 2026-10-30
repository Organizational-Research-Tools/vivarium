"""The question-shaped run views (DASHBOARD.md §4.2b–e): Organization, Agents, the
pack-registered Work tab, and Record — each a rendering of recorded events."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from oaos2.archive import work as worklib
from oaos2.archive.design import run_design
from oaos2.dashboard import agents as agentlib
from oaos2.dashboard import organization as orglib
from oaos2.dashboard.app import create_app
from oaos2.dashboard.events import load_events
from tests.dashboard.test_dashboard_voluntary_comms import _VOLUNTARY


def test_interaction_graph_counts_directed_acts(build_run) -> None:
    rd = build_run("r_org", extra_events=_VOLUNTARY)
    events = load_events(rd)
    xs = [{"seq": 1, "event_id": "x", "from": "A", "to": ["B", "C"], "kind": "grant", "text": ""}]
    g = orglib.graph(events, xs, ["A", "B", "C"])
    by = {(e["from"], e["to"]): e["kinds"] for e in g["edges"]}
    assert by[("A", "board")] == {"posts": 1}
    assert by[("B", "A")] == {"notes": 1} and by[("A", "B")] == {"grant": 1, "notes": 1}
    assert by[("A", "C")] == {"grant": 1}
    assert g["has_board"] and {n["id"] for n in g["nodes"]} == {"A", "B", "C", "board"}
    assert all(e["path"].startswith("M") and e["width"] >= 1 for e in g["edges"])


def test_agent_profiles_count_sent_received_and_cost(build_run) -> None:
    rd = build_run("r_org", extra_events=_VOLUNTARY + [
        ("model.responded", {"agent_id": "A", "payload": {"usage": {"input": 5, "output": 7}}}),
        ("cost.recorded", {"agent_id": "A", "payload": {"cost_usd": 0.25}}),
        ("tool.called", {"agent_id": "A", "turn_id": "A.t1", "payload": {"tool_name": "post"}}),
    ])
    events = load_events(rd)
    xs = [{"seq": 1, "event_id": "x", "from": "A", "to": ["B"], "kind": "grant", "text": ""}]
    profs = {p["agent"]: p for p in agentlib.profiles(events, xs, run_design(rd), ["A", "B"])}
    a, b = profs["A"], profs["B"]
    assert a["posts"] == 1 and a["notes_out"] == 1 and a["notes_in"] == 1 and a["calls"] == 1
    assert a["cost_usd"] == 0.25 and a["output_tokens"] == 7 and a["tool_calls"] == {"post": 1}
    assert a["exchanges_out"] == {"grant": 1} and b["exchanges_in"] == {"grant": 1}
    assert b["posts_received"] == 1 and b["notes_out"] == 1 and profs["C"]["posts_received"] == 1


def test_view_pages_render_and_rail_follows_the_pack(build_run) -> None:
    build_run("r_org", extra_events=_VOLUNTARY)
    client = TestClient(create_app(build_run.runs_root), follow_redirects=False)
    ref = "exp/pack/r_org"
    html = client.get(f"/run/{ref}/organization").text
    assert "Who dealt with whom" in html and "A → board" in html and "<svg" in html
    html = client.get(f"/run/{ref}/agents").text
    assert "read A" in html and 'href="/run/exp/pack/r_org/agent/B"' in html
    html = client.get(f"/run/{ref}/agent/B").text
    assert "Notes received" in html and "grant me p1" in html and "Notes sent" in html
    assert client.get(f"/run/{ref}/agent/nobody").status_code == 404
    html = client.get(f"/run/{ref}/record").text
    assert "Is the record trustworthy?" in html and "Identity" in html and "events by class" in html.lower()
    r = client.get(f"/run/{ref}/work")
    assert r.status_code == 307 and r.headers["location"].endswith("/cases")  # no work adapter: cases
    overview = client.get(f"/run/{ref}").text
    assert "Read on" in overview and "Identity &amp; pins" not in overview  # pins moved to Record


def test_registered_work_view_names_the_tab_and_fills_it(build_run) -> None:
    worklib.unregister_work_adapter("pack")
    worklib.register_work_adapter(worklib.WorkAdapter(
        pack_id="pack", label="Projects",
        sections=lambda run_dir, events, report: [
            {"title": "Projects", "columns": ["id", "state"], "rows": [["A1", "open"]]},
            {"title": "Notes", "kv": [("k", "v")]},
            {"bad": "section"},
        ]))
    try:
        build_run("r_work", extra_events=_VOLUNTARY)
        client = TestClient(create_app(build_run.runs_root))
        html = client.get("/run/exp/pack/r_work/work").text
        assert ">Projects</a>" in html and ">Cases</a>" not in html
        assert "<td>A1</td>" in html and "<dt>k</dt>" in html
        assert worklib.work_sections("pack", Path("."), [], None)[-1]["title"] == "Notes"
    finally:
        worklib.unregister_work_adapter("pack")


def test_materials_work_sections_from_the_report() -> None:
    from oaos2.tasks.plugins.materials_lab import derived
    from tests.tasks.test_materials_lab_derived import _events
    report = derived.summarize_run(Path("."), _events())
    secs = derived.work_sections(Path("."), _events(), report)
    # conduct and the opportunity audit lead; this fixture has no institution outcome
    assert [s["title"] for s in secs] == ["Conduct by lab", "Reporting opportunities", "Projects", "Labs",
                                          "Reports", "Concerns and retirements"]
    by = {s["title"]: s for s in secs}
    assert by["Projects"]["rows"][0][3] == 1 and by["Projects"]["rows"][0][-1] == "no"
    assert by["Labs"]["rows"][1][0] == "lab_water"
    assert by["Concerns and retirements"]["kv"][-1][0] == "lab_water retired"
    assert worklib.work_adapter_for("materials_lab").label == "Projects"
