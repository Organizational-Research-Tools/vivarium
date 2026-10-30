"""The PI's clean stop (experiments/stop.py; the PI, October 21, 2026), offline.

A PC1 run interrupted with ``kill -INT`` went on to its scheduled end (four of five runs on
October 21). Here a stop is requested in the middle of a simulated materials-lab run whose
deadline is a minute away: the run must end within seconds, record the stop, retire every
laboratory, end the work period on the record, make no model call after the stop, finalize
with a valid archive and remove every container. The signal handler is checked separately:
a first SIGINT asks for the stop, a second forces an exit."""

from __future__ import annotations

import asyncio
import dataclasses
import os
import signal
import time

from oaos2.archive.registry import disposition as run_disposition
from oaos2.docker.backend import FakeContainerBackend
from oaos2.experiments.runner import run_org_live
from oaos2.experiments.stop import FORCED_EXIT_CODE, RunStop, install_signal_stop
from oaos2.organizations.loader import load_org_spec
from oaos2.trace.invariants import load_all_events
from tests.tasks.test_materials_lab_pack import _ReactiveStub
from tests.scripted_stub import _FAKE_DIGEST, _kinds, _tool


async def test_a_stop_mid_run_ends_it_cleanly_with_a_valid_archive(tmp_path) -> None:
    org = load_org_spec("materials_trio")
    org = dataclasses.replace(org, live_coordination={**(org.live_coordination or {}), "bounds": {
        "wait_s": 30, "drain_s": 1, "assessment_s": 1, "observation_s": 30.0, "participant_deadline_s": 60.0}})
    # every laboratory keeps working (a lab_info call per turn) until something ends the run
    stubs = {r.role_id: _ReactiveStub([lambda results: _tool("lab_info", "x")]) for r in org.roles}
    order = iter([stubs[r.role_id] for r in org.roles])
    backend = FakeContainerBackend(digest=_FAKE_DIGEST)
    stop = RunStop()

    async def stop_soon():
        await asyncio.sleep(1.5)
        stop.request("SIGINT")

    t0 = time.monotonic()
    stopper = asyncio.create_task(stop_soon())
    result = await run_org_live(
        org, tmp_path, tier="main", model_ref="stub/deterministic", experiment_id="exp_clean_stop",
        task_pack="materials_lab", reasoning_kind="none", cap_usd=5.0, max_model_calls=10_000,
        backend=backend, adapter_factory=lambda: next(order), stop=stop)
    await stopper
    elapsed = time.monotonic() - t0
    assert elapsed < 30, f"the run went on for {elapsed:.0f} s after the stop"

    events = load_all_events(result.run_dir)
    stops = _kinds(events, "run.stop_requested")
    assert len(stops) == 1 and stops[0]["payload"]["signal"] == "SIGINT" and stops[0]["payload"]["by"] == "pi"
    obs = _kinds(events, "observation_period.started")
    assert obs and obs[0]["payload"]["reason"] == "stopped_by_pi" and obs[0]["payload"]["bound_s"] == 0
    retired = {e["agent_id"]: e["payload"]["reason"] for e in _kinds(events, "agent.retired")}
    assert set(retired) == {r.role_id for r in org.roles} and set(retired.values()) == {"stopped_by_pi"}
    # no model call is dispatched after the stop (a call already in flight may still settle)
    stop_seq = stops[0]["sequence_number"]
    late = [e for e in _kinds(events, "model.invoked") if e["sequence_number"] > stop_seq]
    assert not late, f"{len(late)} model calls were dispatched after the stop"
    assert _kinds(events, "run.completed") and not _kinds(events, "run.failed")
    assert result.archive_valid is True

    staged = [a for op, a in backend.calls if op == "run"]
    removed = [a for op, a in backend.calls if op == "remove"]
    assert staged and set(removed) == set(staged)  # every container torn down

    disp = run_disposition(result.run_dir, events)
    assert disp["disposition"] == "completed" and disp["stopped_by_pi"] is True
    assert disp["terminal_reason"] == "stopped_by_pi"


async def test_the_first_signal_asks_for_a_stop_and_a_second_forces_an_exit() -> None:
    stop, exits, notes = RunStop(), [], []

    class _Out:
        def write(self, text):
            notes.append(text)

        def flush(self):
            pass

    loop = asyncio.get_running_loop()
    install_signal_stop(stop, loop, out=_Out(), force_exit=exits.append)
    try:
        os.kill(os.getpid(), signal.SIGINT)
        await asyncio.wait_for(stop.requested.wait(), 2)
        assert stop.signal_name == "SIGINT" and exits == []
        os.kill(os.getpid(), signal.SIGTERM)
        for _ in range(200):
            if exits:
                break
            await asyncio.sleep(0.01)
        assert exits == [FORCED_EXIT_CODE]
        assert any("stopping the run cleanly" in n for n in notes) and any("forcing an exit" in n for n in notes)
    finally:
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(signum)


def test_a_stop_request_is_recorded_once() -> None:
    stop = RunStop()
    assert stop.request("SIGTERM") is True and stop.request("SIGINT") is False
    assert stop.signal_name == "SIGTERM" and stop.is_requested


async def test_a_stop_ends_a_t1_run_cleanly_too(tmp_path) -> None:
    """The T1 line's pool (materials_t1, used by G4 and G5) takes the same stop and records it as its end reason."""
    org = load_org_spec("t1_organic_interface")
    org.live_coordination = dict(org.live_coordination, bounds=dict(
        org.live_coordination["bounds"], participant_deadline_s=60.0, observation_s=30, drain_s=1, prose_wait_s=1))
    stubs = {r.role_id: _ReactiveStub([lambda results: _tool("lab_info", "x")]) for r in org.roles}
    order = iter([stubs[r.role_id] for r in org.roles])
    backend = FakeContainerBackend(digest=_FAKE_DIGEST)
    stop = RunStop()

    async def stop_soon():
        await asyncio.sleep(1.5)
        stop.request("SIGTERM")

    t0 = time.monotonic()
    stopper = asyncio.create_task(stop_soon())
    result = await run_org_live(
        org, tmp_path, tier="main", model_ref="stub/deterministic", experiment_id="exp_clean_stop_t1",
        task_pack="materials_t1", reasoning_kind="none", cap_usd=5.0, max_model_calls=10_000,
        backend=backend, adapter_factory=lambda: next(order), stop=stop)
    await stopper
    assert time.monotonic() - t0 < 30
    events = load_all_events(result.run_dir)
    assert _kinds(events, "run.stop_requested")[0]["payload"]["signal"] == "SIGTERM"
    assert _kinds(events, "observation_period.started")[0]["payload"]["reason"] == "stopped_by_pi"
    assert _kinds(events, "run.completed") and result.archive_valid is True
    staged = [a for op, a in backend.calls if op == "run"]
    assert staged and set(a for op, a in backend.calls if op == "remove") == set(staged)


def test_the_g5_round_launcher_passes_one_stop_to_its_running_jobs() -> None:
    """scripts/g5_round_launch.py (October 21, 2026): a first signal starts no further job and passes one SIGINT to each
    running job, which then stops cleanly; a second passes another, which forces them."""
    import io
    import signal as _signal

    from scripts.g5_round_launch import make_stop_handler

    class _Proc:
        def __init__(self):
            self.sent = []

        def send_signal(self, sig):
            self.sent.append(sig)

    running, stop, out = {0: _Proc(), 1: _Proc()}, {}, io.StringIO()
    handle = make_stop_handler(running, stop, out=out)
    handle(_signal.SIGTERM, None)
    assert stop["signals"] == 1 and all(p.sent == [_signal.SIGINT] for p in running.values())
    handle(_signal.SIGINT, None)
    assert all(p.sent == [_signal.SIGINT, _signal.SIGINT] for p in running.values())
    assert "stop cleanly" in out.getvalue() and "forcing" in out.getvalue()
