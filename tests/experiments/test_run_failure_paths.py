"""Run-integrity failure paths (M2 §8.3): an isolation breach or a mid-fleet staging
failure fails the RUN loudly — terminal record stamped, no leaked container, error
propagated — never a run that scores and finalizes "completed" over a breached or
half-staged fleet, and never an unfinalized spine."""

from __future__ import annotations

import asyncio

import pytest

from oaos2.docker.isolation import IsolationViolation
from oaos2.kernel.run_dir import RunDir
from oaos2.kernel.runtime import build_runtime, make_agent, run_supervisor
from oaos2.trace.invariants import load_all_events
from oaos2.trace.spine import RunSpine

try:
    from oaos2.docker.backend import FakeContainerBackend
    _HAVE_FAKE = True
except Exception:  # pragma: no cover
    _HAVE_FAKE = False

_FAKE_DIGEST = "sha256:fake"


def _classes(root) -> list[str]:
    return [e["event_class"] for e in load_all_events(root)]


async def test_isolation_violation_in_turn_is_run_fatal(tmp_path) -> None:
    """The agent loop must NOT downgrade an IsolationViolation to agent.failed +
    retire — that would let the run score and finalize "completed" over a breach."""
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = RunSpine(rd.root, run_id="run1")
    await spine.start()

    async def breach(agent, rs, ctx):
        raise IsolationViolation("disk quota exceeded")

    rs = build_runtime(spine, [make_agent("A", breach)], scheduler="free")
    with pytest.raises(BaseExceptionGroup) as ei:  # TaskGroup wraps the propagated breach
        await asyncio.wait_for(run_supervisor(rs), timeout=10)
    assert ei.group_contains(IsolationViolation)
    assert "agent.failed" not in _classes(rd.root)
    await spine.finalize("failed")


async def test_ordinary_agent_error_retires_without_crashing_run(tmp_path) -> None:
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = RunSpine(rd.root, run_id="run1")
    await spine.start()

    async def broken(agent, rs, ctx):
        raise ValueError("cognition bug")

    rs = build_runtime(spine, [make_agent("A", broken)], scheduler="free")
    await asyncio.wait_for(run_supervisor(rs), timeout=10)  # completes: agent retired
    await spine.finalize("completed")
    assert "agent.failed" in _classes(rd.root)


pytestmark_live = pytest.mark.skipif(not _HAVE_FAKE, reason="FakeContainerBackend unavailable")


@pytestmark_live
async def test_mid_fleet_staging_failure_tears_down_and_finalizes(tmp_path) -> None:
    """If staging agent k fails, agents 1..k-1's containers must be torn down and the
    spine finalized "failed" — previously they leaked and the spine had no terminal."""
    from oaos2.experiments.runner import run_org_live
    from oaos2.organizations.presets import pipeline
    from tests.experiments.test_multi_agent_live import _SubmitStubAdapter

    class _FlakyBackend(FakeContainerBackend):
        async def run(self, **kw):
            if sum(1 for c in self.calls if c[0] == "run") >= 1:
                raise RuntimeError("docker daemon flaked")
            return await super().run(**kw)

    backend = _FlakyBackend(digest=_FAKE_DIGEST)
    with pytest.raises(RuntimeError, match="docker daemon flaked"):
        await run_org_live(
            pipeline(), tmp_path, tier="hard", model_ref="stub/deterministic",
            experiment_id="exp_fail", reasoning_kind="none", cap_usd=5.0, max_model_calls=10,
            backend=backend, adapter_factory=_SubmitStubAdapter,
        )
    staged = [a for op, a in backend.calls if op == "run"]
    removed = [a for op, a in backend.calls if op == "remove"]
    assert set(removed) == set(staged)  # every staged container torn down
    run_root = next((tmp_path / "exp_fail").rglob("trace")).parent
    assert "run.failed" in _classes(run_root)  # terminal record stamped


@pytestmark_live
async def test_supervisor_error_finalizes_failed_and_tears_down(tmp_path) -> None:
    """An error escaping the supervisor (e.g. a run-fatal breach inside a turn) must
    still tear down containers, finalize the spine "failed", and propagate."""
    from oaos2.experiments.runner import run_org_live
    from oaos2.organizations.presets import single_agent
    from tests.experiments.test_multi_agent_live import _SubmitStubAdapter

    class _BreachingAdapter(_SubmitStubAdapter):
        async def invoke(self, payload):
            raise IsolationViolation("simulated breach surfacing mid-turn")

    backend = FakeContainerBackend(digest=_FAKE_DIGEST)
    with pytest.raises(BaseExceptionGroup) as ei:
        await run_org_live(
            single_agent(), tmp_path, tier="hard", model_ref="stub/deterministic",
            experiment_id="exp_breach", reasoning_kind="none", cap_usd=5.0, max_model_calls=10,
            backend=backend, adapter_factory=_BreachingAdapter,
        )
    assert ei.group_contains(IsolationViolation)
    assert ("remove", "replicator") in backend.calls or any(op == "remove" for op, _ in backend.calls)
    run_root = next((tmp_path / "exp_breach").rglob("trace")).parent
    assert "run.failed" in _classes(run_root)
