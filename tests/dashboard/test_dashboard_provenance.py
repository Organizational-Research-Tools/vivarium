"""Provenance classification + diagnostics rules — the 'what is real' layer."""

from __future__ import annotations

from oaos2.dashboard import diagnostics, provenance
from oaos2.dashboard.store import run_detail
from oaos2.dashboard.events import load_events
from tests.dashboard.conftest import PASSED_STATUS


def _current_sha(pack: str) -> str | None:
    return provenance._library_snapshot()["packs"][pack]["reference_sha256"]


def test_current_run(build_run) -> None:
    v = provenance.classify({"task_pack_id": "budget_allocation",
                             "organization_id": "budget_hierarchy",
                             "experiment_id": "budget_calibration_x",
                             "reference_sha256": _current_sha("budget_allocation")})
    assert v["provenance"] == "current" and not v["provenance_reasons"]


def test_stale_materials_run() -> None:
    v = provenance.classify({"task_pack_id": "budget_allocation",
                             "organization_id": "budget_hierarchy",
                             "experiment_id": "budget_calibration_x",
                             "reference_sha256": "sha256:" + "0" * 64})
    assert v["provenance"] == "stale_materials"
    assert "materials changed" in v["provenance_reasons"][0]


def test_superseded_pack_and_org() -> None:
    v = provenance.classify({"task_pack_id": "traffic_optimization",
                             "organization_id": "single_agent",
                             "experiment_id": "traffic_pilot", "reference_sha256": "sha256:x"})
    assert v["provenance"] == "superseded"
    assert "no longer in the library" in v["provenance_reasons"][0]
    v = provenance.classify({"task_pack_id": "budget_allocation",
                             "organization_id": "organic_deliberative",
                             "experiment_id": "x", "reference_sha256": None})
    assert v["provenance"] == "superseded"


def test_unknown_without_pin_and_gate_tag() -> None:
    v = provenance.classify({"task_pack_id": "paper_replication", "organization_id": "pipeline",
                             "experiment_id": "budget_manip_20260704", "reference_sha256": None})
    assert v["provenance"] == "unknown"
    assert v["tags"] == ["gate-check"]


# --- diagnostics rules ------------------------------------------------------- #

def _diag(run_dir):
    return {f["id"]: f for f in diagnostics.diagnose(run_dir, load_events(run_dir),
                                                     run_detail(run_dir))}


def test_diagnose_killed_and_stalled(build_run) -> None:
    rd = build_run("r_killed", terminal="incomplete", outcome=False)
    assert _diag(rd)["killed"]["severity"] == "serious"
    rd = build_run("r_stall", deadlock=True, outcome=False)
    assert "stalled" in _diag(rd)


def test_diagnose_protocol_and_forced_assent(build_run) -> None:
    rd = build_run("r_forced", status=PASSED_STATUS, extra_events=[
        ("protocol.violation", {"agent_id": "B", "payload": {"reason": "comm_kind_not_permitted"}}),
        ("conversation.closed", {"payload": {"conversation_id": "c1", "reason": "round_backstop"}}),
        ("state.committed", {"agent_id": "deliberation", "payload": {
            "state_commitment": {"commitment_id": "objective_interpretation"},
            "interpretation": {"consensus": False, "budget_forced": ["rep_a", "rep_c"]}}}),
    ])
    d = _diag(rd)
    assert "comm_kind_not_permitted×1" in d["protocol"]["detail"]
    assert d["conv_backstop"]["severity"] == "warning"
    assert d["forced_assent"]["severity"] == "serious"
    assert "rep_a" in d["forced_assent"]["detail"] and "rep_c" in d["forced_assent"]["detail"]


def test_diagnose_cost_pressure(build_run) -> None:
    rd = build_run("r_capped", status=PASSED_STATUS,
                   manifest_extra={"extensions": {"cap_usd": 1.0}},
                   extra_events=[
                       ("cost.recorded", {"agent_id": "A", "payload": {"cost_usd": 0.95}}),
                       ("cost.cap_blocked_dispatch", {"agent_id": "A", "payload": {}}),
                   ])
    d = _diag(rd)
    assert d["near_cap"]["severity"] == "warning"
    assert d["cap_blocked"]["severity"] == "serious"


def test_diagnose_constraints_are_info_not_problems(build_run) -> None:
    rd = build_run("r_compact", status=PASSED_STATUS, extra_events=[
        ("context.compaction", {"agent_id": "A", "payload": {"evicted": 3}}),
    ])
    d = _diag(rd)
    assert d["context.compaction"]["severity"] == "info"
    assert "treatment observable" in d["context.compaction"]["detail"]


def test_clean_run_has_no_findings_beyond_info(build_run) -> None:
    rd = build_run("r_clean", status=PASSED_STATUS)
    assert all(f["severity"] == "info" for f in _diag(rd).values())
