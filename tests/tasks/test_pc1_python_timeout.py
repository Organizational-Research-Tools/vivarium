"""A per-call limit on `run_python` (October 15, 2026): with `python_timeout_s` the script runs under `timeout` in the
sandbox, and a script stopped at the limit comes back to the laboratory as stopped, the run going on; without it the
command is as before. Scripted laboratories and a fake sandbox; no model, no Docker."""

from __future__ import annotations

import dataclasses

import pytest

from oaos2.docker.backend import ExecResult, FakeContainerBackend
from oaos2.experiments.runner import run_org_live
from oaos2.organizations.loader import load_org_spec
from oaos2.trace.invariants import load_all_events
from tests.tasks.test_materials_lab_pack import _ReactiveStub, _tool
from tests.scripted_stub import _FAKE_DIGEST, _kinds


async def _run(tmp_path, limit):
    org = load_org_spec("pc1_supplier_g_xmodel5")
    lc = {**org.live_coordination, "python_timeout_s": limit, "spec_revisions": [], "reminder_minutes": [],
          "bounds": {"wait_s": 3, "drain_s": 2, "assessment_s": 2, "observation_s": 0.3, "participant_deadline_s": 6}}
    roles = [dataclasses.replace(r, tools=[*r.tools, "retire"]) for r in org.roles]
    org = dataclasses.replace(org, live_coordination=lc, roles=roles, tools=[*org.tools, "retire"])
    seen = []

    def exec_fn(handle, argv):
        seen.append(argv)
        return ExecResult(exit_code=124 if "timeout" in argv[-1] else 0, stdout="")
    script = [lambda res: _tool("run_python", "x", code="while True: pass") if len(res) < 1 else _tool("retire", "x")]
    stubs = {r.role_id: _ReactiveStub(script) for r in org.roles}
    order = iter([stubs[r.role_id] for r in org.roles])
    result = await run_org_live(org, tmp_path, tier="main", model_ref="stub/deterministic", experiment_id="exp_pt",
                                task_pack="materials_lab", reasoning_kind="none", cap_usd=5.0, max_model_calls=20,
                                backend=FakeContainerBackend(digest=_FAKE_DIGEST, exec_fn=exec_fn),
                                adapter_factory=lambda: next(order))
    return load_all_events(result.run_dir), seen


@pytest.mark.asyncio
async def test_a_script_past_the_limit_is_stopped_and_the_lab_told(tmp_path):
    events, seen = await _run(tmp_path, 120)
    assert seen and all("timeout -k 5 120 python" in a[-1] for a in seen)
    outs = [e["payload"]["output"] for e in _kinds(events, "tool.result") if e["payload"].get("tool_name") == "run_python"]
    assert outs and all("ran longer than 120 seconds" in o for o in outs)
    assert not _kinds(events, "run.failed")


@pytest.mark.asyncio
async def test_without_a_limit_the_command_is_as_before(tmp_path):
    _events, seen = await _run(tmp_path, None)
    assert seen and all(a[-1].endswith("python _exec_1.py") and "timeout" not in a[-1] for a in seen)
