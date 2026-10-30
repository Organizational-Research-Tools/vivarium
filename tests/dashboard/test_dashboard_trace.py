"""D1 web surface: trace explorer, event inspector, audit page, raw payload serving."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from oaos2.dashboard.app import create_app  # noqa: E402
from tests.dashboard.conftest import PROSE  # noqa: E402


@pytest.fixture
def client(rich_run):
    return TestClient(create_app(rich_run["runs_root"]))


def _row(cls: str) -> str:
    """A rendered table-row cell (the filter selects also carry class NAMES)."""
    return f"<code>{cls}</code>"


def test_trace_clean_view_folds_prose(client, rich_run) -> None:
    html = client.get(f"/run/{rich_run['run_ref']}/trace").text
    assert PROSE in html                          # the verbatim utterance, folded from raw/
    assert _row("model.responded") not in html    # the telemetry line stays out of clean
    assert "says" in html


def test_trace_full_view_shows_everything(client, rich_run) -> None:
    html = client.get(f"/run/{rich_run['run_ref']}/trace", params={"view": "full"}).text
    for cls in ("run.started", "model.responded", "protocol.violation", "state.committed"):
        assert _row(cls) in html
    assert "read_file" in html  # tool summary text = the transcript's _summary output


def test_trace_filters(client, rich_run) -> None:
    ref = rich_run["run_ref"]
    html = client.get(f"/run/{ref}/trace", params={"view": "full", "agent": "B"}).text
    assert _row("conversation.volley") in html and _row("tool.called") not in html
    html = client.get(f"/run/{ref}/trace", params={"view": "full", "family": "tool"}).text
    assert _row("tool.called") in html and _row("handoff") not in html
    html = client.get(f"/run/{ref}/trace", params={"view": "full", "q": "review the draft"}).text
    assert _row("message.sent") in html and _row("cost.recorded") not in html


def test_trace_pagination(client, rich_run) -> None:
    ref = rich_run["run_ref"]
    p1 = client.get(f"/run/{ref}/trace", params={"view": "full", "page_size": 5}).text
    p2 = client.get(f"/run/{ref}/trace", params={"view": "full", "page_size": 5, "page": 2}).text
    assert "page 1" in p1 and "page 2" in p2
    assert _row("run.started") in p1 and _row("run.started") not in p2


def test_event_inspector(client, rich_run) -> None:
    ref, ids = rich_run["run_ref"], rich_run["ids"]
    r = client.get(f"/run/{ref}/event/{ids['model_responded']}")
    assert r.status_code == 200
    assert PROSE in r.text                                # notable text via renderer
    assert rich_run["digest"][:16] in r.text              # raw payload link
    assert ids["model_invoked"] in r.text                 # parent link

    r = client.get(f"/run/{ref}/event/{ids['commit']}")
    assert "recorded predecessors" in r.text and ids["run_started"] in r.text

    r = client.get(f"/run/{ref}/event/{ids['reasoning']}")
    assert "the floors bind on health" in r.text          # thinking surfaced

    assert client.get(f"/run/{ref}/event/no_such_event").status_code == 404


def test_deep_links_from_trace_to_inspector(client, rich_run) -> None:
    ref, ids = rich_run["run_ref"], rich_run["ids"]
    html = client.get(f"/run/{ref}/trace", params={"view": "full"}).text
    assert f"/run/{ref}/event/{ids['handoff']}" in html


def test_audit_page(client, rich_run) -> None:
    r = client.get(f"/run/{rich_run['run_ref']}/audit")
    assert r.status_code == 200
    assert "protocol.violation" in r.text and "comm_kind_not_permitted" in r.text
    assert "pause_timeout" in r.text                      # intervention listed
    assert "$0.0123" in r.text and "$0.01" in r.text      # ledger row + total
    assert rich_run["ids"]["violation"] in r.text         # linked into the explorer


def test_raw_payload_route(client, rich_run) -> None:
    ref, digest = rich_run["run_ref"], rich_run["digest"]
    r = client.get(f"/run/{ref}/rawpayload/{digest}")
    assert r.status_code == 200 and PROSE in r.text
    assert client.get(f"/run/{ref}/rawpayload/{'0' * 64}").status_code == 404   # absent
    assert client.get(f"/run/{ref}/rawpayload/not-a-digest").status_code == 404  # malformed


def test_run_page_links_to_explorer(client, rich_run) -> None:
    html = client.get(f"/run/{rich_run['run_ref']}").text
    assert f"/run/{rich_run['run_ref']}/trace" in html
    assert f"/run/{rich_run['run_ref']}/audit" in html
