"""Citations resolve without a server, carry a content digest, and the document
checker catches a missing object, a changed payload, and a misquotation."""

from __future__ import annotations

import json
from pathlib import Path

from oaos2.archive import cite
from oaos2.archive.clock import day_index, day_spans, final_day, rounds_total
from oaos2.archive.transcript import events_in_order
from oaos2.kernel.run_dir import RunDir
from oaos2.trace.spine import RunSpine


async def _run(tmp_path: Path) -> tuple[Path, str, str]:
    rd = RunDir.create(tmp_path / "runs", "exp", "pack", "r1")
    rd.manifest_path.write_text(json.dumps({"run_id": "r1", "experiment_id": "exp",
                                            "organization_id": "o", "mode": "pilot",
                                            "task_pack_id": "pack"}))
    spine = RunSpine(rd.root, run_id="r1")
    await spine.start()
    c = await spine.emit_event("run.started", payload={"run_id": "r1"})
    await spine.emit_event("clock.round", caused_by=c, payload={"round_no": 1, "rounds_total": 3})
    await spine.emit_event("clock.round", caused_by=c, payload={"round_no": 2, "rounds_total": 3})
    h = await spine.emit_event("handoff", agent_id="A", caused_by=c, payload={
        "from_agent": "A", "to_agent": "B", "kind": "handoff",
        "payload_text": "The gymnasium closes this quarter; two units of screening need a home."})
    await spine.emit_event("outcome.closed", caused_by=c, payload={"outcome_id": "main"})
    await spine.finalize("completed")
    sub = rd.root / "captured" / "submitted"
    sub.mkdir(parents=True)
    (sub / "disposition_cs1.json").write_text(json.dumps(
        {"case_id": "C-S1", "detail": "Screening moves to the annex; sessions take the morning block."}))
    return rd.root, "exp/pack/r1", h


async def test_day_projection(tmp_path) -> None:
    run, _, h = await _run(tmp_path)
    events = events_in_order(run)
    days = day_index(events)
    assert days[h] == 2 and days[events[0]["event_id"]] == 0
    spans = day_spans(events)
    assert [s["day"] for s in spans] == [0, 1, 2]
    assert rounds_total(events) == 3 and final_day(events) == 2


async def test_event_citation_round_trip_and_verification(tmp_path) -> None:
    run, ref, h = await _run(tmp_path)
    events = events_in_order(run)
    event = next(e for e in events if e["event_id"] == h)
    c = cite.event_citation(ref, event, day_index(events)[h])
    parsed = cite.parse_citation(c)
    assert parsed["kind"] == "event" and parsed["event_id"] == h and parsed["day"] == 2
    res = cite.resolve(tmp_path / "runs", parsed)
    assert res["ok"] and any("gymnasium" in t for t in res["texts"])
    doc = (f'officer A filed: "two units of screening need a home" — {c}\n'
           f'misquoted: "three units of screening need a home" — {c}\n')
    results = cite.verify_document(tmp_path / "runs", doc)
    assert [r["ok"] for r in results] == [True, True]
    assert results[0]["quotes"][0]["found"] is True
    assert results[1]["quotes"][0]["found"] is False
    # a changed digest is refused
    tampered = c[:-12] + "000000000000"
    bad = cite.resolve(tmp_path / "runs", cite.parse_citation(tampered))
    assert not bad["ok"] and "digest" in bad["problem"]
    # an unknown run is refused, and a ref cannot escape the root
    assert not cite.resolve(tmp_path / "runs", {**parsed, "run_ref": "../etc"})["ok"]


async def test_file_citation(tmp_path) -> None:
    run, ref, _ = await _run(tmp_path)
    data = (run / "captured" / "submitted" / "disposition_cs1.json").read_bytes()
    c = cite.file_citation(ref, "submitted/disposition_cs1.json", data)
    parsed = cite.parse_citation(c)
    assert parsed["kind"] == "file"
    res = cite.resolve(tmp_path / "runs", parsed)
    assert res["ok"] and res["object"]["case_id"] == "C-S1"
    md = cite.excerpt_markdown(citation=c, quote="Screening moves to the annex", cell="o · rep0")
    assert md.startswith("> Screening moves") and c in md
