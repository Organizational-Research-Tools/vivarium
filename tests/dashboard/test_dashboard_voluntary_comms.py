"""The voluntary channels (M8 §7) in the read-side views: the board, notes per pair,
registered exchanges, derived threads, communication grants as declared channels, and
posts and notes in recorded use. Delivery, retrieval, and recognition stay separate."""

from __future__ import annotations

from fastapi.testclient import TestClient

from oaos2.archive import design as designlib
from oaos2.archive import exchanges as exchangelib
from oaos2.archive.datasets import compute_metrics
from oaos2.dashboard import events as ev
from oaos2.dashboard import provenance
from oaos2.dashboard.app import create_app
from oaos2.dashboard.events import load_events

_VOLUNTARY = [
    ("board.posted", {"agent_id": "A", "payload": {"seq": 1, "text": "who can measure heat?",
                                                    "recipients": ["B", "C"]}}),
    ("board.retrieved", {"agent_id": "B", "payload": {"since_seq": 0, "from_seq": 1, "to_seq": 1,
                                                       "count": 1, "board_length": 1}}),
    ("message.sent", {"agent_id": "B", "payload": {"to": "A", "kind": "note",
                                                    "payload_text": "[note from B] I can, grant me p1"}}),
    ("notes.retrieved", {"agent_id": "A", "payload": {"count": 1, "from_seq": 1, "to_seq": 1}}),
    ("message.sent", {"agent_id": "A", "payload": {"to": "B", "kind": "note",
                                                    "payload_text": "[note from A] granted"}}),
    ("message.sent", {"agent_id": "coordination", "payload": {"to": "C", "kind": "message",
                                                               "payload_text": "relayed"}}),
]


def _fake_exchanges(events: list[dict]) -> list[dict]:
    """A pack-style exchange between the note and the reply: A grants B after B asks."""
    reply = next(e for e in events if e.get("event_class") == "message.sent"
                 and (e.get("payload") or {}).get("payload_text", "").endswith("granted"))
    return [{"seq": reply["sequence_number"] - 0.5, "event_id": "x-grant", "from": "A",
             "to": ["B"], "kind": "grant measurement", "text": "prototype p1, blind"}]


def test_metrics_count_posts_notes_and_reads(build_run) -> None:
    rd = build_run("r_vol", extra_events=_VOLUNTARY)
    m = compute_metrics(rd, load_events(rd))
    assert (m["n_board_posts"], m["n_notes"], m["n_messages"]) == (1, 2, 3)
    assert (m["n_board_reads"], m["n_note_reads"]) == (1, 1)


def test_comm_view_groups_notes_by_pair_and_builds_threads(build_run) -> None:
    rd = build_run("r_vol", extra_events=_VOLUNTARY)
    events = load_events(rd)
    c = ev.comm_view(events, exchanges=_fake_exchanges(events))
    assert [e["agent_id"] for e in c["board"]] == ["A"]
    assert len(c["notes"]) == 2 and len(c["messages"]) == 1  # notes apart from relays
    assert [p["pair"] for p in c["note_pairs"]] == [("A", "B")]
    assert c["retrievals"] == [
        {"agent": "A", "board_reads": 0, "note_reads": 1, "last_board_seq": None},
        {"agent": "B", "board_reads": 1, "note_reads": 0, "last_board_seq": 1},
    ]
    threads = c["threads"]
    assert [t["request"]["kind"] for t in threads] == ["post", "note", "note"]
    post = threads[0]
    assert post["author"] == "A" and [r["by"] for r in post["replies"]] == ["B", "C"]
    # B's reply window: its note back to A closes it; C did nothing toward A.
    assert [i["kind"] for i in post["replies"][0]["items"]] == ["note"]
    assert post["replies"][1]["items"] == []
    ask = threads[1]  # B's note to A: A's grant, then A's note back, closes the window
    assert ask["author"] == "B" and ask["replies"][0]["by"] == "A"
    assert [i["kind"] for i in ask["replies"][0]["items"]] == ["grant measurement", "note"]
    assert ask["event_ids"][0] == ask["request"]["event_id"] and "x-grant" in ask["event_ids"]


def test_exchange_rows_need_a_registered_adapter_and_drop_malformed_rows() -> None:
    assert exchangelib.exchange_rows("no_such_pack", []) == []
    exchangelib.unregister_exchange_adapter("seampack")
    exchangelib.register_exchange_adapter(exchangelib.ExchangeAdapter(
        pack_id="seampack", rows=lambda events: [
            {"seq": 5, "event_id": "e5", "from": "A", "to": ["C", "B"], "kind": "k", "text": "t"},
            {"seq": 2, "event_id": "e2", "from": "A", "to": [], "kind": "k", "text": "t"},
            {"seq": 9, "event_id": "e9", "from": "A"},  # malformed: dropped, not invented
        ]))
    try:
        rows = exchangelib.exchange_rows("seampack", [])
        assert [r["seq"] for r in rows] == [2, 5] and rows[1]["to"] == ["B", "C"]
    finally:
        exchangelib.unregister_exchange_adapter("seampack")


def test_realization_counts_voluntary_channels(build_run) -> None:
    rd = build_run("r_vol", extra_events=_VOLUNTARY)
    events = load_events(rd)
    real = designlib.realization(events, designlib.run_design(rd), [])
    by_kind = {(c["kind"], c["from"], c["to"]): c for c in real["channels"]}
    assert by_kind[("board", "A", designlib.BOARD)]["used"] == 1
    assert by_kind[("note", "B", "A")]["used"] == 1 and by_kind[("note", "A", "B")]["used"] == 1
    assert not by_kind[("note", "B", "A")]["declared"]  # the pipeline preset grants no notes
    roles = real["roles"]
    assert roles["A"]["posts"] == 1 and roles["A"]["notes_out"] == 1 and roles["A"]["notes_in"] == 1
    assert roles["A"]["note_reads"] == 1 and roles["B"]["board_reads"] == 1


def test_communication_grants_come_from_the_pack_manifest() -> None:
    actions = designlib.communication_actions("materials_lab")
    assert set(actions) == {"post", "read_board", "send_note", "read_notes",
                            "start_thread", "reply", "board_index", "read_thread", "read_post"}
    assert designlib.communication_actions("budget_allocation") == {}
    assert designlib.communication_actions(None) == {}
    org = designlib.organization_of({"organization_id": "materials_peers",
                                     "task_pack_id": "materials_lab"})
    assert org["source"] == "library@HEAD"
    assert all(r["comm_grants"] == ["post", "read_board", "read_notes", "send_note"]
               for r in org["roles"].values())


def test_pool_packs_load_in_the_provenance_snapshot() -> None:
    packs = provenance._library_snapshot()["packs"]
    for pack in ("materials_lab", "python_bug_repair"):
        assert isinstance(packs[pack], dict), f"{pack} must load by its own declared profile"


def test_comms_page_shows_notes_threads_and_codes_in_place(build_run) -> None:
    build_run("r_vol", extra_events=_VOLUNTARY)
    client = TestClient(create_app(build_run.runs_root), follow_redirects=False)
    ref = "exp/pack/r_vol"
    html = client.get(f"/run/{ref}/comms").text
    assert "Board</span> (1)" in html and "who can measure heat?" in html
    assert "Notes</span> (2)" in html and "grant me p1" in html
    assert "Exchange threads</span> (3)" in html and "derived reading aid" in html
    assert "Relayed messages (1)" in html and "relayed" in html
    assert "Exchanges</span> (" not in html  # no adapter for this pack: no invented section
    # Coding a thread returns the reader to the communication page, never elsewhere.
    ids = [line.split('value="')[1].split('"')[0] for line in html.splitlines()
           if 'name="event_ids"' in line]
    schemas = [line.split('value="')[1].split('"')[0] for line in html.splitlines()
               if "<option value=" in line and "label_schema_ref" not in line]
    if ids and schemas:
        r = client.post(f"/run/{ref}/annotate", data={
            "label_schema_ref": schemas[0], "event_ids": ids[0], "note": "n",
            "back": f"/run/{ref}/comms"})
        assert r.status_code == 303 and r.headers["location"] == f"/run/{ref}/comms"
        r = client.post(f"/run/{ref}/annotate", data={
            "label_schema_ref": schemas[0], "event_ids": ids[0], "note": "n",
            "back": "https://elsewhere.example/"})
        assert r.headers["location"].startswith(f"/run/{ref}/")


def test_design_page_lists_grants_and_voluntary_use(build_run) -> None:
    build_run("r_vol", extra_events=_VOLUNTARY)
    client = TestClient(create_app(build_run.runs_root))
    html = client.get("/run/exp/pack/r_vol/design").text
    assert "communication grants" in html and "A → board" in html and "B → A" in html
    assert "notes out / in" in html
