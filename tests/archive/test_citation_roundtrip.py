from oaos2.archive.cite import event_citation, parse_citation, verify_document
from oaos2.trace.invariants import load_all_events
from oaos2.trace.spine import RunSpine


async def test_run_level_citation_roundtrips_and_resolves(tmp_path):
    root = tmp_path / "e/p/r"
    spine = RunSpine(root, "r")
    await spine.start()
    event_id = await spine.emit_event("run.started")
    await spine.finalize("completed")
    event = next(e for e in load_all_events(root) if e["event_id"] == event_id)
    citation = event_citation("e/p/r", event, None)
    assert parse_citation(citation)["event_id"] == event_id
    assert verify_document(tmp_path, citation)[0]["ok"]
    legacy = citation.replace(" · — · day", " · · · day")
    assert verify_document(tmp_path, legacy)[0]["ok"]


def test_malformed_citation_is_reported_not_skipped(tmp_path):
    checked = verify_document(tmp_path, "Evidence `cite: missing fields`.")
    assert len(checked) == 1
    assert not checked[0]["ok"] and checked[0]["problem"] == "malformed citation"
