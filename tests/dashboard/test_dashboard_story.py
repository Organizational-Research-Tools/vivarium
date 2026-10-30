"""The Story view (DASHBOARD.md §4.2a): the forum as the spine, notes as asides, what
agents said between them, milestones and problems always shown — every item one
recorded event in writer order — and the library's organization families."""

from __future__ import annotations

from fastapi.testclient import TestClient

from oaos2.dashboard import story, workbench
from oaos2.dashboard.app import create_app
from oaos2.dashboard.events import load_events

_EVENTS = [
    ("board.posted", {"agent_id": "A", "payload": {"seq": 1, "text": "who can measure heat?",
                                                    "recipients": ["B"]}}),
    ("reasoning.step", {"agent_id": "B", "turn_id": "B.t1",
                        "payload": {"narration": "I'll answer A.", "thinking": "A needs heat."}}),
    ("message.sent", {"agent_id": "B", "payload": {"to": "A", "kind": "note",
                                                    "payload_text": "[note from B] I can."}}),
    ("tool.called", {"agent_id": "B", "turn_id": "B.t1", "payload": {"tool_name": "measure"}}),
    ("protocol.violation", {"agent_id": "B", "payload": {"reason": "comm_kind_not_permitted"}}),
    ("agent.launched", {"agent_id": "B", "payload": {}}),
]


def _kinds(items):
    return [it["kind"] for it in items]


def test_depths_are_cumulative_and_problems_always_show(build_run) -> None:
    rd = build_run("r_story", extra_events=_EVENTS)
    events = load_events(rd)
    at = lambda depth, agent=None: story.story_items(  # noqa: E731
        events, exchanges=[], milestones=[], depth=depth, agent=agent)
    tail = ["problem", "lifecycle", "lifecycle", "lifecycle"]  # B joined, outcome closed, run completed
    assert _kinds(at("forum")) == ["post"] + tail
    assert _kinds(at("notes")) == ["post", "note"] + tail
    assert _kinds(at("said")) == ["post", "said", "note"] + tail
    assert _kinds(at("everything")) == ["post", "said", "thinking", "note", "tool"] + tail
    # the forum is shared and run-level items belong to everyone; B's own turn drops out
    assert _kinds(at("everything", agent="A")) == ["post", "note", "problem", "lifecycle", "lifecycle"]
    post = at("forum")[0]
    assert post["title"] == "#1" and post["to"] == ["B"] and post["seq"] > 0


def test_registered_rows_join_the_story_in_order(build_run) -> None:
    rd = build_run("r_story", extra_events=_EVENTS)
    events = load_events(rd)
    note = next(e for e in events if e.get("event_class") == "message.sent")
    xs = [{"seq": note["sequence_number"] + 0.5, "event_id": "x1", "from": "A", "to": ["B"],
           "kind": "grant measurement", "text": "p1"}]
    ms = [{"seq": note["sequence_number"] + 0.7, "event_id": "m1", "from": "A", "to": [],
           "kind": "report.submitted", "text": "report r1 on A1"}]
    items = story.story_items(events, exchanges=xs, milestones=ms, depth="said")
    kinds = _kinds(items)
    assert kinds.index("note") < kinds.index("exchange") < kinds.index("milestone") < kinds.index("problem")
    assert story.story_items(events, exchanges=xs, milestones=ms, depth="forum")[1]["title"] == "submitted"


def test_story_page_renders_and_paginates(build_run) -> None:
    build_run("r_story", extra_events=_EVENTS)
    client = TestClient(create_app(build_run.runs_root))
    html = client.get("/run/exp/pack/r_story/story").text
    assert "who can measure heat?" in html and "private note" in html and "I can." in html
    assert "answer A." not in html  # narration is one depth deeper
    html = client.get("/run/exp/pack/r_story/story", params={"depth": "said"}).text
    assert "answer A." in html and "comm_kind_not_permitted" in html
    assert "B joined the run" in html
    items = [{"kind": "post", "seq": i, "e": {}} for i in range(1001)]
    page, pages = story.paginate(items, 3)
    assert pages == 3 and len(page) == 201 and page[0]["seq"] == 800


def test_organization_families_diff_variants_against_a_base() -> None:
    entries = [
        {"name": "solo", "path": "organizations/solo.yaml",
         "resolved": {"n_agents": 1, "scheduler": "free", "tools": ["a", "b"],
                      "live_coordination": {"mode": "m", "x": 1},
                      "roles": [{"role_id": "p", "context_budget_tokens": 60000, "tools": ["a"]}]}},
        {"name": "solo_c5k", "path": "organizations/solo_c5k.yaml",
         "resolved": {"n_agents": 1, "scheduler": "free", "tools": ["a", "b", "c"],
                      "live_coordination": {"mode": "m", "x": 2},
                      "roles": [{"role_id": "p", "context_budget_tokens": 5000, "tools": ["a"]}]}},
        {"name": "duo", "path": "organizations/duo.yaml",
         "resolved": {"n_agents": 2, "roles": [{"role_id": "p"}, {"role_id": "q"}]}},
        {"name": "broken", "path": "organizations/broken.yaml", "error": "boom"},
    ]
    fams = workbench.organization_families(entries)
    assert [f["label"] for f in fams] == ["solo", "duo", "presets that fail to load"]
    solo = fams[0]
    assert solo["base"] == "solo" and solo["members"][0]["is_base"]
    assert solo["members"][1]["diffs"] == ["live_coordination.x: 1 → 2", "tools: +c",
                                           "p.context_budget_tokens: 60000 → 5000"]
    assert fams[2]["members"][0]["name"] == "broken"
    fams = workbench.organization_families(workbench.list_library()["organizations"])
    assert any(f["label"] == "budget_execution_solo" for f in fams)  # the real library groups


def test_consecutive_exchanges_fold_into_one_line(build_run) -> None:
    rd = build_run("r_story", extra_events=_EVENTS)
    events = load_events(rd)
    base = max(e["sequence_number"] for e in events)
    xs = [{"seq": base + i, "event_id": f"x{i}", "from": "A", "to": ["B"],
           "kind": "grant measurement", "text": f"p{i}"} for i in range(1, 9)]
    xs.append({"seq": base + 9, "event_id": "x9", "from": "A", "to": ["C"],
               "kind": "grant measurement", "text": "p9"})
    items = [it for it in story.story_items(events, exchanges=xs, milestones=[], depth="said")
             if it["kind"] == "exchange"]
    assert len(items) == 2 and items[0]["n"] == 8 and items[0]["text"].startswith("8× — p1; p2")
    assert items[0]["last_seq"] == base + 8 and "n" not in items[1]


def test_notices_days_lapses_and_compaction_join_the_story(build_run) -> None:
    rd = build_run("r_story_env", extra_events=[
        ("clock.round", {"payload": {"round_no": 1, "rounds_total": 16}}),
        ("environment.event", {"agent_id": "B", "payload": {"environment_event": {
            "target_role_id": "B", "payload": {"case_id": "C-S2", "notice_id": "N-7",
                                               "text": "The port is closed."}}}}),
        ("capacity.deadline_lapse", {"agent_id": "B", "payload": {"case_id": "C-S2", "forced": True}}),
        ("context.compaction", {"agent_id": "B", "payload": {}}),
        ("coordination.report_timeout", {"agent_id": "A", "payload": {"reason": "no report"}}),
    ])
    events = load_events(rd)
    items = story.story_items(events, exchanges=[], milestones=[], depth="notes")
    by = {it["kind"]: it for it in items}
    assert by["notice"]["to"] == ["B"] and "port is closed" in by["notice"]["text"]
    assert by["notice"]["title"] == "C-S2 · N-7"
    texts = [it["text"] for it in items]
    assert "day 1 opens of 16" in texts
    assert any("C-S2 passed its deadline unresolved (closed by the platform)" in t for t in texts)
    assert any("context was compacted" in t for t in texts)
    assert any(it["kind"] == "problem" and it["title"] == "coordination.report_timeout" for it in items)
    # a notice to B is not in A's story
    assert "notice" not in [it["kind"] for it in story.story_items(
        events, exchanges=[], milestones=[], depth="notes", agent="A")]


def test_a_run_without_a_board_is_not_described_as_having_a_forum(build_run) -> None:
    build_run("r_noboard", extra_events=[
        ("message.sent", {"agent_id": "B", "payload": {"to": "A", "kind": "note", "payload_text": "hi"}})])
    client = TestClient(create_app(build_run.runs_root))
    page = client.get("/run/exp/pack/r_noboard/story").text
    assert "milestones only" in page and "the forum" not in page and "had no board" in page
    assert "the forum" not in client.get("/run/exp/pack/r_noboard").text
    build_run("r_board", extra_events=_EVENTS)  # posts to the board: the forum is the spine
    assert "the forum" in client.get("/run/exp/pack/r_board/story").text


def test_a_burst_of_exchanges_folds_across_the_agents_own_steps_only() -> None:
    def it(kind, who, seq, to=("B",), title="grant measurement", text="p"):
        return {"kind": kind, "who": who, "seq": seq, "to": list(to), "title": title, "text": f"{text}{seq}", "e": {}}
    items = [it("exchange", "A", 1), it("said", "A", 2), it("tool", "A", 3), it("exchange", "A", 4),
             it("exchange", "A", 5), it("note", "C", 6), it("exchange", "A", 7)]
    out = story._fold_exchange_runs(items)
    assert [(x["kind"], x.get("n", 1)) for x in out] == [
        ("exchange", 3), ("said", 1), ("tool", 1), ("note", 1), ("exchange", 1)]  # C's note ends the burst
    assert out[0]["last_seq"] == 5 and out[0]["members"] == ["p1", "p4", "p5"]
    other = story._fold_exchange_runs([it("exchange", "A", 1), it("exchange", "A", 2, to=("C",))])
    assert len(other) == 2  # different recipients are different acts
