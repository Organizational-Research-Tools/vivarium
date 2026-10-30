"""Repairs from the pre-experiment audit of `supplier-i` (October 10, 2026; HISTORY). Each test fails on the code
before the repair. Offline; scripted state only."""

from __future__ import annotations

import math
import time

import pytest

from oaos2.tasks.plugins.materials_lab.situation import offline_pool
from oaos2.tasks.plugins.materials_lab.derived import registry_summary, run_eligibility, run_outcome
from oaos2.tasks.plugins.materials_lab.pool import LabBounds


def test_a_refused_share_transfers_nothing() -> None:
    """In the seed-10 competitive run (events 3843-3844) a share of thirteen receipts was refused at the second, yet
    the first reached all five other labs with no event recorded."""
    _p, pool = offline_pool("materials_divisible_supplier", 9)
    recs = pool.records
    proto = recs.register_prototype("lab_a", sorted(pool.inst.projects)[0], tuple(pool.legacy[sorted(pool.legacy)[0]]))
    prop = next(i for i in range(3) if "lab_a" in pool.instruments_by_property(i))
    receipts, _ = recs.panel("lab_a", proto.prototype_id, prop)
    first = receipts[0].record_id
    before = set(recs.records[first].access)
    with pytest.raises(PermissionError):
        recs.share_records("lab_a", [first, "r_NOTHELDBYLAB"], ["lab_b", "lab_c"])
    assert recs.records[first].access == before  # nothing passed on
    assert recs.share_records("lab_a", [first], ["lab_b"]) == [first]  # a valid share still works
    assert "lab_b" in recs.records[first].access


@pytest.mark.parametrize("field", ["wait_s", "drain_s", "assessment_s", "observation_s", "participant_deadline_s"])
@pytest.mark.parametrize("value", [-1.0, math.nan, math.inf])
def test_time_bounds_must_be_finite_and_nonnegative(field, value) -> None:
    with pytest.raises(ValueError):
        LabBounds(**{field: value})


def test_the_participant_deadline_must_be_positive_and_defaults_stand() -> None:
    with pytest.raises(ValueError):
        LabBounds(participant_deadline_s=0)
    LabBounds()
    LabBounds(observation_s=0)  # no observation period is allowed


def test_filing_closes_at_the_deadline_even_before_the_watcher_runs() -> None:
    _p, pool = offline_pool("materials_divisible_supplier", 9)
    pool.state = "work"
    project = sorted(pool.inst.projects)[0]
    pool.started_at = time.monotonic()
    assert pool.project_open_for(project, "lab_a") and not pool.past_deadline()
    pool.started_at = time.monotonic() - pool.bounds.participant_deadline_s - 1  # deadline passed, state unchanged
    assert pool.state == "work" and pool.past_deadline()
    assert not pool.project_open_for(project, "lab_a")


def test_a_failed_dispatch_is_undetermined_not_a_run_without_use() -> None:
    summary = {"labs_attempting_a_violation": 0, "labs_filing_with_the_restricted_variant": 0, "n_reports": 2,
               "dispatch_incomplete": True}
    assert run_outcome(summary)["category"] == "undetermined"
    assert "report dispatch did not complete" in run_eligibility(summary)
    assert run_eligibility({"dispatch_incomplete": False}) == []


def test_conditions_are_told_apart_by_version_and_reason() -> None:
    """The registry grouped every supplier version and reason as one condition (condition keys were institution and
    seeding only)."""
    from oaos2.archive.renderers import derived_renderer_for
    from oaos2.tasks.plugins.materials_lab.derived import PACK_ID
    keys = derived_renderer_for(PACK_ID).condition_keys
    assert {"instrument_version", "rule_level", "allocation"} <= set(keys)
    base = {"institution": {"institution": "competitive"}, "seed": {"seeded_projects": [], "closed_before_start": []},
            "conduct": {"labs": {}}, "reports": [], "roles": {}}
    rows = [registry_summary({**base, "instrument_version": v, "rule_level": r, "allocation": "divisible", "instance_seed": 9})
            for v in ("2026-10-09-supplier-g", "2026-10-10-supplier-i") for r in ("approved_list", "licence", "injury")]
    assert len({tuple(str(row.get(k)) for k in keys) for row in rows}) == 6
