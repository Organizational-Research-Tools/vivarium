"""The deepened run-unfolding graphs: turn spans, overview swimlane, flow minimap,
cost curve, agent identity colors."""

from __future__ import annotations

import pytest

from oaos2.dashboard import events as ev
from oaos2.dashboard.app import agent_slot


def test_swimlane_turn_spans(rich_run) -> None:
    model = ev.swimlane(ev.load_events(rich_run["run_dir"]))
    spans = [s for s in model["spans"] if s["agent"] == "A" and s["turn"] == "A.t1"]
    assert len(spans) == 1
    assert spans[0]["s0"] < spans[0]["s1"]  # started → completed, in order


def test_agent_slots_fixed_order_never_cycled() -> None:
    agents = [f"a{i}" for i in range(10)]
    slots = agent_slot(agents)
    assert slots["a0"] == 0 and slots["a7"] == 7
    assert slots["a8"] == -1 and slots["a9"] == -1  # overflow folds to gray, never reuses


fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from oaos2.dashboard.app import create_app  # noqa: E402


@pytest.fixture
def client(rich_run):
    return TestClient(create_app(rich_run["runs_root"]))


def test_overview_shows_how_the_run_unfolded(client, rich_run) -> None:
    html = client.get(f"/run/{rich_run['run_ref']}").text
    assert "How the run unfolded" in html and "<svg" in html
    assert "sw-span" in html                       # activity band rendered
    assert 'class="adot-0"' in html                # agent identity dot


def test_flow_minimap_jumps_across_pages(client, rich_run) -> None:
    html = client.get(f"/run/{rich_run['run_ref']}/flow").text
    assert 'class="mmap' in html
    assert "mm-problem" in html                    # the violation is a tall red tick
    assert "mm-commit" in html
    assert "mm-window" in html                     # current reading window shaded
    assert f"#e{rich_run['ids']['violation']}" in html  # tick deep-links to the anchor


def test_audit_cost_curve(client, rich_run, build_run) -> None:
    # rich run has one cost event → curve renders with total label
    html = client.get(f"/run/{rich_run['run_ref']}/audit").text
    assert "cumulative spend over the run" in html
    assert "polyline" in html
    # a capped run draws the cap line and marks blocked dispatches on it
    from tests.dashboard.conftest import PASSED_STATUS
    build_run("r_capline", status=PASSED_STATUS,
              manifest_extra={"extensions": {"cap_usd": 1.0}},
              extra_events=[("cost.recorded", {"agent_id": "A", "payload": {"cost_usd": 0.5}}),
                            ("cost.cap_blocked_dispatch", {"agent_id": "A", "payload": {}})])
    html = client.get("/run/exp/pack/r_capline/audit").text
    assert "cap $1.00" in html
    assert "cap_blocked_dispatch" in html and "cut off here" in html


def test_comms_agent_dots_consistent(client, rich_run) -> None:
    html = client.get(f"/run/{rich_run['run_ref']}/comms").text
    assert 'class="adot-' in html                  # lane labels + volley speakers
    assert "sw-span" in html
