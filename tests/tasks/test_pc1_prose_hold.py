"""A lab that ends a turn in prose (October 12, 2026, the PI): with `prose_wait_s` it resumes after the bound and is
told the run continues; without it, it waits until something arrives, as before. Scripted labs; no model."""

from __future__ import annotations

import dataclasses

import pytest

from oaos2.docker.backend import FakeContainerBackend
from oaos2.experiments.runner import run_org_live
from oaos2.organizations.loader import load_org_spec
from oaos2.trace.invariants import load_all_events
from tests.tasks.test_materials_lab_pack import _ReactiveStub, _tool
from tests.scripted_stub import _FAKE_DIGEST, _kinds


class _Prose(_ReactiveStub):
    """A lab whose first two turns end in a status message without a tool call, then reads and retires."""

    def __init__(self, script):
        super().__init__(script)
        self.calls = 0

    async def invoke(self, payload):
        self.calls += 1
        raw = await super().invoke(payload)
        if self.calls <= 2:
            return type(raw)(payload={**raw.payload, "blocks": [{"kind": "text", "text": "Status: nothing to do."}],
                                      "stop": "end_turn"})
        return raw


async def _run(tmp_path, prose_wait_s):
    org = load_org_spec("pc1_supplier_g_xmodel")
    bounds = {"wait_s": 5, "drain_s": 2, "assessment_s": 2, "observation_s": 0.3, "participant_deadline_s": 12,
              "prose_wait_s": prose_wait_s}
    lc = {**org.live_coordination, "bounds": bounds, "spec_revisions": [], "reminder_minutes": []}
    # a lab with `retire` is retired, not held, when it ends a turn without an action; only the quiet ones get it
    roles = [r if r.role_id == "lab_a" else dataclasses.replace(r, tools=[*r.tools, "retire"]) for r in org.roles]
    org = dataclasses.replace(org, live_coordination=lc, roles=roles, tools=[*org.tools, "retire"])
    quiet = [lambda results: _tool("retire", "x")]
    stubs = {r.role_id: (_Prose([lambda results: _tool("lab_info", "x") if len(results) < 1 else _tool("wait", "x")])
                         if r.role_id == "lab_a" else _ReactiveStub(quiet)) for r in org.roles}
    order = iter([stubs[r.role_id] for r in org.roles])
    result = await run_org_live(org, tmp_path, tier="main", model_ref="stub/deterministic", experiment_id="exp_prose",
                                task_pack="materials_lab", reasoning_kind="none", cap_usd=5.0, max_model_calls=40,
                                backend=FakeContainerBackend(digest=_FAKE_DIGEST), adapter_factory=lambda: next(order))
    return load_all_events(result.run_dir), stubs["lab_a"]


@pytest.mark.asyncio
async def test_a_lab_that_ends_a_turn_in_prose_resumes_after_the_bound(tmp_path):
    events, lab_a = await _run(tmp_path, prose_wait_s=1)
    waits = [e["payload"] for e in _kinds(events, "agent.waiting")
             if e["agent_id"] == "lab_a" and e["payload"].get("reason") == "no_action"]
    assert waits and all(w["bound_s"] == 1 for w in waits)
    woken = [e["payload"]["reason"] for e in _kinds(events, "agent.woken") if e["agent_id"] == "lab_a"]
    assert "bound" in woken
    assert lab_a.calls >= 3  # it came back after each prose turn and went on to act
    assert any("The run continues." in s for s in lab_a.seen_inbox)


@pytest.mark.asyncio
async def test_without_the_bound_a_lab_that_ends_a_turn_in_prose_waits_as_before(tmp_path):
    events, lab_a = await _run(tmp_path, prose_wait_s=0)
    waits = [e["payload"] for e in _kinds(events, "agent.waiting")
             if e["agent_id"] == "lab_a" and e["payload"].get("reason") == "no_action"]
    assert waits and waits[0]["bound_s"] is None
    woken = [e["payload"]["reason"] for e in _kinds(events, "agent.woken") if e["agent_id"] == "lab_a"]
    assert "bound" not in woken  # it resumed only when something arrived (the deadline's notice), as before
    assert not any("The run continues." in t for t in lab_a.seen_inbox)
