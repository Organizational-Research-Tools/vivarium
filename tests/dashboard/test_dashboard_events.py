"""D1 data layer: cached event access, filters, prose folding, causal navigation."""

from __future__ import annotations

from oaos2.archive.transcript import _summary
from oaos2.dashboard import events as ev
from oaos2.dashboard import renderers
from tests.dashboard.conftest import PROSE


def test_load_events_memoized_until_stream_changes(rich_run) -> None:
    rd = rich_run["run_dir"]
    first = ev.load_events(rd)
    assert ev.load_events(rd) is first  # same snapshot object = cache hit
    # Append one line → fingerprint changes → reload.
    with (rd / "trace" / "events.jsonl").open("a") as f:
        f.write("\n")
    assert ev.load_events(rd) is not first


def test_event_index_and_causality(rich_run) -> None:
    rd, ids = rich_run["run_dir"], rich_run["ids"]
    by_id = ev.event_index(rd)
    events = ev.load_events(rd)

    tool_result = by_id[ids["tool_result"]]
    parents = ev.parents_of(by_id, tool_result)
    assert ids["tool_called"] in [p["event_id"] for p in parents]
    children = ev.children_of(events, ids["tool_called"])
    assert ids["tool_result"] in [c["event_id"] for c in children]

    # "What led to this commitment?" — the ancestry walks back to run.started.
    outline = ev.ancestry_outline(by_id, ids["commit"])
    assert ids["run_started"] in [a["event_id"] for _, a in outline]
    # …and matches the archive's own transitive walk.
    from oaos2.archive.lineage import causal_ancestors
    assert {a["event_id"] for _, a in outline} == set(causal_ancestors(rd, ids["commit"]))


def test_filters_and_facets(rich_run) -> None:
    events = ev.load_events(rich_run["run_dir"])
    assert all(e["agent_id"] == "A" for e in ev.filter_events(events, agent="A"))
    assert [e["event_class"] for e in ev.filter_events(events, event_class="handoff")] == ["handoff"]
    fams = {ev.family_of(e["event_class"]) for e in ev.filter_events(events, family="conversation")}
    assert fams == {"conversation"}
    hits = ev.filter_events(events, q="housing is the frame")  # matches the volley summary
    assert [e["event_class"] for e in hits] == ["conversation.volley"]
    f = ev.facets(events)
    assert "A" in f["agent"] and "conversation" in f["family"] and "agent" in f["audience"]


def test_prose_and_raw_digest(rich_run) -> None:
    rd, ids = rich_run["run_dir"], rich_run["ids"]
    responded = ev.event_index(rd)[ids["model_responded"]]
    assert ev.prose_for(rd, responded) == PROSE
    assert ev.raw_ref_digest(responded) == rich_run["digest"]


def test_summary_is_the_transcript_summary(rich_run) -> None:
    # The explorer's row text is the SAME function the derived transcripts use —
    # the two readings can never drift (DASHBOARD.md D1 acceptance).
    assert ev.summary is _summary
    events = ev.load_events(rich_run["run_dir"])
    for e in events:
        assert ev.summary(e) == _summary(e)


def test_renderer_registry_notable_text(rich_run) -> None:
    rd, ids = rich_run["run_dir"], rich_run["ids"]
    by_id = ev.event_index(rd)
    assert renderers.notable_text(rd, by_id[ids["model_responded"]]) == [("verbatim prose (raw/)", PROSE)]
    assert renderers.notable_text(rd, by_id[ids["reasoning"]]) == [("thinking", "the floors bind on health")]
    assert renderers.notable_text(rd, by_id[ids["volley"]]) == [("text", "I think housing is the frame")]
    assert renderers.notable_text(rd, by_id[ids["tool_called"]]) == []  # unregistered → payload JSON only

    # The registry is open (a pack may register its own class) and guards collisions.
    renderers.register("pack.custom_event", lambda run_dir, e: [("note", "hi")])
    try:
        assert renderers.notable_text(rd, {"event_class": "pack.custom_event"}) == [("note", "hi")]
        import pytest
        with pytest.raises(ValueError):
            renderers.register("pack.custom_event", lambda run_dir, e: [])
    finally:
        renderers._RENDERERS.pop("pack.custom_event", None)