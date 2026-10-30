"""The replay (DASHBOARD.md §4.2g): busy intervals and directed acts keyed to the time
since the first event, read from the record; the page embeds them and the lanes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from oaos2.dashboard import replay
from oaos2.dashboard.app import create_app


def _e(seq, cls, agent=None, t=0.0, **payload):
    return {"event_class": cls, "event_id": f"e{seq}", "sequence_number": seq, "timestamp": 1000.0 + t,
            "agent_id": agent, "payload": payload}


def test_busy_intervals_and_acts_are_read_from_the_record() -> None:
    events = [_e(0, "run.started", t=0), _e(1, "model.invoked", "A", t=1), _e(2, "tool.called", "A", t=2),
              _e(3, "model.responded", "A", t=3), _e(4, "tool.result", "A", t=5),
              _e(5, "message.sent", "A", t=6, to="B", kind="note"), _e(6, "board.posted", "B", t=7, text="hi"),
              _e(7, "model.invoked", "B", t=8), _e(8, "handoff", "B", t=9, from_agent="B", to_agent="A")]
    busy = replay.busy_intervals(events, ["A", "B"], 1000.0)
    assert busy["A"] == [[1.0, 5.0]]           # a model call then a tool call, one stretch
    assert busy["B"] == [[8.0, 9.0]]           # still open at the end: runs to the last event
    xs = [{"seq": 7, "event_id": "x", "from": "B", "to": ["A", "C"], "kind": "grant measurement"}]
    acts = replay.acts(events, xs, ["A", "B"], 1000.0)
    assert [(a["t"], a["from"], a["to"], a["kind"]) for a in acts] == [
        (6.0, "A", "B", "note"), (7.0, "B", "board", "post"), (8.0, "B", "A", "grant measurement"),
        (9.0, "B", "A", "handoff")]           # C is not an agent of this run and is left out
    data = replay.replay_data(events, xs, ["A", "B"])
    assert data["timed"] and data["duration"] == 9.0 and data["nodes"] and data["acts"] == acts
    assert replay.replay_data([{"event_class": "x"}], [], [])["timed"] is False


def test_replay_page_renders_with_its_data(build_run) -> None:
    build_run("r_replay", extra_events=[
        ("board.posted", {"agent_id": "A", "payload": {"seq": 1, "text": "who can measure heat?", "recipients": ["B"]}}),
        ("message.sent", {"agent_id": "B", "payload": {"to": "A", "kind": "note", "payload_text": "I can."}})])
    html = TestClient(create_app(build_run.runs_root)).get("/run/exp/pack/r_replay/replay").text
    assert 'id="rdata"' in html and 'id="rscrub"' in html and ">Replay</a>" in html
    assert "The conversation" in html and 'id="rconv"' in html and "I can." in html
    assert "who can measure heat?" in html and 'data-t="' in html



def test_an_empty_record_and_a_near_instant_run_say_so(build_run) -> None:
    import shutil
    rd = build_run("r_fast")  # the fixture's run takes milliseconds, like an offline stub run
    client = TestClient(create_app(build_run.runs_root))
    assert "nearly simultaneous" in client.get("/run/exp/pack/r_fast/replay").text
    (rd / "trace" / "events.jsonl").write_text("")
    for f in (rd / "trace").glob("infra*.jsonl"):
        f.write_text("")
    shutil.rmtree(build_run.runs_root / ".dashboard", ignore_errors=True)
    assert "record is empty" in client.get("/run/exp/pack/r_fast/replay").text



def test_messages_carry_their_text_and_fold_a_broadcast_handoff() -> None:
    ref = {"handoff_delta": {"formalized_payload_ref": "submitted/plan.json"}}
    events = [_e(0, "run.started", t=0),
              _e(1, "message.sent", "A", t=1, to="B", kind="note", payload_text="can you measure heat?"),
              _e(2, "message.sent", "B", t=2, to="A", kind="note", payload_text="yes, sending now"),
              _e(3, "board.posted", "A", t=3, text="thanks all"),
              _e(4, "handoff", "A", t=4, from_agent="A", to_agent="B", payload_text="{}", **ref),
              _e(5, "handoff", "A", t=4, from_agent="A", to_agent="C", payload_text="{}", **ref)]
    xs = [{"seq": 3, "event_id": "x", "from": "B", "to": ["A"], "kind": "grant measurement", "text": "prototype p1"}]
    msgs = replay.messages(events, xs, ["A", "B", "C"], 1000.0)
    assert [(m["from"], m["to"], m["kind"]) for m in msgs] == [
        ("A", ["B"], "note"), ("B", ["A"], "note"), ("A", ["board"], "post"),
        ("B", ["A"], "grant measurement"), ("A", ["B", "C"], "handoff")]
    assert msgs[0]["text"] == "can you measure heat?" and msgs[-1]["text"].startswith("submitted/plan.json")
    assert "ref" not in msgs[-1]
