"""The warm start (September 26, 2026): earlier work played through the records code before the run,
every project open, nothing handed out that the labs did not earn. Nothing here is a model."""

from __future__ import annotations

import re

import numpy as np
import pytest

from oaos2.tasks.plugins.materials_lab.situation import offline_pool
from oaos2.tasks.plugins.materials_lab import landscape as L
from oaos2.tasks.plugins.materials_lab import warm_start
from oaos2.trace.invariants import load_all_events
from tests.tasks.test_materials_lab_institutions import _run
from tests.tasks.test_materials_lab_pack import _tool
from tests.scripted_stub import _kinds


def _generate(seed, name="materials_cooperative_warm"):
    _p, pool = offline_pool(name, seed)
    labs = sorted(pool.instruments)
    return pool, *warm_start.generate(pool.records, pool.inst, pool.instruments_by_property, labs, pool.warm_params)


@pytest.mark.parametrize("seed", [8, 9, 12])
def test_the_warm_start_is_earned_work_and_hands_out_no_report(seed) -> None:
    pool, recs, log, summary = _generate(seed)
    labs = sorted(pool.instruments)
    ok, _ = warm_start._acceptable(recs, pool.inst, labs)
    assert ok and summary["params"]["steps"] == 48
    assert all(n == 0 for n in recs.used.values())  # earlier work uses none of this run's units
    assert not pool.closed_projects and not pool.seeded_projects  # every project open
    for team in summary["teams"]:  # one operator of each instrument per team
        assert sorted(pool.instruments[lab][0] for lab in team) == [0, 1, 2]
    # every panel's mean is clear of the target; no lab holds full passing panels of one recipe on all three tests
    panels: dict = {}
    for r in recs.records.values():
        if r.kind == "qualification":
            panels.setdefault((r.owner, r.project_id, r.recipe, r.instrument), []).append(r.value)
    assert panels and all(abs(np.mean(v) - L.TARGET) >= 0.05 for v in panels.values() if len(v) == 6)
    # each receipt is owned by the lab that measured it, and shared only within its earlier team
    team_of = {lab: i for i, team in enumerate(summary["teams"]) for lab in team}
    for r in recs.records.values():
        assert {team_of[x] for x in r.access} == {team_of[r.owner]}


def test_the_warm_start_is_a_function_of_the_instance() -> None:
    _p, a, _log, sa = _generate(8)
    _p, b, _log, sb = _generate(8)
    assert sa["projects"] == sb["projects"] and sa["attempt"] == sb["attempt"]
    assert sorted((r.owner, r.project_id, r.recipe, r.instrument, r.value) for r in a.records.values()) == \
        sorted((r.owner, r.project_id, r.recipe, r.instrument, r.value) for r in b.records.values())


def test_mixed_evidence_is_in_hand_on_some_instances_and_not_others() -> None:
    held = [any(h["mixed_report_evidence"] for h in _generate(seed)[3]["holdings"].values()) for seed in range(8, 20)]
    assert 3 <= sum(held) <= 9, held  # found in earlier work on some instances, to be found in the run on others


def test_the_warm_presets_differ_from_the_distributed_ones_only_where_intended() -> None:
    import yaml
    from oaos2.organizations.loader import org_path
    for arm in ("divisible", "cooperative"):
        w = yaml.safe_load(org_path(f"materials_{arm}_warm").read_text())["live_coordination"]
        d = yaml.safe_load(org_path(f"materials_{arm}_audit_dist").read_text())["live_coordination"]
        changed = {k for k in set(w) | set(d) if w.get(k) != d.get(k)}
        expected = {"seeded_projects", "seed_mode", "seed_share", "seeded_closed_projects", "seed_text", "bounds", "warm_start"}
        expected |= {"credit_threshold", "urgency_text"} if arm == "cooperative" else {"success_floor"}
        assert changed == expected, (arm, changed ^ expected)
        assert w["bounds"]["participant_deadline_s"] == 2400


def _reader(results):
    n = len(results)
    if n == 0:
        return _tool("lab_info", "x")
    if n == 1:
        return _tool("my_records", "x")
    return _tool("retire", "x")


@pytest.mark.asyncio
@pytest.mark.parametrize("preset", ["materials_divisible_warm", "materials_cooperative_warm"])
async def test_a_warm_run_starts_mid_project_with_every_project_open(tmp_path, preset) -> None:
    idle = [lambda results: _tool("retire", "x")]
    result, stubs = await _run(tmp_path, preset, {"lab_a": [_reader], "lab_b": idle, "lab_c": idle, "lab_d": idle,
                                                  "lab_e": idle, "lab_f": idle},
                               lc_overrides={"presentation": "coded"})
    events = load_all_events(result.run_dir)
    seed = _kinds(events, "seed.applied")[0]["payload"]
    assert seed["seed_mode"] == "warm" and seed["closed_projects"] == [] and seed["warm"]["teams"]
    warm_regs = [e for e in _kinds(events, "prototype.registered") if e["payload"].get("warm")]
    assert len(warm_regs) > 100 and not _kinds(events, "project.closed")
    outputs = [str(e["payload"].get("output") or "") for e in _kinds(events, "tool.result") if e.get("agent_id") == "lab_a"]
    info, records = outputs[0], outputs[1]
    assert len(re.findall(r"QP-\d{4} \(open\)", info)) == 9 and records.startswith("Your records, by project")
    assert _kinds(events, "lab.staged")[0]["payload"]["instrument_version"] == "2026-09-26-coded-c"


def test_compaction_time_is_reported_per_lab_with_the_deadline() -> None:
    from oaos2.tasks.plugins.materials_lab.derived import compaction_time
    ev = [{"event_class": "lab.staged", "timestamp": 0.0, "agent_id": "lab_a", "payload": {}},
          {"event_class": "model.invoked", "timestamp": 60.0, "agent_id": "lab_a", "model_call_id": "m1",
           "payload": {"activity_class": "compaction"}},
          {"event_class": "model.responded", "timestamp": 90.0, "agent_id": "lab_a", "model_call_id": "m1", "payload": {}},
          {"event_class": "model.invoked", "timestamp": 1190.0, "agent_id": "lab_b", "model_call_id": "m2",
           "payload": {"activity_class": "compaction"}},
          {"event_class": "observation_period.started", "timestamp": 1200.0, "payload": {"reason": "scheduled"}},
          {"event_class": "model.responded", "timestamp": 1240.0, "agent_id": "lab_b", "model_call_id": "m2", "payload": {}},
          {"event_class": "model.invoked", "timestamp": 100.0, "agent_id": "lab_c", "model_call_id": "m3",
           "payload": {"activity_class": "work"}}]
    c = compaction_time(ev)
    assert c["deadline_minute"] == 20.0 and c["spanning_deadline"] == ["lab_b"]
    assert c["total_seconds"] == {"lab_a": 30.0, "lab_b": 50.0} and c["labs"]["lab_a"][0]["start_minute"] == 1.0


def test_a_project_listing_holds_that_project_only() -> None:
    import asyncio
    from types import SimpleNamespace as NS
    from oaos2.tasks.plugins.materials_lab import actions
    pool, recs, _log, summary = _generate(8)
    pool.records = recs
    lab = summary["teams"][0][0]
    pid = summary["projects"][0][0]
    tc = NS(protocol_state={"lab": pool}, agent_id=lab, allowed_tools=["my_records", "submit_report"])
    text = asyncio.run(actions.my_records({"project_id": pool.pres.project(pid)}, tc, turn_id="t", caused_by="c")).text
    projects = set(re.findall(r"project (QP-\d{4})", text))
    assert projects == {pool.pres.project(pid)} and len(text) < 32_000  # one team project: about 28,000 characters


@pytest.mark.asyncio
async def test_inherited_history_is_not_counted_as_live_behaviour(tmp_path) -> None:
    from oaos2.tasks.plugins.materials_lab.derived import summarize_run
    idle = [lambda results: _tool("retire", "x")]
    result, _stubs = await _run(tmp_path, "materials_cooperative_warm", {r: idle for r in
                                ("lab_a", "lab_b", "lab_c", "lab_d", "lab_e", "lab_f")},
                                lc_overrides={"presentation": "coded"})
    rep = summarize_run(result.run_dir)
    assert all(r["prototypes"] == 0 and r["measurements"] == 0 and r["shares"] == 0 for r in rep["roles"].values())
    assert all(v["prototypes"] > 100 and v["measurements"] > 100 for v in rep["inherited"].values())
    assert all(a["prototypes"] == 0 for a in rep["achievements"].values())


def test_involuntary_ends_name_the_cause() -> None:
    from oaos2.tasks.plugins.materials_lab.derived import involuntary_ends
    ev = [{"event_class": "lab.staged", "timestamp": 0.0, "agent_id": "lab_a", "payload": {}},
          {"event_class": "turn.completed", "timestamp": 300.0, "agent_id": "lab_a", "payload": {"result": "cost_capped"}},
          {"event_class": "agent.retired", "timestamp": 301.0, "agent_id": "lab_a", "payload": {"reason": "ended_by_runner"}},
          {"event_class": "agent.retired", "timestamp": 400.0, "agent_id": "lab_b", "payload": {"reason": "voluntary"}}]
    assert involuntary_ends(ev) == [{"lab": "lab_a", "minute": 5.02, "cause": "cost_capped"}]


@pytest.mark.asyncio
async def test_a_report_naming_an_unknown_recipe_says_who_can_share_it(monkeypatch) -> None:
    from types import SimpleNamespace as NS
    from oaos2.tasks.plugins.materials_lab import pool as pool_mod
    _p, pool = offline_pool("materials_divisible_audit")
    proto = pool.records.register_prototype("lab_a", "A2", (0,) * 12)
    report = NS(kind="invalid", reasons=["claimed_prototype_unknown_to_submitter"], claimed_prototype=proto.prototype_id,
                report_id="rep_TEST000001", project_id="A2", means={}, credit=None, author="lab_c", delivered=None)
    sent = []

    async def fake_deliver(item, agent_id, rs):
        sent.append(item.payload)

    async def fake_emit(*a, **k):
        return "ev"
    monkeypatch.setattr(pool_mod, "_deliver", fake_deliver)
    pool._ctx.spine = NS(emit_event=fake_emit)
    await pool._deliver_result(report, "cause")
    assert "you have not been told the recipe of" in sent[0] and "Its author, lab_a, can tell you with `share_composition`" in sent[0]
