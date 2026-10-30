"""CapacityPolicy gates: the ordered ceiling interactions the audits kept
repairing (day/global exhaustion vs the starved slot's declared fallback;
fire-exactly-once; warning at ceiling-1) are policy logic — pinned here in
isolation, independent of the behavior loop."""

from __future__ import annotations

from oaos2.agents.capacity import CapacityPolicy


def _policy(**kw):
    st: dict = {}
    defaults = dict(max_model_calls=10, max_calls_per_turn=3, max_calls_per_slot=2)
    defaults.update(kw)
    return CapacityPolicy(st, **defaults), st


def test_day_budget_resets_per_turn_and_charges_every_provider_call() -> None:
    p, st = _policy()
    p.begin_turn("t1")
    assert not p.day_exhausted()
    p.charge_provider_call()   # work call
    p.charge_provider_call()   # deliberation volley
    p.charge_provider_call()   # compaction — audit round 4 P1-1: every provider call counts
    assert p.day_exhausted()
    p.begin_turn("t2")  # a new working day
    assert not p.day_exhausted()
    assert st["_calls_this_turn"] == 0


def test_global_ceiling_counts_every_provider_call() -> None:
    # Audit round 5 P1-4: deliberation and compaction calls spend the
    # run-global ceiling too, not only main work calls.
    p, st = _policy(max_model_calls=2, max_calls_per_turn=None)
    assert p.call_fraction() == 0.0
    p.charge_provider_call()   # a compaction call
    p.charge_provider_call()   # a work call
    assert p.global_exhausted() and p.call_fraction() == 1.0
    assert st["calls"] == 2


def test_slot_fallback_claims_exactly_once_across_all_exhaustion_paths() -> None:
    # Audit round 4 P1-2: whichever ceiling ends the turn first, the starved
    # slot's contract-declared fallback fires — and only once.
    p, _ = _policy(max_calls_per_slot=1)
    p.bind_slot("slot_a")
    p.charge_slot_call()
    assert p.slot_exhausted("slot_a")
    assert p.claim_slot_fallback("slot_a") is True   # first claimant fires it
    assert p.claim_slot_fallback("slot_a") is False  # day-end retry: already fired
    assert p.claim_slot_fallback("slot_a") is False  # global-cap retry: already fired


def test_slot_fallback_never_claims_below_ceiling_or_without_slot() -> None:
    p, _ = _policy(max_calls_per_slot=2)
    p.bind_slot("slot_a")
    p.charge_slot_call()
    assert p.claim_slot_fallback("slot_a") is False  # below ceiling
    assert p.claim_slot_fallback(None) is False


def test_slot_warning_fires_once_at_final_available_call() -> None:
    p, _ = _policy(max_calls_per_slot=2)
    p.bind_slot("slot_a")
    assert p.claim_slot_warning("slot_a") is False  # 2 calls remain
    p.charge_slot_call()
    assert p.claim_slot_warning("slot_a") is True   # ceiling-1: final call
    assert p.claim_slot_warning("slot_a") is False  # once only


def test_binding_advance_resets_slot_counters() -> None:
    p, st = _policy(max_calls_per_slot=1)
    p.bind_slot("slot_a")
    p.charge_slot_call()
    assert p.slot_exhausted("slot_a")
    p.bind_slot("slot_b")  # the platform advanced the staged binding
    assert not p.slot_exhausted("slot_b")
    assert st["_slot_calls"] == 0 and st["_slot_warned"] is False


def test_unbounded_modes_never_exhaust() -> None:
    p, _ = _policy(max_calls_per_turn=None, max_calls_per_slot=None)
    p.begin_turn("t1")
    for _ in range(50):
        p.charge_provider_call()
        p.charge_slot_call()
    assert not p.day_exhausted()
    assert not p.slot_exhausted("any")
