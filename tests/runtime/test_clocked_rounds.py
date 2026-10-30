"""Clocked-rounds kernel gates (decision (c), clock_design.md §1–§3).

The engine mechanics only: one turn per live role per round, quiescence-driven
advance, fast-forward through empty rounds, and round-stamped arrival dispatch.
Agent cognition is scripted via the behavior seam; the budget_execution pack's
adoption (stamped schedules, per-case slots, v2.1 lateness) is a separate unit.
"""

from __future__ import annotations

import asyncio
import hashlib
import json

import pytest

from oaos2.environment.driver import (
    DeterministicScheduleDriver,
    EnvironmentScheduleError,
)
from oaos2.kernel.clock import ClockState
from oaos2.kernel.run_dir import RunDir
from oaos2.kernel.runtime import ActionPlan, build_runtime, make_agent, run_supervisor
from oaos2.trace.spine import RunSpine


async def _spine(tmp_path):
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = RunSpine(rd.root, run_id="run1")
    await spine.start()
    return rd, spine


async def test_one_turn_per_role_per_round_and_monotone_advance(tmp_path) -> None:
    rd, spine = await _spine(tmp_path)
    turns: list[tuple[str, int]] = []
    rounds_opened: list[int] = []

    def behave():
        async def b(agent, rs, ctx):
            turns.append((agent.agent_id, rs.clock.round_no))
            if rs.clock.round_no >= 3 and agent.agent_id == "A":
                rs.close_outcome()
                return ActionPlan(result="retire")
            return ActionPlan(result="finish_turn")
        return b

    rs = build_runtime(spine, [make_agent("A", behave()), make_agent("B", behave())],
                       scheduler="clocked_rounds")

    async def on_round(round_no: int) -> None:
        rounds_opened.append(round_no)

    rs.clock = ClockState(rounds_total=10, on_round=on_round)
    await asyncio.wait_for(run_supervisor(rs), timeout=10)

    assert rounds_opened == sorted(rounds_opened)  # monotone, no skipped bookkeeping
    assert rounds_opened[0] == 1 and max(rounds_opened) >= 3
    per_round: dict[int, list[str]] = {}
    for agent_id, round_no in turns:
        per_round.setdefault(round_no, []).append(agent_id)
    assert 0 not in per_round  # nobody acts before the first round opens
    for round_no, actors in per_round.items():
        assert len(actors) == len(set(actors)), (round_no, actors)  # ≤1 turn each


async def test_rounds_fast_forward_to_the_next_arrival(tmp_path) -> None:
    """With no ready work, quiescence advances the clock — time passes when
    nobody has work — and the arrival makes the agent ready again."""
    rd, spine = await _spine(tmp_path)
    acted_in: list[int] = []

    async def b(agent, rs, ctx):
        acted_in.append(rs.clock.round_no)
        rs.close_outcome()
        return ActionPlan(result="retire")

    rs = build_runtime(spine, [make_agent("A", b)], scheduler="clocked_rounds")
    ready = {"flag": False}
    rs.readiness = {"A": lambda: ready["flag"]}

    async def on_round(round_no: int) -> None:
        if round_no == 4:
            ready["flag"] = True  # the "arrival": A becomes admittable

    rs.clock = ClockState(rounds_total=10, on_round=on_round)
    await asyncio.wait_for(run_supervisor(rs), timeout=10)
    assert acted_in == [4]  # rounds 1–3 passed without a single wasted turn


async def test_clock_exhaustion_stops_advancing(tmp_path) -> None:
    """Past rounds_total + 1 the clock refuses to advance; the run then ends
    through its normal closure (here: the last round's callback closes it)."""
    rd, spine = await _spine(tmp_path)

    async def never_ready(agent, rs, ctx):  # pragma: no cover — never admitted
        return ActionPlan(result="finish_turn")

    rs = build_runtime(spine, [make_agent("A", never_ready)],
                       scheduler="clocked_rounds")
    rs.readiness = {"A": lambda: False}
    seen: list[int] = []

    async def on_round(round_no: int) -> None:
        seen.append(round_no)
        if round_no >= rs.clock.rounds_total + 1:
            rs.close_outcome()  # the runner's past-final forcing hook lives here

    rs.clock = ClockState(rounds_total=3, on_round=on_round)
    await asyncio.wait_for(run_supervisor(rs), timeout=10)
    assert seen == [1, 2, 3, 4]  # exactly one past-final tick, then closure


def _write_schedule(tmp_path, stamps: dict[str, dict]):
    schedule = {"schema_version": 1, "waves": [{
        "wave_id": "w1", "trigger_commitment_id": "initial_plan",
        "packets": [
            {"packet_id": pid,
             "target_scopes": ["all"],
             "payload": {"text": f"notice {pid}"},
             "classification": {"rule_coverage": "exception",
                                "expected_scopes": ["office/a", "office/b"],
                                **cls}}
            for pid, cls in stamps.items()
        ]}]}
    path = tmp_path / "schedule.json"
    raw = json.dumps(schedule).encode()
    path.write_text(raw.decode())
    return path, "sha256:" + hashlib.sha256(raw).hexdigest()


def test_driver_round_stamps_parse_and_dispatch_once(tmp_path) -> None:
    path, digest = _write_schedule(tmp_path, {
        "p1": {"arrival_round": 1, "response_deadline_round": 3},
        "p2": {"arrival_round": 2},
    })
    driver = DeterministicScheduleDriver(schedule_ref=str(path), content_hash=digest)
    first = driver.packets_at_round(1)
    assert [p.packet_id for p in first] == ["p1"]
    assert first[0].response_deadline_round == 3
    with pytest.raises(EnvironmentScheduleError):
        driver.packets_at_round(1)  # once-only per packet, fail closed
    assert [p.packet_id for p in driver.packets_at_round(2)] == ["p2"]
    driver.assert_complete()  # wave complete via round dispatch alone


def test_driver_rejects_deadline_before_arrival(tmp_path) -> None:
    path, digest = _write_schedule(tmp_path, {
        "p1": {"arrival_round": 4, "response_deadline_round": 2},
    })
    with pytest.raises(EnvironmentScheduleError):
        DeterministicScheduleDriver(schedule_ref=str(path), content_hash=digest)


def test_driver_mode_exclusive_dispatch_fails_closed(tmp_path) -> None:
    path, digest = _write_schedule(tmp_path, {"p1": {"arrival_round": 1}})
    driver = DeterministicScheduleDriver(schedule_ref=str(path), content_hash=digest)
    driver.packets_at_round(1)
    with pytest.raises(EnvironmentScheduleError):
        driver.packets_after("initial_plan")  # same wave via the batched path
