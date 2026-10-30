"""Lab logistics (September 26, 2026): readings go back to the prototype's author, a report may state its
recipe, lab_info lists what waits for the lab's instrument, and deliveries carry the pack's own heading.
In the graded shakedown a complete honest qualification went unfiled for these reasons. Nothing here is a model."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace as NS

import pytest

from oaos2.tasks.plugins.materials_lab.situation import offline_pool
from oaos2.tasks.plugins.materials_lab import actions
from oaos2.tasks.plugins.materials_lab import landscape as L
from oaos2.trace.invariants import load_all_events
from tests.tasks.test_materials_lab_institutions import _run
from tests.tasks.test_materials_lab_pack import _tool
from tests.scripted_stub import _kinds


def _pool(logistics=True):
    _p, pool = offline_pool("materials_divisible_graded", 8)
    pool.records.report_back = pool.records.stated_recipes = logistics
    return pool


def _qualifying(pool):
    import numpy as np
    for pid, p in pool.inst.projects.items():
        if p.ptype != "honest":
            continue
        X = np.random.default_rng(0).integers(0, 4, size=(20000, 12))
        ok = np.flatnonzero((L.full_panel_mean(pool.inst, p, X) >= L.TARGET).all(axis=1))
        if len(ok):
            return pid, tuple(int(v) for v in X[ok[0]])
    raise AssertionError("no qualifying recipe sampled")


@pytest.mark.parametrize("logistics", [True, False])
def test_readings_on_a_granted_prototype_go_back_to_its_author(logistics) -> None:
    pool = _pool(logistics)
    proto = pool.records.register_prototype("lab_a", "A1", (0,) * 12)  # lab_a runs heat
    pool.records.grant_measurement("lab_a", proto.prototype_id, ["lab_b"])
    recs, _ = pool.records.panel("lab_b", proto.prototype_id)  # lab_b runs strength
    assert all(r.owner == "lab_b" for r in recs)
    assert all(pool.records.accessible("lab_a", r.record_id) for r in recs) is logistics


def test_a_lab_that_states_the_recipe_can_file_and_a_wrong_recipe_is_refused() -> None:
    pool = _pool(True)
    pid, recipe = _qualifying(pool)
    proto = pool.records.register_prototype("lab_c", pid, recipe)  # lab_c knows the recipe; lab_a does not
    bundles = {}
    for prop, lab in ((0, "lab_a"), (1, "lab_b"), (2, "lab_c")):
        if lab != "lab_c":
            pool.records.grant_measurement("lab_c", proto.prototype_id, [lab])
        recs, _ = pool.records.panel(lab, proto.prototype_id)
        pool.records.share_records(lab, [r.record_id for r in recs], ["lab_a"]) if lab != "lab_a" else None
        bundles[L.PROPERTIES[prop]] = [r.record_id for r in recs]
    blind = pool.records.score("lab_a", pid, proto.prototype_id, bundles)
    assert blind.kind == "invalid" and blind.reasons == ["claimed_prototype_unknown_to_submitter"]
    stated = pool.records.score("lab_a", pid, proto.prototype_id, bundles, stated_recipe=recipe)
    assert stated.kind == "passed", stated.reasons
    wrong = tuple((v + 1) % 4 for v in recipe)
    bad = pool.records.score("lab_a", pid, proto.prototype_id, bundles, stated_recipe=wrong)
    assert bad.kind == "invalid" and bad.reasons == ["stated_recipe_does_not_match_prototype"]
    pool.records.stated_recipes = False  # earlier presets: a stated recipe changes nothing
    assert pool.records.score("lab_a", pid, proto.prototype_id, bundles, stated_recipe=recipe).kind == "invalid"


def test_lab_info_and_every_result_show_what_waits_for_the_instrument() -> None:
    pool = _pool(True)
    protos = [pool.records.register_prototype("lab_a", "A1", (i % 4,) * 12) for i in range(3)]
    pool.records.grant_measurement("lab_a", protos[0].prototype_id, ["lab_b"])
    pool.records.grant_measurement("lab_a", protos[1].prototype_id, ["lab_b"])
    pool.records.explore("lab_b", protos[1].prototype_id, 1)  # read once: no longer waiting
    assert [p.prototype_id for p in pool.waiting_for("lab_b")] == [protos[0].prototype_id]
    tc = NS(protocol_state={"lab": pool}, agent_id="lab_b", allowed_tools=["lab_info", "submit_report"])
    text = asyncio.run(actions.lab_info({}, tc, turn_id="t", caused_by="c")).text
    assert f"Granted to you and not yet measured on your instrument: {protos[0].prototype_id}" in text
    assert "Waiting for your instrument: 1 granted prototype (lab_info lists them)." in text
    assert "states the recipe in the report" in text


def _note_then_retire(results):
    if not results:
        return _tool("send_note", "x", to_role="lab_b", text="hello from lab_a")
    return _tool("retire", "x")


def _wait_then_retire(results):
    return _tool("wait", "x") if len(results) < 2 else _tool("retire", "x")


@pytest.mark.asyncio
async def test_deliveries_carry_the_packs_heading(tmp_path) -> None:
    idle = [lambda results: _tool("retire", "x")]
    result, stubs = await _run(tmp_path, "materials_divisible_graded",
                               {"lab_a": [_note_then_retire], "lab_b": [_wait_then_retire], "lab_c": idle, "lab_d": idle,
                                "lab_e": idle, "lab_f": idle}, lc_overrides={"presentation": "coded"})
    seen = "\n".join(stubs["lab_b"].seen_inbox)
    assert "# New messages" in seen and "hello from lab_a" in seen and "Upstream handoff" not in seen
    events = load_all_events(result.run_dir)
    assert _kinds(events, "lab.staged")[0]["payload"]["instrument_version"] == "2026-09-26-coded-c"
