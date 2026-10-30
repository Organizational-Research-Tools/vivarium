"""The decision-flow view: content inline, cumulative zoom levels, problems never hidden."""

from __future__ import annotations

import pytest

from oaos2.dashboard import events as ev
from tests.dashboard.conftest import PROSE


def _kinds(run_dir, level):
    items = ev.flow_items(run_dir, ev.load_events(run_dir), level)
    return items, {i["kind"] for i in items}


def test_levels_are_cumulative(rich_run) -> None:
    rd = rich_run["run_dir"]
    _, decisions = _kinds(rd, "decisions")
    _, dialogue = _kinds(rd, "dialogue")
    _, reasoning = _kinds(rd, "reasoning")
    _, everything = _kinds(rd, "everything")
    assert decisions <= dialogue <= reasoning <= everything
    assert "commit" in decisions and "handoff" in decisions
    assert "thinking" not in decisions and "say" not in decisions
    assert "say" in dialogue and "volley" in dialogue and "thinking" not in dialogue
    assert "thinking" in reasoning and "tool" in reasoning and "other" not in reasoning
    assert "other" in everything


def test_problems_visible_at_every_level(rich_run) -> None:
    rd = rich_run["run_dir"]
    for level in ev.FLOW_LEVELS:
        items, kinds = _kinds(rd, level)
        assert "problem" in kinds  # the protocol.violation can never be zoomed away
        assert any(i["e"]["event_class"] == "protocol.violation" for i in items)


def test_content_is_inline(rich_run) -> None:
    rd = rich_run["run_dir"]
    items, _ = _kinds(rd, "reasoning")
    by_kind = {}
    for i in items:
        by_kind.setdefault(i["kind"], []).append(i)
    assert any(i["text"] == "the floors bind on health" for i in by_kind["thinking"])
    assert any(i["title"] == "I'll check the register first." for i in by_kind["thinking"])
    assert any(i["text"] == PROSE for i in by_kind["say"])
    assert any("42 rows" in i["text"] for i in by_kind["tool"])
    assert any("the spec, not the numbers" in i["text"] for i in by_kind["handoff"])
    # the commit shows the ACTUAL submitted artifact, read from disk
    commit = by_kind["commit"][0]
    assert '"home52": 52' in commit["text"] and "COMMIT final" in commit["title"]


def test_committed_payload_ref_is_contained(rich_run) -> None:
    # a hostile payload_ref cannot read outside the run dir
    assert ev._committed_payload(rich_run["run_dir"], "../../../../etc/passwd") \
        .startswith("(submitted payload")
    assert ev._committed_payload(rich_run["run_dir"], None) == ""


def test_long_text_folds(rich_run) -> None:
    body, folded = ev._fold("x" * 2000)
    assert len(body) == 1400 and len(folded) == 600
    body, folded = ev._fold("short")
    assert body == "short" and folded == ""


def test_flow_groups_break_on_agent_turn(rich_run) -> None:
    items = ev.flow_items(rich_run["run_dir"], ev.load_events(rich_run["run_dir"]), "everything")
    groups = ev.flow_groups(items)
    assert len(groups) > 1
    for g in groups:
        assert {(i["e"].get("agent_id") or "·") for i in g["items"]} == {g["agent"]}


# --- the web surface ---------------------------------------------------------- #

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from oaos2.dashboard.app import create_app  # noqa: E402


@pytest.fixture
def client(rich_run):
    return TestClient(create_app(rich_run["runs_root"]))


def test_flow_page_reasoning_default(client, rich_run) -> None:
    html = client.get(f"/run/{rich_run['run_ref']}/flow").text
    assert "the floors bind on health" in html      # thinking inline
    assert PROSE in html                            # utterance inline
    assert "42 rows" in html                        # tool output inline
    assert "home52" in html and "COMMIT final" in html  # submitted artifact inline (quotes escape)
    assert "Problem moments" in html and "Protocol violations" in html
    assert f"e{rich_run['ids']['violation']}" in html  # anchor jump target


def test_flow_zoom_out_hides_reasoning_keeps_problems(client, rich_run) -> None:
    html = client.get(f"/run/{rich_run['run_ref']}/flow", params={"level": "decisions"}).text
    assert "the floors bind on health" not in html
    assert PROSE not in html
    assert "COMMIT final" in html and "HANDOFF A → B" in html
    assert "comm_kind_not_permitted" in html        # the problem stays visible


def test_flow_agent_filter(client, rich_run) -> None:
    html = client.get(f"/run/{rich_run['run_ref']}/flow",
                      params={"level": "everything", "agent": "B"}).text
    assert "housing is the frame" in html           # B's volley
    assert "the floors bind on health" not in html  # A's thinking filtered out
    # the findings strip still lists every problem, linking off-page ones by event
    assert "Problem moments" in html