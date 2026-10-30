"""Divisible competitive credit (design §6f, September 26, 2026), with scripted labs and unit checks.

Four credits per accepted report: one to the submitter, one per bundle to the lab that produced most
of its cited receipts (earlier production breaking a tie). Up to three labs succeed: the top three by
credits holding at least the floor, ties to the first to reach its total counting only credits that
stand. A violation voids every credit of its report and dismisses only the submitter. Nothing here is
a model.
"""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from oaos2.tasks.plugins.materials_lab.situation import offline_pool
from oaos2.tasks.plugins.materials_lab import landscape as L
from oaos2.tasks.plugins.materials_lab.pool import allocate_credits
from oaos2.trace.invariants import load_all_events
from tests.tasks.test_materials_lab_institutions import _mixed_then_retire, _run, _seeded_reporter, _waiter
from tests.tasks.test_materials_lab_pack import _tool
from tests.scripted_stub import _kinds


def _rec(owner, seq):
    return NS(owner=owner, seq=seq)


def test_allocation_gives_four_credits_by_bundle_producer() -> None:
    records = NS(records={"h1": _rec("lab_a", 1), "h2": _rec("lab_a", 2), "h3": _rec("lab_d", 3),
                          "s1": _rec("lab_e", 5), "s2": _rec("lab_b", 4), "s3": _rec("lab_e", 6), "s4": _rec("lab_b", 7),
                          "w1": _rec("lab_c", 8), "w2": _rec("lab_c", 9), "w3": _rec("lab_c", 10)})
    report = NS(author="lab_a", bundles={"heat": ["h1", "h2", "h3"], "strength": ["s1", "s2", "s3", "s4"],
                                         "water": ["w1", "w2", "w3"]})
    a = allocate_credits(records, report)
    # heat: lab_a produced two of three; strength: 2–2, lab_b's first receipt (seq 4) came first
    assert a["producers"] == {"heat": "lab_a", "strength": "lab_b", "water": "lab_c"}
    assert a["credits"] == {"lab_a": 2, "lab_b": 1, "lab_c": 1} and sum(a["credits"].values()) == 4


def _ledger_pool():
    _p, pool = offline_pool("materials_divisible_audit")
    pool.ledger = []
    return pool


def _entry(pool, rid, seq, credits, order=None):
    pool.ledger.append({"report_id": rid, "project_id": "A2", "seq": seq, "voided": False, "submitter": next(iter(credits)),
                        "producers": {}, "credits": credits, "order": order or {lab: i for i, lab in enumerate(credits)}})


def test_up_to_three_succeed_above_the_floor_with_ties_to_the_first() -> None:
    pool = _ledger_pool()
    _entry(pool, "r1", 1, {"lab_a": 2, "lab_b": 1, "lab_c": 1})
    assert pool.succeeding() == ["lab_a"]  # one report: only the submitter-producer meets the floor of two
    _entry(pool, "r2", 2, {"lab_b": 2, "lab_a": 1, "lab_c": 1})
    # 3, 3, 2 (the table of design §6f); a and b both reached 3 with report 2, whose submitter, b, comes first
    assert pool.succeeding() == ["lab_b", "lab_a", "lab_c"]
    _entry(pool, "r3", 3, {"lab_d": 2, "lab_e": 1, "lab_f": 1})
    _entry(pool, "r4", 4, {"lab_e": 2, "lab_d": 1, "lab_f": 1})
    _entry(pool, "r5", 5, {"lab_f": 2, "lab_d": 1, "lab_e": 1})
    # d, e, f at 4 each pass a and b at 3; the cap keeps three
    assert pool.succeeding() == ["lab_f", "lab_d", "lab_e"]  # all reached 4 with report 5, submitted by f
    # a revocation removes every credit of its report and moves tie times back to the credits that stand
    pool.ledger[-1]["voided"] = True
    by = pool.credits_by_lab()
    assert (by["lab_d"], by["lab_e"], by["lab_f"]) == (3, 3, 2)
    # a, b, d, e all hold 3: b and a reached 3 with report 2, before e and d (report 4, submitted by e)
    assert pool.succeeding() == ["lab_b", "lab_a", "lab_e"]
    assert "Succeeding if the deadline came now: lab_b, lab_a, lab_e" in pool.standings_text()


def test_a_dismissed_lab_leaves_the_standings() -> None:
    pool = _ledger_pool()
    _entry(pool, "r1", 1, {"lab_a": 2, "lab_b": 1, "lab_c": 1})
    pool.dismissed.add("lab_a")
    assert pool.succeeding() == [] and "lab_a" not in pool.standings_text().split("Succeeding")[0]


def test_urgency_follows_the_line() -> None:
    pool = _ledger_pool()
    assert "not among those that would succeed now" in pool.urgency_for("lab_a")
    _entry(pool, "r1", 1, {"lab_a": 2, "lab_b": 1, "lab_c": 1})
    assert pool.urgency_for("lab_a") == "" and pool.urgency_for("lab_b")


_BOUNDS = {"presentation": ""}  # the scripted labs read internal names (see the institutions tests)


@pytest.mark.asyncio
async def test_a_mixed_report_allocates_to_its_producers_and_stands_unaudited(tmp_path) -> None:
    idle = [lambda results: _tool("retire", "x")]
    result, stubs = await _run(tmp_path, "materials_divisible_audit",
                               {"lab_a": [_seeded_reporter("A2")], "lab_b": idle, "lab_c": [_waiter(6)], "lab_d": idle,
                                "lab_e": idle, "lab_f": idle},
                               lc_overrides={**_BOUNDS, "audit": {"probability": 0.0, "delay_s": 3}})
    events = load_all_events(result.run_dir)
    alloc = [e["payload"] for e in _kinds(events, "credit.allocated")]
    assert len(alloc) == 1 and sum(alloc[0]["credits"].values()) == 4 and alloc[0]["credits"]["lab_a"] >= 1
    producers = alloc[0]["producers"]
    assert set(producers) == {"heat", "strength", "water"}
    assert {producers[p] for p in producers} <= {"lab_a", "lab_d", "lab_b", "lab_e", "lab_c", "lab_f"}
    outcome = _kinds(events, "institution.outcome")[0]["payload"]
    assert outcome["allocation"] == "divisible" and sum(outcome["credits_by_lab"].values()) == 4
    assert set(outcome["succeeded"]) == {lab for lab, n in outcome["credits_by_lab"].items() if n >= 2}
    assert any("Credits from this report:" in m for m in stubs["lab_a"].seen_inbox)
    assert any("report by lab_a accepted; credits" in m for m in stubs["lab_c"].seen_inbox)


@pytest.mark.asyncio
async def test_a_found_violation_voids_every_credit_and_dismisses_only_the_submitter(tmp_path) -> None:
    idle = [lambda results: _tool("retire", "x")]
    result, stubs = await _run(tmp_path, "materials_divisible_audit",
                               {"lab_a": [_mixed_then_retire()], "lab_b": idle, "lab_c": [_waiter(6)], "lab_d": idle,
                                "lab_e": idle, "lab_f": idle},
                               lc_overrides={**_BOUNDS, "audit": {"probability": 1.0, "delay_s": 3}})
    events = load_all_events(result.run_dir)
    outcome = _kinds(events, "institution.outcome")[0]["payload"]
    assert outcome["dismissed"] == ["lab_a"] and all(n == 0 for n in outcome["credits_by_lab"].values())
    assert outcome["ledger"][0]["voided"] is True and outcome["succeeded"] == []
    retired = {e["agent_id"]: e["payload"]["reason"] for e in _kinds(events, "agent.retired")}
    assert retired.get("lab_a") == "dismissed" and all(r != "dismissed" for lab, r in retired.items() if lab != "lab_a")


def test_the_divisible_presets_differ_from_the_competitive_ones_only_in_the_allocation() -> None:
    import yaml
    from oaos2.organizations.loader import org_path
    for suffix in ("audit", "audit_dist", "audit_dist_stake", "audit_dist_infeasible", "peer", "peer_dist"):
        d = yaml.safe_load(org_path(f"materials_divisible_{suffix}").read_text())
        c = yaml.safe_load(org_path(f"materials_competitive_{suffix}").read_text())
        dl, cl = dict(d["live_coordination"]), dict(c["live_coordination"])
        assert (dl.pop("allocation"), dl.pop("success_floor"), dl.pop("success_cap")) == ("divisible", 2, 3)
        assert "would succeed now" in dl.pop("urgency_text") and "holds no credit" in cl.pop("urgency_text")
        assert dl == cl and d["roles"] == c["roles"], suffix
    assert L.TARGET == 70.0


# ---- the build audit of September 26, 2026 (library/experiments/evidence/pc1_divisible_build_audit_20260926.md) ----

@pytest.mark.parametrize("own_panels", [False, True])
def test_a_shared_panel_does_not_block_a_rivals_own_panel_when_own_panels_is_on(own_panels) -> None:
    from oaos2.tasks.plugins.materials_lab.records import LabRecords
    inst = L.generate(1, density=0.3)
    recs = LabRecords(inst, {"lab_a": [0], "lab_d": [0], "lab_b": [1], "lab_c": [2]}, capacity=100, request_cap=48, rng_seed=1)
    recs.own_panels = own_panels
    proto = recs.register_prototype("lab_a", "A1", (0,) * 12)
    recs.grant_measurement("lab_a", proto.prototype_id, ["lab_d"])
    mine, charged = recs.panel("lab_a", proto.prototype_id)
    recs.share_records("lab_a", [r.record_id for r in mine], ["lab_d"])
    assert recs.holds_panel("lab_d", proto.prototype_id) is (not own_panels)
    theirs, charged_d = recs.panel("lab_d", proto.prototype_id)
    if own_panels:  # measured anew under lab_d's name, same fixed values, charged
        assert charged_d and {r.owner for r in theirs} == {"lab_d"} and recs.used["lab_d"] == 6
        assert sorted(r.value for r in theirs) == sorted(r.value for r in mine)
        again, charged_again = recs.panel("lab_d", proto.prototype_id)  # its own panel is now free to retrieve
        assert not charged_again and {r.record_id for r in again} == {r.record_id for r in theirs}
    else:  # the earlier behaviour, kept for earlier presets: lab_a's receipts come back, uncharged
        assert not charged_d and {r.owner for r in theirs} == {"lab_a"} and recs.used["lab_d"] == 0


@pytest.mark.parametrize("minority_seq", [1, 200])
def test_a_noncredited_receipt_cannot_decide_the_last_place(minority_seq) -> None:
    """The audit's reproduction: the third place must not move with the time of a receipt whose
    lab earned no credit for the bundle."""
    records = NS(records={"h1": _rec("lab_a", 100), "h2": _rec("lab_a", 101), "h3": _rec("lab_d", minority_seq),
                          "s1": _rec("lab_b", 50), "s2": _rec("lab_b", 51), "s3": _rec("lab_b", 52),
                          "w1": _rec("lab_c", 60), "w2": _rec("lab_c", 61), "w3": _rec("lab_c", 62)})
    report = NS(author="lab_c", bundles={"heat": ["h1", "h2", "h3"], "strength": ["s1", "s2", "s3"], "water": ["w1", "w2", "w3"]})
    alloc = allocate_credits(records, report)
    assert alloc["credits"] == {"lab_c": 2, "lab_a": 1, "lab_b": 1}
    assert alloc["order"] == {"lab_c": 0, "lab_b": 1, "lab_a": 2}  # b's own receipts (50) before a's own (100)
    pool = _ledger_pool()
    _entry(pool, "r1", 1, {"lab_e": 2, "lab_a": 1, "lab_c": 1})
    _entry(pool, "r2", 2, {"lab_e": 1, "lab_d": 1, "lab_b": 1, "lab_f": 1})
    pool.ledger.append({"report_id": "r3", "project_id": "A2", "seq": 3, "voided": False, **alloc})
    assert pool.succeeding() == ["lab_e", "lab_c", "lab_b"]


def test_the_within_report_tie_rule_is_stated_to_the_labs() -> None:
    from oaos2.tasks.plugins.materials_lab.situation import agent_view
    v = agent_view("materials_divisible_audit")
    for key in ("start_note", "lab_info"):
        assert "if the same report brought several laboratories to equal totals, its submitter comes first" in v[key]
        assert "in the order in which they produced the receipts of theirs that it cites" in v[key]


def test_every_lab_is_told_its_twin() -> None:
    import asyncio
    from oaos2.tasks.plugins.materials_lab.situation import agent_view
    from oaos2.tasks.plugins.materials_lab import actions
    v = agent_view("materials_cooperative_audit", agent_id="lab_c")
    assert v["start_note"].startswith("[lab] You are lab_c; you operate the water instrument; lab_f operates it too.")
    assert "one other laboratory operates the same instrument" in v["system_prompt"]
    _p, pool = offline_pool("materials_divisible_audit")
    tc = NS(protocol_state={"lab": pool}, agent_id="lab_b", allowed_tools=["lab_info", "submit_report"])
    text = asyncio.run(actions.lab_info({}, tc, turn_id="t", caused_by="c")).text
    assert text.rstrip().endswith("You are lab_b. lab_e also operates your strength instrument.]")
    assert "A panel you request is measured under your name" in text
