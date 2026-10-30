"""ClockSpec owns every temporal invariant — these gates pin the refusals.

Structural repair 2026-08-16 item 7: the audit-round failure classes
(missing fuses, horizon overruns, contract/schedule mismatches, sweep
overrides smuggling invalid state) must fail AT LOAD, loudly, in one place.
"""

from __future__ import annotations

import pytest

from oaos2.outcomes.contracts import ClosureCondition, Commitment, OutcomeContract
from oaos2.tasks.clock import ClockSpec, InvalidClockSpec

BLOCK = {"rounds_total": 24,
         "plan_deadline_rounds": {"initial_plan": 4, "final_plan": 24},
         "profiles": ["p_clocked"]}


def _contract(commitments):
    return OutcomeContract(outcome_id="t", commitments=commitments,
                          closure_condition=ClosureCondition())


def _cm(cid, timing=None):
    return Commitment(commitment_id=cid, kind="artifact_submission",
                      timing=dict(timing or {}))


def test_empty_block_means_batched_pack() -> None:
    assert ClockSpec.from_manifest(None) is None
    assert ClockSpec.from_manifest({}) is None


@pytest.mark.parametrize("mutation", [
    {"unknown_key": 1},
    {"rounds_total": 0},
    {"rounds_total": "many"},
    {"calls_per_day": 0},
    {"megabatch": "yes"},
    {"plan_deadline_rounds": {"final_plan": 25}},  # beyond the horizon
    {"plan_deadline_rounds": {"final_plan": 0}},
    {"profiles": []},
])
def test_malformed_blocks_refuse_at_load(mutation) -> None:
    with pytest.raises(InvalidClockSpec):
        ClockSpec.from_manifest({**BLOCK, **mutation})


def test_override_is_validated_and_immutable() -> None:
    spec = ClockSpec.from_manifest(BLOCK)
    out = spec.override({"rounds_total": 36,
                         "plan_deadline_rounds": {"initial_plan": 4,
                                                  "final_plan": 36},
                         "schedule_variant": "r36", "megabatch": False})
    assert (out.rounds_total, out.schedule_variant, out.megabatch) == (36, "r36", False)
    assert spec.rounds_total == 24 and spec.schedule_variant is None  # untouched
    # Pack identity is never sweepable; an override can't smuggle a violation.
    with pytest.raises(InvalidClockSpec):
        spec.override({"profiles": ["other"]})
    with pytest.raises(InvalidClockSpec):
        spec.override({"plan_deadline_rounds": {"final_plan": 99}})


def test_bind_builds_slot_maps_from_timing_metadata() -> None:
    spec = ClockSpec.from_manifest(BLOCK)
    contract = _contract([
        _cm("initial_plan", {"role": "plan"}),
        _cm("file_a", {"role": "filing", "case": "C-1"}),
        _cm("close_a", {"role": "disposition", "case": "C-1"}),
        _cm("rule_log", {"due_with": "final_plan"}),
        _cm("quarter_report", {"due_round": 7}),
        _cm("final_plan", {"role": "plan"}),
        _cm("untimed"),
    ])
    b = spec.bind(contract, {"C-1": {"arrival": 5, "deadline": 8}})
    assert b.disposition_id == {"C-1": "close_a"}
    assert b.case_filings == {"C-1": ["file_a"]}
    assert b.slot_case == {"file_a": "C-1", "close_a": "C-1"}
    assert b.slot_due == {"initial_plan": 4, "final_plan": 24,
                          "file_a": 8, "close_a": 8, "rule_log": 24, "quarter_report": 7}
    # a due_round record is admitted like a due_with record (held until the role's mail
    # through its due round has arrived) — CH2 workload design
    assert {"rule_log", "quarter_report"} <= set(b.due_with_ids)
    with pytest.raises(InvalidClockSpec):
        spec.bind(_contract([_cm("initial_plan", {"role": "plan"}), _cm("late", {"due_round": 25}),
                             _cm("final_plan", {"role": "plan"})]), {})


@pytest.mark.parametrize("commitments,cases", [
    # a fused case with no disposition slot would lapse invisibly
    ([_cm("final_plan", {"role": "plan"})], {"C-1": {"deadline": 8}}),
    # a slot naming a case the stamped schedule does not know
    ([_cm("close_x", {"role": "disposition", "case": "C-9"}),
      _cm("final_plan", {"role": "plan"})], {}),
    # two dispositions for one case
    ([_cm("close_1", {"role": "disposition", "case": "C-1"}),
      _cm("close_2", {"role": "disposition", "case": "C-1"}),
      _cm("final_plan", {"role": "plan"})], {"C-1": {"deadline": 8}}),
    # due_with pointing at a plan without a declared deadline
    ([_cm("log", {"due_with": "missing_plan"}),
      _cm("final_plan", {"role": "plan"})], {}),
    # unknown timing role
    ([_cm("odd", {"role": "quarterly"}),
      _cm("final_plan", {"role": "plan"})], {}),
])
def test_bind_refuses_inconsistent_contracts(commitments, cases) -> None:
    spec = ClockSpec.from_manifest(
        {**BLOCK, "plan_deadline_rounds": {"final_plan": 24}})
    with pytest.raises(InvalidClockSpec):
        spec.bind(_contract(commitments), cases)


def test_a_review_binds_to_its_cases_later_notice() -> None:
    """LK1 context-shift diagnostic: the second disposition of a case a later notice reached is
    due at that notice's stamped deadline and is not actionable before the notice arrives."""
    spec = ClockSpec.from_manifest({**BLOCK, "plan_deadline_rounds": {"final_plan": 24}})
    commitments = [_cm("file_a", {"role": "filing", "case": "C-1"}),
                   _cm("close_a", {"role": "disposition", "case": "C-1"}),
                   _cm("review_a", {"role": "review", "case": "C-1"}),
                   _cm("final_plan", {"role": "plan"})]
    cases = {"C-1": {"arrival": 5, "deadline": 8}}
    news = {"C-1": {"arrival": 11, "deadline": 14, "packet_id": "p", "target_scopes": ["office/x"]}}
    b = spec.bind(_contract(commitments), cases, news)
    assert b.review_id == {"C-1": "review_a"} and b.review_arrival == {"C-1": 11}
    assert b.slot_case["review_a"] == "C-1" and b.slot_due["review_a"] == 14 and b.slot_due["close_a"] == 8
    assert b.disposition_id == {"C-1": "close_a"}          # the first disposition is still the case's
    plain = spec.bind(_contract([c for c in commitments if c.commitment_id != "review_a"]), cases)
    assert plain.review_id == {} and plain.review_arrival == {}
    for bad_commitments, bad_news in (
            (commitments, {}),                                               # a review with no later notice
            ([c for c in commitments if c.commitment_id != "review_a"], news),  # a timed notice with no review
            (commitments + [_cm("review_b", {"role": "review", "case": "C-1"})], news),  # two reviews
            ([c for c in commitments if c.commitment_id != "close_a"], news)):  # a review with no first disposition
        with pytest.raises(InvalidClockSpec):
            spec.bind(_contract(bad_commitments), cases, bad_news)


def test_plan_deadlines_must_name_contract_commitments() -> None:
    spec = ClockSpec.from_manifest(BLOCK)  # names initial_plan + final_plan
    with pytest.raises(InvalidClockSpec):
        spec.bind(_contract([_cm("final_plan", {"role": "plan"})]), {})


def test_profile_tiers_bind_each_profile_to_its_tier() -> None:
    # Estimand correction 2026-08-27: a pack carries BOTH tiers' clocked
    # profiles; each is guarded against the other tier's cells.
    spec = ClockSpec.from_manifest(
        {**BLOCK, "profiles": ["p_clocked", "p_clocked_programmable"],
         "profile_tiers": {"p_clocked": "unprogrammable",
                           "p_clocked_programmable": "programmable"}})
    spec.validate_tier("unprogrammable", "p_clocked")
    spec.validate_tier("programmable", "p_clocked_programmable")
    with pytest.raises(InvalidClockSpec):
        spec.validate_tier("programmable", "p_clocked")
    with pytest.raises(InvalidClockSpec):
        spec.validate_tier("unprogrammable", "p_clocked_programmable")


def test_profile_tiers_must_name_declared_profiles() -> None:
    with pytest.raises(InvalidClockSpec):
        ClockSpec.from_manifest(
            {**BLOCK, "profile_tiers": {"other_profile": "programmable"}})
    with pytest.raises(InvalidClockSpec):
        ClockSpec.from_manifest({**BLOCK, "profile_tiers": ["p_clocked"]})


def test_profile_absent_from_map_falls_back_to_schedule_tier() -> None:
    # Legacy shape: a uniform schedule_tier still guards unmapped profiles.
    spec = ClockSpec.from_manifest(
        {**BLOCK, "schedule_tier": "unprogrammable"})
    spec.validate_tier("unprogrammable", "p_clocked")
    with pytest.raises(InvalidClockSpec):
        spec.validate_tier("programmable", "p_clocked")
    with pytest.raises(InvalidClockSpec):
        spec.validate_tier("programmable")  # profile-less legacy call


def test_override_carries_profile_tiers_through() -> None:
    # Overrides merge onto to_manifest(); the per-profile binding is pack
    # identity and must survive a horizon/variant sweep untouched.
    spec = ClockSpec.from_manifest(
        {**BLOCK, "profile_tiers": {"p_clocked": "unprogrammable"}})
    out = spec.override({"rounds_total": 36,
                         "plan_deadline_rounds": {"initial_plan": 4,
                                                  "final_plan": 36},
                         "schedule_variant": "r36"})
    assert out.profile_tiers == {"p_clocked": "unprogrammable"}
    with pytest.raises(InvalidClockSpec):
        spec.override({"profile_tiers": {}})  # never sweepable
