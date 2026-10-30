"""Hard per-role enforcement + cost-parity wiring (DESIGN §18.1, §8, §9; M7 §4)."""

from __future__ import annotations

from types import SimpleNamespace

from oaos2.agents.tools import ToolContext, dispatch_tool
from oaos2.experiments.design import ParityPolicy
from oaos2.experiments.runner import _role_file_policy
from oaos2.kernel.run_dir import RunDir
from oaos2.organizations.spec import Role
from oaos2.trace.invariants import load_all_events
from oaos2.trace.spine import RunSpine


# --- per-role file ACL (derived from the tool grant) ----------------------- #

def test_role_file_policy_read_only_vs_builder() -> None:
    reader = Role(role_id="reader", attention="sample/spec", plays=["reader"], specialized=True,
                  tools=["read_file", "submit_results"])
    builder = Role(role_id="builder", attention="implementation", plays=["builder"], specialized=True,
                   tools=["run_python", "read_file", "write_file", "submit_results"])
    rp, bp = _role_file_policy(reader), _role_file_policy(builder)
    assert rp.may_read("visible") and rp.may_read("scratch_reader")       # reader can read
    assert not rp.may_write("scratch_reader") and not rp.may_execute("scratch_reader")  # but not write/execute
    assert bp.may_write("scratch_builder") and bp.may_execute("scratch_builder")        # builder can
    # A role with no declared tools (single_agent/ensemble) defaults to full scratch rights.
    solo = Role(role_id="solo", attention="all", plays=["replicator"], specialized=False, tools=None)
    sp = _role_file_policy(solo)
    assert sp.may_write("scratch_solo") and sp.may_execute("scratch_solo")


# --- hard tool gate at dispatch (not just offer-layer) --------------------- #

async def test_dispatch_denies_tool_not_permitted_for_role(tmp_path) -> None:
    rd = RunDir.create(tmp_path, "e", "p", "r")
    spine = RunSpine(rd.root, run_id="r")
    await spine.start()
    ctx = ToolContext(agent_id="reader", rs=SimpleNamespace(spine=spine), backend=None, handle=None,
                      run_dir=rd, coordinator=None, submit_commitment_id="spec_v1",
                      allowed_tools={"read_file", "submit_results"})
    seed = await spine.emit_event("turn.started", agent_id="reader", turn_id="t1")
    res = await dispatch_tool("run_python", {"code": "print(1)"}, ctx, turn_id="t1", caused_by=seed)
    await spine.finalize("completed")
    assert "not permitted" in res.text and not res.submitted
    events = load_all_events(rd.root)
    assert any(e["event_class"] == "tool.denied"
               and e["payload"].get("reason") == "tool_not_permitted_for_role" for e in events)


async def test_dispatch_allows_permitted_tool(tmp_path) -> None:
    # read_file is permitted for the reader; a missing file returns an error result but is
    # NOT a permission denial (the gate let it through).
    rd = RunDir.create(tmp_path, "e", "p", "r2")
    spine = RunSpine(rd.root, run_id="r2"); await spine.start()
    ctx = ToolContext(agent_id="reader", rs=SimpleNamespace(spine=spine), backend=None, handle=None,
                      run_dir=rd, coordinator=None, submit_commitment_id="spec_v1",
                      allowed_tools={"read_file", "submit_results"})
    seed = await spine.emit_event("turn.started", agent_id="reader", turn_id="t1")
    res = await dispatch_tool("read_file", {"path": "nope.csv"}, ctx, turn_id="t1", caused_by=seed)
    await spine.finalize("completed")
    assert "not permitted" not in res.text  # got past the gate


# --- cost-parity regimes (M7 §4) ------------------------------------------- #

def test_parity_resolve_regimes() -> None:
    assert ParityPolicy(regime="budget_matched").resolve_regimes(3.0) == [("budget_matched", 3.0)]
    assert ParityPolicy(regime="unconstrained").resolve_regimes(3.0) == [("unconstrained", 9.0)]
    both = ParityPolicy(regime="both").resolve_regimes(3.0)
    assert [r[0] for r in both] == ["budget_matched", "unconstrained"] and both[1][1] == 9.0


# --- exposure_confounded surfaced from the archive (M3 §2.1) --------------- #

async def test_exposure_confounded_read_from_archive(tmp_path) -> None:
    from oaos2.experiments.runner import _exposure_confounded_from_archive
    # No archive / clean run → not confounded.
    rd = RunDir.create(tmp_path, "e", "p", "rx")
    spine = RunSpine(rd.root, run_id="rx"); await spine.start()
    seed = await spine.emit_event("turn.started", agent_id="a", turn_id="t")
    await spine.emit_event("model.responded", agent_id="a", caused_by=seed,
                           payload={"realized_exposure": {"exposure_confounded": False}})
    await spine.finalize("completed")
    assert _exposure_confounded_from_archive(rd.root) is False

    # A single degraded call flips the whole cell to confounded.
    rd2 = RunDir.create(tmp_path, "e", "p", "ry")
    spine2 = RunSpine(rd2.root, run_id="ry"); await spine2.start()
    seed2 = await spine2.emit_event("turn.started", agent_id="a", turn_id="t")
    await spine2.emit_event("model.responded", agent_id="a", caused_by=seed2,
                            payload={"realized_exposure": {"exposure_confounded": True}})
    await spine2.finalize("completed")
    assert _exposure_confounded_from_archive(rd2.root) is True


async def test_sweep_reports_parity_facts(tmp_path) -> None:
    from oaos2.experiments.designs.first_experiment import first_experiment_design
    from oaos2.experiments.runner import run_sweep
    sweep = await run_sweep(first_experiment_design(), tmp_path, execution="offline", replications=1)
    assert sweep.parity_facts and sweep.parity_facts["basis"] == "usd"
    bm = sweep.parity_facts["by_regime"]["budget_matched"]["by_preset"]
    assert set(bm) >= {"single_agent", "pipeline"} and all("mean_realized_usd" in v for v in bm.values())
