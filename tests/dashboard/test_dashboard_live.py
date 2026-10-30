"""The live view (DASHBOARD.md §4.2f): the tail reads only appended, complete lines;
groups come from declared role settings; the feed continues after the reader's last
position and tags the groups a directed item crossed; the pages render."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from oaos2.dashboard import live, story
from oaos2.dashboard.app import create_app
from oaos2.tasks.plugins.materials_lab.views import standings as lab_standings  # the workshop's live panel

_EVENTS = [
    ("board.posted", {"agent_id": "A", "payload": {"seq": 1, "text": "who can measure heat?",
                                                    "recipients": ["B"]}}),
    ("turn.started", {"agent_id": "B", "turn_id": "B.t1", "payload": {}}),
    ("message.sent", {"agent_id": "B", "payload": {"to": "A", "kind": "note",
                                                    "payload_text": "[note from B] I can."}}),
    ("tool.called", {"agent_id": "B", "turn_id": "B.t1", "payload": {"tool_name": "measure"}}),
]


def _line(pos: int, cls: str, agent: str, **payload) -> bytes:
    return (json.dumps({"event_class": cls, "event_id": f"e{pos}", "sequence_number": pos,
                        "timestamp": 1000.0 + pos, "agent_id": agent, "payload": payload})
            + "\n").encode()


def test_tail_reads_appended_complete_lines_only(tmp_path) -> None:
    rd = tmp_path / "run"
    (rd / "trace").mkdir(parents=True)
    stream = rd / "trace" / "events.jsonl"
    stream.write_bytes(_line(0, "run.started", None) + _line(1, "turn.started", "A"))
    events, v1 = live.tail_events(rd)
    assert [e["sequence_number"] for e in events] == [0, 1]
    half = _line(2, "tool.called", "A", tool_name="measure")
    with open(stream, "ab") as f:
        f.write(half[:20])  # the writer is mid-line
    events, v2 = live.tail_events(rd)
    assert len(events) == 2 and v2 == v1
    with open(stream, "ab") as f:
        f.write(half[20:])
    (rd / "trace" / "infra.jsonl").write_bytes(_line(3, "cost.recorded", "A", cost_usd=0.5))
    events, v3 = live.tail_events(rd)
    assert [e["sequence_number"] for e in events] == [0, 1, 2, 3] and v3 > v2
    stream.write_bytes(_line(0, "run.started", None))  # replaced: read again from the start
    events, _ = live.tail_events(rd)
    assert [e["sequence_number"] for e in events] == [0, 3]


def test_groups_use_declared_settings_and_fall_back_to_everyone() -> None:
    roles = {"integrator": {"attention": "integrator_view", "role_packet": "integrator"},
             **{f"o{i}": {"attention": f"office/{i}", "role_packet": "officer"} for i in range(3)}}
    agents = list(roles)
    used, member = live.groups(agents, roles, "auto")
    assert used == "attention" and member["o1"] == "office" and member["integrator"] == "integrator_view"
    used, member = live.groups(agents + ["coordination"], roles, "packet")
    assert member["o2"] == "officer" and member["coordination"] == "coordination"
    labs = {f"lab_{c}": {"attention": "all", "role_packet": "lab"} for c in "abc"}
    assert live.groups(list(labs), labs, "auto") == ("none", {a: "everyone" for a in labs})


def test_state_feed_and_crossings(tmp_path) -> None:
    rd = tmp_path / "run"
    (rd / "trace").mkdir(parents=True)
    (rd / "trace" / "events.jsonl").write_bytes(
        _line(0, "turn.started", "A") + _line(1, "message.sent", "A", to="B", kind="note",
                                              payload_text="hi")
        + _line(2, "agent.waiting", "B") + _line(3, "message.sent", "B", to="C", kind="note",
                                                 payload_text="relay"))
    events, _ = live.tail_events(rd)
    roles = {"A": {"role_packet": "x"}, "B": {"role_packet": "x"}, "C": {"role_packet": "y"}}
    s = live.live_clock(live.live_state(rd, events, roles=roles, exchanges=[], by="packet"),
                        rd, now=1010.0)
    rows = {a["agent"]: a for g in s["groups"] for a in g["agents"]}
    assert rows["A"]["state"] == "working" and rows["B"]["state"] == "waiting"
    assert rows["C"]["state"] == "not started" and rows["B"]["quiet_s"] == 7
    assert s["ended"] is None and s["quiet_s"] == 7
    assert {(f["from"], f["to"], f["n"]) for f in s["flows"]} == {("x", "x", 1), ("x", "y", 1)}
    items = story.story_items(events, exchanges=[], milestones=[], depth="notes", fold=False)
    feed = live.feed_items(items, after=None, member=s["member"])
    assert [it["crossing"] for it in feed] == ["within x", "x → y"]
    assert [it["seq"] for it in live.feed_items(items, after=1, member=s["member"])] == [3]
    assert [it["seq"] for it in live.feed_items(items, after=None, member=s["member"],
                                                group="y")] == [3]


def test_live_pages_render_and_poll(build_run) -> None:
    build_run("r_live", extra_events=_EVENTS)
    client = TestClient(create_app(build_run.runs_root))
    html = client.get("/run/exp/pack/r_live/live").text
    assert "who can measure heat?" in html and "Where each agent is" in html
    assert "the run has ended" in html or "ended" in html
    d = client.get("/run/exp/pack/r_live/live.json", params={"after": -1}).json()
    assert d["n_new"] > 0 and d["ended"] and "I can." in d["feed_html"]
    d = client.get("/run/exp/pack/r_live/live.json", params={"after": d["last_seq"]}).json()
    assert d["n_new"] == 0 and d["feed_html"] == "" and "Where each agent is" in d["panels_html"]
    assert client.get("/live").status_code == 200


def test_lanes_place_items_mark_busy_lanes_and_separate_days(tmp_path) -> None:
    rd = tmp_path / "run"
    (rd / "trace").mkdir(parents=True)
    (rd / "trace" / "events.jsonl").write_bytes(
        _line(0, "clock.round", None, round_no=1)
        + _line(1, "model.invoked", "A") + _line(2, "model.invoked", "C")
        + _line(3, "message.sent", "B", to="C", kind="note", payload_text="to the other group")
        + _line(4, "model.responded", "A")
        + _line(5, "board.posted", "A", seq=1, text="hello all", recipients=["B", "C"])
        + _line(6, "clock.round", None, round_no=2)
        + _line(7, "message.sent", "A", to="B", kind="note", payload_text="same group"))
    events, _ = live.tail_events(rd)
    member = {"A": "x", "B": "x", "C": "y"}
    lanes, index = live.lanes_of(["A", "B", "C"], member, board=True)
    assert lanes == ["x", "y", "board"] and index == {"A": 0, "B": 0, "C": 1}
    items = story.story_items(events, exchanges=[], milestones=[], depth="notes", fold=False)
    rows = live.lane_rows(live.feed_items(items, after=-1, member=member), events,
                          lanes=lanes, index=index)
    note, post, same = rows  # a day opening is a separator, not a row of its own
    assert note["lane"] == 0 and note["reached"] == [1] and note["arrive"] == {1: ["C"]}
    assert note["busy"] == [1, 1, 0] and note["span"] == (0, 1)
    assert post["lane"] == 2 and post["from"] == 0 and post["reached"] == [] and post["span"] == (0, 2)
    assert post["busy"] == [0, 1, 0] and post["t"] == 5
    assert same["reached"] == [] and same["span"] is None
    assert [r["sep"] for r in rows if r["sep"]] == ["day 1 opens", "day 2 opens"]
    assert [r["item"]["seq"] for r in live.rows_after(rows, 5)] == [7]
    # without groups, each agent is its own lane
    assert live.lanes_of(["A", "B"], {"A": "everyone", "B": "everyone"}, board=False) == (
        ["A", "B"], {"A": 0, "B": 1})


def test_live_lanes_view_renders_and_polls(build_run) -> None:
    build_run("r_live", extra_events=_EVENTS)
    client = TestClient(create_app(build_run.runs_root))
    html = client.get("/run/exp/pack/r_live/live", params={"view": "lanes"}).text
    assert 'class="story llanes"' in html and "who can measure heat?" in html
    d = client.get("/run/exp/pack/r_live/live.json", params={"view": "lanes", "after": -1}).json()
    assert d["n_new"] > 0 and 'class="lrow"' in d["feed_html"] and d["lanes_key"]
    html = client.get("/run/exp/pack/r_live/live", params={"view": "feed"}).text
    assert 'class="story llanes"' not in html and "I can." in html


def test_live_tab_only_for_runs_that_may_still_be_written(tmp_path) -> None:
    rd = tmp_path / "run"
    (rd / "trace").mkdir(parents=True)
    stream = rd / "trace" / "events.jsonl"
    stream.write_bytes(b"")
    assert not live.is_unfinished(rd, idle_after_s=3600)  # empty
    stream.write_bytes(_line(0, "run.started", None) + _line(1, "turn.started", "A"))
    assert live.is_unfinished(rd, idle_after_s=3600)
    import time
    assert not live.is_unfinished(rd, idle_after_s=3600, now=time.time() + 7200)  # idle
    with open(stream, "ab") as f:
        f.write(_line(2, "run.completed", None))
    assert not live.is_unfinished(rd, idle_after_s=3600)  # ended, though not finalized
    stream.write_bytes(_line(0, "run.started", None))
    (rd / "run_status.json").write_text("{}")
    assert not live.is_unfinished(rd, idle_after_s=3600)  # finalized


def test_retired_stays_retired_and_task_milestones_are_counted(tmp_path) -> None:
    rd = tmp_path / "run"
    (rd / "trace").mkdir(parents=True)
    (rd / "trace" / "events.jsonl").write_bytes(
        _line(0, "turn.started", "A") + _line(1, "agent.retired", "A")
        + _line(2, "turn.completed", "A") + _line(3, "coordination.report_timeout", "A"))
    events, _ = live.tail_events(rd)
    ms = [{"seq": 1, "event_id": "m1", "from": "A", "to": [], "kind": "report.submitted", "text": "r1"}]
    s = live.live_state(rd, events, roles={"A": {}}, exchanges=[], milestones=ms)
    a = s["groups"][0]["agents"][0]
    assert a["state"] == "retired" and a["milestones"] == 1 and a["problems"] == 1


def test_a_saved_report_that_predates_the_analysis_is_rendered_again(tmp_path) -> None:
    """A pack's ``expects`` names keys its current analysis produces; a saved report
    without them is rendered into the dashboard cache and the file is left alone."""
    import dataclasses
    from oaos2.archive import renderers as R
    from oaos2.dashboard.reports import ReportStore
    run = tmp_path / "runs" / "r"
    (run / "trace").mkdir(parents=True)
    (run / "derived").mkdir()
    (run / "trace" / "events.jsonl").write_bytes(_line(0, "run.started", None))
    (run / "manifest.json").write_text(json.dumps({"task_pack_id": "stalepack"}))
    (run / "derived" / "stale.json").write_text(json.dumps({"old": 1}))
    base = R.DerivedRenderer(pack_id="stalepack", filename="stale.json",
                             render=lambda rd, ev: {"old": 1, "new": 2}, summary=lambda r: r,
                             identity="t1", expects=("new",))
    R.register_derived_renderer(base, override=True)
    try:
        got = ReportStore(tmp_path / "runs").get(run)
        assert got["report"] == {"old": 1, "new": 2} and got["superseded_file"] == "stale.json"
        assert got["stale_keys"] == ["new"] and json.loads((run / "derived" / "stale.json").read_text()) == {"old": 1}
        def refuse(rd, ev):
            raise ValueError("pinned materials changed")
        R.register_derived_renderer(dataclasses.replace(base, render=refuse, identity="t2"), override=True)
        got = ReportStore(tmp_path / "runs").get(run)
        assert got["source"] == "file" and got["report"] == {"old": 1} and got["stale_keys"] == ["new"]
    finally:
        R.unregister_derived_renderer("stalepack")


def test_unknown_usage_and_left_out_runs_are_labelled(build_run, tmp_path, monkeypatch) -> None:
    """A model call that ended with unknown usage makes the cost a lower bound; a run a
    saved evidence dataset's audit left out is labelled with that dataset's reason."""
    from oaos2.dashboard import frozen
    rd = build_run("r_unknown", extra_events=[
        ("model.invocation_failed", {"agent_id": "A", "payload": {"error": "CancelledError",
                                                                  "usage_status": "unknown"}})])
    client = TestClient(create_app(build_run.runs_root))
    record = client.get("/run/exp/pack/r_unknown/record").text
    assert "Model usage unknown ×1" in record
    page = client.get("/run/exp/pack/r_unknown").text
    assert "≥ " in page and "1 call with unknown usage" in page
    ev = tmp_path / "evidence"
    ev.mkdir()
    (ev / "study.json").write_text(json.dumps({"dataset": {"rows": [], "audit": {
        "nonqualifying": [{"run_dir": rd.name, "reason": "no_run_status"}]}}}))
    monkeypatch.setattr(frozen, "_evidence_dir", lambda: ev)
    monkeypatch.setattr(frozen, "_snapshot", None)
    assert frozen.left_out_of_dataset(rd.name)["reason"] == "no_run_status"
    page = client.get("/run/exp/pack/r_unknown").text
    assert "left out of analysis dataset" in page and "no run status" in page


def test_library_listing_is_memoized_until_a_file_changes(tmp_path, monkeypatch) -> None:
    from oaos2.dashboard import workbench
    lib = tmp_path / "library"
    for sub in ("experiments", "organizations", "tasks"):
        (lib / sub).mkdir(parents=True)
    monkeypatch.setattr(workbench, "library_dir", lambda: lib)
    monkeypatch.setattr(workbench, "_LIBRARY_MEMO", None)
    calls = []
    real = workbench._list_library
    monkeypatch.setattr(workbench, "_list_library", lambda: calls.append(1) or real())
    workbench.list_library()
    workbench.list_library()
    assert len(calls) == 1
    (lib / "organizations" / "x.yaml").write_text("preset_id: x\n")
    workbench.list_library()
    assert len(calls) == 2


def test_a_folded_burst_returns_to_the_feed_when_it_grows() -> None:
    folded = {"kind": "exchange", "who": "A", "seq": 3, "last_seq": 9, "to": ["B"], "text": "3×", "n": 3}
    plain = {"kind": "note", "who": "A", "seq": 5, "to": ["B"], "text": "hi"}
    got = live.feed_items([folded, plain], after=6, member={"A": "x", "B": "x"})
    assert [x["seq"] for x in got] == [3]  # its newest member is past the reader's position


def test_an_abandonment_note_ends_a_run_that_never_closed(tmp_path) -> None:
    """A run stopped before its closing event reads as live until it goes idle; a note beside the
    trace (never in it) says it was abandoned, and the live view respects it at once."""
    rd = tmp_path / "run"
    (rd / "trace").mkdir(parents=True)
    (rd / "trace" / "events.jsonl").write_text(json.dumps({"event_class": "model.invoked"}) + "\n")
    assert live.is_unfinished(rd, idle_after_s=3600)
    (rd / "ABANDONED.json").write_text(json.dumps({"reason": "stopped by the PI"}))
    assert not live.is_unfinished(rd, idle_after_s=3600)
    assert (rd / "trace" / "events.jsonl").read_text().count("\n") == 1  # the trace is untouched


def _credit_events(institution, **rule):
    staged = [{"event_class": "lab.staged", "timestamp": 0.0, "agent_id": lab,
               "payload": {"institution": institution, **rule}} for lab in ("lab_a", "lab_b", "lab_c", "lab_d")]

    def alloc(t, rid, credits):
        return {"event_class": "credit.allocated", "timestamp": t, "agent_id": "x",
                "payload": {"report_id": rid, "project_id": "A1", "submitter": next(iter(credits)), "credits": credits}}
    return staged, alloc


def test_standings_rank_credits_mark_who_succeeds_and_strike_voided_reports() -> None:
    staged, alloc = _credit_events("competitive", allocation="divisible", success_floor=3, success_cap=2)
    ev = staged + [alloc(60, "r1", {"lab_a": 2, "lab_b": 1, "lab_c": 1}),
                   alloc(120, "r2", {"lab_c": 2, "lab_b": 1, "lab_d": 1}),
                   alloc(180, "r3", {"lab_d": 4}),
                   {"event_class": "credit.voided", "timestamp": 360, "payload": {"report_id": "r3"}},
                   {"event_class": "agent.retired", "timestamp": 360, "agent_id": "lab_d", "payload": {"reason": "dismissed"}}]
    st = lab_standings(ev)
    assert [(r["lab"], r["credits"], r["succeeding"]) for r in st["rows"]] == \
        [("lab_c", 3, True), ("lab_a", 2, False), ("lab_b", 2, False), ("lab_d", 1, False)]
    assert st["rows"][-1]["dismissed"] and st["reports"][2]["voided"] and st["reports"][2]["voided_minute"] == 6.0
    # lab_a and lab_b tie at 2; lab_a reached it first (report r1), lab_b at r2 -- neither meets the floor of 3
    # an event read twice, and the one credit recorded before a divisible split, count once
    dup = [{"event_class": "credit.awarded", "timestamp": 60, "agent_id": "lab_a", "payload": {"report_id": "r1"}}]
    assert lab_standings(staged + dup + ev + ev[4:5])["rows"][0]["credits"] == 3


def test_standings_read_a_missing_rule_from_the_start_note_and_show_cooperative_progress() -> None:
    staged, alloc = _credit_events("competitive")
    note = {"event_class": "agent.observed", "timestamp": 1, "agent_id": "lab_a", "payload": {"items": [
        "... Failure rule: at the deadline, the three laboratories with the most credits succeed, if each holds at least "
        "4 credits; every other laboratory fails ..."]}}
    st = lab_standings(staged + [note, alloc(60, "r1", {"lab_a": 2, "lab_b": 1, "lab_c": 1})])
    assert st["from_note"] and (st["floor"], st["cap"]) == (4, 3) and not any(r["succeeding"] for r in st["rows"])
    staged, _ = _credit_events("cooperative", credit_threshold=3)
    award = {"event_class": "credit.awarded", "timestamp": 90, "agent_id": "lab_b", "payload": {"report_id": "r1", "project_id": "B2"}}
    st = lab_standings(staged + [award])
    assert st["kind"] == "progress" and (st["credits"], st["threshold"]) == (1, 3)
    assert lab_standings([{"event_class": "lab.staged", "timestamp": 0, "payload": {}}]) is None


def test_standings_hold_everyone_below_the_program_target() -> None:
    staged, alloc = _credit_events("competitive", allocation="divisible", success_floor=2, success_cap=3,
                                   program_target=2)
    st = lab_standings(staged + [alloc(60, "r1", {"lab_a": 2, "lab_b": 1, "lab_c": 1})])
    assert st["program"] == {"qualified": 1, "target": 2, "pct": 50, "label": "projects qualified"}
    assert not any(r["succeeding"] for r in st["rows"])
    st = lab_standings(staged + [alloc(60, "r1", {"lab_a": 2, "lab_b": 1, "lab_c": 1}),
                                  {**alloc(90, "r2", {"lab_b": 2, "lab_a": 1, "lab_c": 1}),
                                   "payload": {"report_id": "r2", "project_id": "B1", "submitter": "lab_b",
                                               "credits": {"lab_b": 2, "lab_a": 1, "lab_c": 1}}}])
    assert st["program"]["qualified"] == 2 and [r["lab"] for r in st["rows"] if r["succeeding"]] == ["lab_b", "lab_a", "lab_c"]


def test_standings_follow_displacement_restoration_and_the_product_lines() -> None:
    staged, alloc = _credit_events("competitive", allocation="divisible", success_floor=2, success_cap=3,
                                   program_lines=True, family_types={"alpha": [], "beta": [], "gamma": []})

    def awarded(t, rid, margin):
        return {"event_class": "credit.awarded", "timestamp": t, "agent_id": "lab_a",
                "payload": {"report_id": rid, "project_id": "A1", "margin": margin}}
    ev = staged + [awarded(60, "r1", 2.0), alloc(60, "r1", {"lab_a": 2, "lab_b": 1, "lab_c": 1}),
                   {"event_class": "credit.lapsed", "timestamp": 120, "payload": {"report_id": "r1", "displaced_by": "r2"}},
                   awarded(120, "r2", 3.5), alloc(120, "r2", {"lab_d": 2, "lab_e": 1, "lab_f": 1})]
    st = lab_standings(ev)
    assert st["reports"][0]["lapsed"] and st["reports"][0]["margin"] == 2.0 and st["reports"][1]["margin"] == 3.5
    assert {r["lab"]: r["credits"] for r in st["rows"]}["lab_a"] == 0
    assert st["program"]["qualified"] == 1 and st["program"]["target"] == 3 and not any(r["succeeding"] for r in st["rows"])
    ev += [{"event_class": "credit.voided", "timestamp": 200, "payload": {"report_id": "r2"}},
           {"event_class": "credit.restored", "timestamp": 200, "payload": {"report_id": "r1"}}]
    st = lab_standings(ev)
    assert {r["lab"]: r["credits"] for r in st["rows"]}["lab_a"] == 2 and st["reports"][0]["restored"]
