"""Full-system web surface: comms/files/annotation flows, provenance display,
experiment pivot, CSV export, library editor routes, launch gates."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from oaos2.dashboard import workbench  # noqa: E402
from oaos2.dashboard.app import LIVE_CONFIRM_PHRASE, create_app  # noqa: E402


@pytest.fixture
def client(rich_run):
    return TestClient(create_app(rich_run["runs_root"]), follow_redirects=False)


def test_comms_page_threads_and_swimlane(client, rich_run) -> None:
    html = client.get(f"/run/{rich_run['run_ref']}/comms").text
    assert "I think housing is the frame" in html          # volley text, in-thread
    assert "conv1" in html and "mutual_done" in html       # thread header + closure
    assert "the spec, not the numbers" in html             # handoff body
    assert "please review the draft" in html               # message body
    assert "<svg" in html and "Coordination shape" in html # swimlane rendered
    assert f"/run/{rich_run['run_ref']}/event/" in html    # marks deep-link


def test_files_page(client, rich_run) -> None:
    r = client.get(f"/run/{rich_run['run_ref']}/files")
    assert r.status_code == 200  # rich run has no file events → empty-state page
    assert "no file changes" in r.text


def test_provenance_on_registry_and_run_page(client, rich_run) -> None:
    html = client.get("/runs").text
    assert "provenance" in html and "superseded" in html   # pack "pack" is not in the library
    run_html = client.get(f"/run/{rich_run['run_ref']}").text
    assert "removed apparatus" in run_html and "details in Record" in run_html  # one muted line
    record_html = client.get(f"/run/{rich_run['run_ref']}/record").text
    assert "no longer in the library" in record_html       # Record explains WHY
    assert "Historical record" in run_html


def test_registry_csv(client, rich_run) -> None:
    r = client.get("/registry.csv")
    assert r.headers["content-type"].startswith("text/csv")
    assert "r_rich" in r.text and "provenance" in r.text


def test_experiment_pivot_page(client, rich_run) -> None:
    html = client.get("/experiment/exp").text
    assert "Cells" in html and "pass" in html
    assert client.get("/experiment/nope").status_code == 404


def test_audit_diagnostics_listed(client, rich_run) -> None:
    html = client.get(f"/run/{rich_run['run_ref']}/audit").text
    assert "Diagnostics" in html
    assert "Protocol violations" in html                   # the rich run's violation surfaced
    assert "comm_kind_not_permitted" in html


def test_annotation_flow_end_to_end(client, rich_run) -> None:
    # define a lens → code an event → margin mark + coverage appear
    r = client.post("/annotations/schema", data={
        "label_schema_ref": "frame.v1", "namespace": "frame", "arity": "unary",
        "description": "framing moves"})
    assert r.status_code == 303
    eid = rich_run["ids"]["volley"]
    r = client.post(f"/run/{rich_run['run_ref']}/annotate", data={
        "label_schema_ref": "frame.v1", "event_ids": eid, "note": "housing frame asserted"})
    assert r.status_code == 303
    assert "housing frame asserted" in client.get(
        f"/run/{rich_run['run_ref']}/event/{eid}").text
    assert "◆" in client.get(f"/run/{rich_run['run_ref']}/trace?view=full").text
    assert "frame" in client.get(f"/run/{rich_run['run_ref']}/annotations").text
    assert "r_rich" in client.get("/annotations").text     # coverage lists the run
    # bad requests are refused loudly
    assert client.post(f"/run/{rich_run['run_ref']}/annotate", data={
        "label_schema_ref": "frame.v1", "event_ids": "not_an_event"}).status_code == 400
    assert client.post("/annotations/schema", data={
        "label_schema_ref": "frame.v1", "namespace": "frame", "arity": "unary"}).status_code == 400


def test_launch_gates(client, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(workbench, "launch",
                        lambda root, **kw: calls.append(kw) or {"pid": 1, "log": ""})
    # offline: no gate
    r = client.post("/launch", data={"design": "budget_calibration", "execution": "offline"})
    assert r.status_code == 303 and calls[-1]["execution"] == "offline"
    # live without the phrase → refused, nothing spawned
    n = len(calls)
    r = client.post("/launch", data={"design": "budget_calibration", "execution": "live",
                                     "cap_usd": "2.0", "confirm": "yes please"})
    assert r.status_code == 400 and len(calls) == n
    # live without a cap → refused
    r = client.post("/launch", data={"design": "budget_calibration", "execution": "live",
                                     "confirm": LIVE_CONFIRM_PHRASE})
    assert r.status_code == 400 and len(calls) == n
    # phrase + cap → launches with the cap threaded through
    r = client.post("/launch", data={"design": "budget_calibration", "execution": "live",
                                     "cap_usd": "2.0", "confirm": LIVE_CONFIRM_PHRASE})
    assert r.status_code == 303 and calls[-1] == {"design": "budget_calibration",
                                                  "execution": "live", "reps": None,
                                                  "cap_usd": 2.0}
    # unknown design → refused
    assert client.post("/launch", data={"design": "nope", "execution": "offline"}).status_code == 400


def test_library_pages(client) -> None:
    html = client.get("/library").text
    assert "budget_calibration" in html and "budget_allocation" in html
    r = client.get("/library/edit", params={"f": "experiments/budget_calibration.yaml"})
    assert r.status_code == 200 and "Save (validated)" in r.text
    assert client.get("/library/edit", params={"f": "../oaos2/dashboard/app.py"}).status_code == 404

def test_run_tab_rail_on_every_run_page(client, rich_run) -> None:
    ref = rich_run["run_ref"]
    for suffix in ("", "/story", "/organization", "/agents", "/record", "/annotations",
                   "/flow", "/trace", "/comms", "/files", "/audit", "/design"):
        html = client.get(f"/run/{ref}{suffix}", follow_redirects=True).text
        assert 'class="tabs"' in html, suffix
        for tab in ("Overview", "Story", "Organization", "Agents", "Cases", "Record", "Annotations"):
            assert f'>{tab}</a>' in html, (suffix, tab)
        assert ">Days</a>" not in html  # not a clocked run


def test_event_page_steps_by_sequence(client, rich_run) -> None:
    ids = rich_run["ids"]
    html = client.get(f"/run/{rich_run['run_ref']}/event/{ids['tool_called']}").text
    # prev/next links point at the adjacent sequence numbers
    assert "← [" in html and "] →" in html
    assert f"/event/{ids['tool_result']}" in html  # next in stream


def test_plain_language_help_tooltips(client, rich_run) -> None:
    assert 'class="help"' in client.get("/runs").text                   # runs table headers
    assert 'class="help"' in client.get(f"/run/{rich_run['run_ref']}").text  # outcome card
    html = client.get("/annotations").text
    assert "highlighter color" in html                                  # the 'lens' explainer
