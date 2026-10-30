"""Readiness: every affordance a role is told about must be one it can use (2026-09-25).

The original clocked presets told every role that its correspondence and the filed
submissions were on record under paths no role could read, and the officer packet
described repair and follow-up slots the clocked profiles never issue. These tests pin
the audit that catches both, on synthetic text and on the real presets.
"""

from __future__ import annotations

import json

import pytest

from oaos2.experiments.affordances import audit_affordances, audit_texts
from oaos2.experiments.runner import clock_notice_text, run_org_live
from oaos2.organizations.loader import load_org_spec
from oaos2.tasks.loader import load_task_pack

try:
    from oaos2.docker.backend import FakeContainerBackend
    _HAVE_FAKE = True
except Exception:  # pragma: no cover
    _HAVE_FAKE = False

_TIER = "unprogrammable"
# the sentences the clock notice carried until 2026-09-25
_OLD_NOTICE = ("[Fund clock] Day 1 of 16. Arrived correspondence is kept on file in "
               "/work/agents/fund_integrator/correspondence/. Filed submissions are on record in "
               "/work/submitted/. A response filed after its stated return window is still accepted.")


def _pack_for(preset: str):
    org = load_org_spec(preset)
    profile = (org.live_coordination or {}).get("contract_profile", {}).get(_TIER)
    return org, load_task_pack("budget_execution", profile=profile)


def test_audit_texts_flags_paths_tools_and_slots_the_role_cannot_use() -> None:
    texts = {"notice": _OLD_NOTICE,
             "system_prompt": "Use the read tool on /visible/data/x.csv. Report in the repair slot; "
                              "a follow-up report follows. Then the query stage."}
    findings = audit_texts("r", texts, granted={"submit_results"}, commitment_ids=["disposition_cs6"])
    kinds = {(f.kind, f.promise) for f in findings}
    assert ("path", "/work/submitted/") in kinds
    assert ("path", "/work/agents/fund_integrator/correspondence/") in kinds
    assert ("path", "/visible/data/x.csv") in kinds
    assert ("tool", "read_file") in kinds
    assert ("slot", "repair slot") in kinds and ("slot", "follow-up slot") in kinds
    assert ("slot", "query slot") in kinds


def test_audit_texts_is_silent_when_the_role_can_act() -> None:
    texts = {"system_prompt": "Use read_file on /visible/data/x.csv; file the repair slot."}
    findings = audit_texts("r", texts, granted={"read_file", "submit_results"},
                           commitment_ids=["repair_w1_housing"])
    assert findings == []
    # /work/submitted is readable by no tool, whatever the grant
    findings = audit_texts("r", {"n": "on record in /work/submitted/"}, granted={"read_file", "run_python"},
                           commitment_ids=[])
    assert [f.promise for f in findings] == ["/work/submitted/"]


def test_a_denied_affordance_is_not_a_promise() -> None:
    texts = {"brief": "Each office files once per case; there is no later repair report, follow-up "
                      "or query. Nothing is kept under /work/submitted/ for you."}
    assert audit_texts("r", texts, granted={"submit_results"}, commitment_ids=[]) == []


def test_current_clock_notice_promises_no_path() -> None:
    text = clock_notice_text(round_no=1, rounds_total=16, duty="", checkpoints="none")
    assert audit_texts("r", {"notice": text}, granted={"submit_results"}, commitment_ids=[]) == []
    assert "still accepted" in text


def test_original_vertical_preset_promised_records_and_slots_it_could_not_use() -> None:
    org, pack = _pack_for("budget_execution_vertical_clocked")
    findings = audit_affordances(org, pack, _TIER, notice_texts={"clock": _OLD_NOTICE})
    paths = {f.promise for f in findings if f.kind == "path"}
    assert "/work/submitted/" in paths and "/work/agents/fund_integrator/correspondence/" in paths
    # the frozen stage-1 officer packet still describes repair and follow-up slots that the
    # clocked profile never issues — a known hold on the original presets, not repaired here
    slots = {f.promise for f in findings if f.kind == "slot"}
    assert {"repair slot", "follow-up slot"} <= slots
    # with the current notice, the path promises are gone; the packet's slot promises remain
    now = audit_affordances(org, pack, _TIER, notice_texts={
        "clock": clock_notice_text(round_no=1, rounds_total=16, duty="", checkpoints="none")})
    assert not [f for f in now if f.kind == "path"]
    assert {f.promise for f in now if f.kind == "slot"} == slots


def test_ch2_workload_preset_is_clean() -> None:
    # its packets were rewritten on 2026-09-23/24 to describe the clocked sequence with no
    # repair, follow-up, query or messaging stage
    org, pack = _pack_for("budget_execution_ch2w_summary_unknown_clocked")
    findings = audit_affordances(org, pack, _TIER, notice_texts={
        "clock": clock_notice_text(round_no=1, rounds_total=16, duty="", checkpoints="none")})
    assert findings == [], [(f.role_id, f.kind, f.promise, f.source) for f in findings]


@pytest.mark.skipif(not _HAVE_FAKE, reason="FakeContainerBackend unavailable")
async def test_strict_audit_refuses_to_stage_a_preset_with_dead_affordances(tmp_path) -> None:
    from oaos2.tasks.plugins.budget_execution.offline_stub import ClockedPerfectPlayStub
    with pytest.raises(ValueError, match="affordance audit"):
        await run_org_live(
            load_org_spec("budget_execution_vertical_clocked"), tmp_path, tier=_TIER,
            model_ref="stub/deterministic", experiment_id="exp_affordance_strict",
            task_pack="budget_execution", reasoning_kind="none", cap_usd=1.0, max_model_calls=5,
            backend=FakeContainerBackend(digest="sha256:fake"),
            adapter_factory=lambda: ClockedPerfectPlayStub(tier=_TIER),
            affordance_check="strict",
            clock_override={"rounds_total": 16,
                            "plan_deadline_rounds": {"initial_plan": 4, "revised_plan_w1": 10, "final_plan": 16},
                            "schedule_variant": "r16w3", "calls_per_day": 4, "megabatch": True},
        )
    audits = list(tmp_path.rglob("affordance_audit.json"))
    assert audits, "the findings are recorded even when the run is refused"
    recorded = json.loads(audits[0].read_text())
    assert recorded["mode"] == "strict" and recorded["findings"]
