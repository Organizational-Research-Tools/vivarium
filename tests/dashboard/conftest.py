"""Shared builder: real spine-written runs in tmp_path (same shape as the
run-registry tests — the dashboard is a projection, so tests feed it real traces)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from oaos2.kernel.run_dir import RunDir
from oaos2.trace.spine import RunSpine


async def _make(runs_root: Path, run_id: str, *, experiment="exp", org="pipeline",
                pack="pack", terminal="completed", deadlock=False, outcome=True,
                status=None, manifest_extra=None, extra_events=()) -> Path:
    rd = RunDir.create(runs_root, experiment, pack, run_id)
    rd.manifest_path.write_text(json.dumps({
        "run_id": run_id, "experiment_id": experiment, "organization_id": org,
        "mode": "pilot", "task_pack_id": pack, "pricing_table_version": "2026-06-01",
        "schema_version": "2026-06-01.v1", **(manifest_extra or {}),
    }))
    spine = RunSpine(rd.root, run_id=run_id)
    await spine.start()
    c = await spine.emit_event("run.started", payload={"run_id": run_id})
    c = await spine.emit_event("turn.completed", agent_id="A", turn_id="A.t1", caused_by=c,
                               payload={"result": "finish_turn"})
    for cls, kw in extra_events:
        await spine.emit_event(cls, caused_by=c, **kw)
    if deadlock:
        await spine.emit_event("run.deadlock_timeout", caused_by=c, payload={"timeout_s": 1})
    if outcome:
        await spine.emit_event("outcome.closed", caused_by=c, payload={"outcome_id": "main"})
    await spine.finalize("completed" if terminal != "failed" else "causality_violation")
    if terminal == "incomplete":
        # A killed run: events flushed, no terminal record — strip it (as the registry tests do).
        for name in ("events.jsonl", "infra.jsonl"):
            f = rd.root / "trace" / name
            if f.exists():
                kept = [ln for ln in f.read_text().splitlines()
                        if '"run.completed"' not in ln and '"run.failed"' not in ln]
                f.write_text("\n".join(kept) + ("\n" if kept else ""))
    if status is not None:
        (rd.root / "run_status.json").write_text(json.dumps(status))
    return rd.root


PASSED_STATUS = {"passed": True, "partial_score": 1.0, "archive_valid": True, "cost_usd": 2.1,
                 "preset_id": "pipeline", "model_ref": "anthropic/claude-haiku-4-5",
                 "difficulty": "high_ambiguity", "label": "unassisted",
                 "parity_regime": "budget_matched", "exposure_confounded": False,
                 "closed": True, "context_budget": None}


@pytest.fixture
def build_run(tmp_path):
    """Sync wrapper over the async builder; ``build_run.runs_root`` is the scanned root."""
    def _build(run_id: str, **kw) -> Path:
        return asyncio.run(_make(tmp_path / "runs", run_id, **kw))
    _build.runs_root = tmp_path / "runs"
    return _build


PROSE = "I propose we fund the housing flagship."


async def _make_rich(runs_root: Path, run_id: str) -> dict:
    """A run exercising the D1 explorer surface: model call with a real raw/ payload,
    reasoning, tools, comms, a conversation, trouble events, cost, commit."""
    import gzip
    import hashlib

    rd = RunDir.create(runs_root, "exp", "pack", run_id)
    rd.manifest_path.write_text(json.dumps({
        "run_id": run_id, "experiment_id": "exp", "organization_id": "pipeline",
        "mode": "pilot", "task_pack_id": "pack",
    }))
    raw_body = json.dumps({"content": [{"type": "text", "text": PROSE}]}).encode()
    digest = hashlib.sha256(raw_body).hexdigest()
    raw_dir = rd.root / "raw"
    raw_dir.mkdir(exist_ok=True)
    with gzip.open(raw_dir / f"{digest}.json.gz", "wb") as f:
        f.write(raw_body)

    spine = RunSpine(rd.root, run_id=run_id)
    await spine.start()
    ids: dict[str, str] = {}

    async def emit(name, cls, **kw):
        eid = await spine.emit_event(cls, **kw)  # emit returns the minted event_id
        ids[name] = eid
        return eid

    c0 = await emit("run_started", "run.started", payload={"run_id": run_id})
    await emit("turn_started", "turn.started", agent_id="A", turn_id="A.t1", caused_by=c0,
               payload={})
    m1 = await emit("model_invoked", "model.invoked", agent_id="A", turn_id="A.t1",
                    caused_by=c0, payload={"model_ref": "anthropic/claude-haiku-4-5"})
    m2 = await emit("model_responded", "model.responded", agent_id="A", turn_id="A.t1",
                    caused_by=m1, payload={"usage": {"input": 100, "output": 20},
                                           "stop_reason": "end_turn",
                                           "raw_provider_response_ref": f"sha256/{digest}"})
    await emit("reasoning", "reasoning.step", agent_id="A", turn_id="A.t1", caused_by=m2,
               payload={"thinking": "the floors bind on health",
                        "narration": "I'll check the register first."})
    t1 = await emit("tool_called", "tool.called", agent_id="A", turn_id="A.t1", caused_by=m2,
                    payload={"tool_name": "read_file"})
    await emit("tool_result", "tool.result", agent_id="A", turn_id="A.t1", caused_by=t1,
               payload={"tool_name": "read_file",
                        "output": "program_register.csv: 42 rows"})
    await emit("turn_completed", "turn.completed", agent_id="A", turn_id="A.t1", caused_by=t1,
               payload={"result": "finish_turn"})
    msg = await emit("message", "message.sent", agent_id="A", caused_by=t1,
                     payload={"to": "B", "kind": "message", "payload_text": "please review the draft"})
    h = await emit("handoff", "handoff", agent_id="A", caused_by=msg,
                   payload={"from_agent": "A", "to_agent": "B", "kind": "handoff",
                            "payload_text": "the spec, not the numbers"})
    co = await emit("conv_opened", "conversation.opened", caused_by=c0,
                    payload={"conversation_id": "conv1", "participants": ["A", "B"]})
    cv = await emit("volley", "conversation.volley", agent_id="B", caused_by=co,
                    payload={"conversation_id": "conv1", "speaker": "B", "round_index": 0,
                             "text": "I think housing is the frame"})
    await emit("conv_closed", "conversation.closed", caused_by=cv,
               payload={"conversation_id": "conv1", "reason": "mutual_done"})
    await emit("violation", "protocol.violation", agent_id="B", caused_by=h,
               payload={"reason": "comm_kind_not_permitted"})
    await emit("intervention", "intervention.recorded", caused_by=h,
               payload={"kind": "pause_timeout", "class": "recorded"})
    await emit("cost", "cost.recorded", agent_id="A", caused_by=m2, payload={"cost_usd": 0.0123})
    submitted = rd.root / "container_mount" / "submitted"
    submitted.mkdir(parents=True, exist_ok=True)
    (submitted / "final.json").write_text(json.dumps({"allocation": {"home52": 52}}))
    sc = await emit("commit", "state.committed", agent_id="A", caused_by=h,
                    payload={"state_commitment": {"commitment_id": "final",
                                                  "payload_ref": "submitted/final.json"},
                             "content_hash": "sha256:deadbeef"})
    await emit("outcome", "outcome.closed", caused_by=sc, payload={"outcome_id": "main"})
    await spine.finalize("completed")
    (rd.root / "run_status.json").write_text(json.dumps(PASSED_STATUS))
    return {"run_dir": rd.root, "ids": ids, "digest": digest}


@pytest.fixture
def rich_run(tmp_path):
    """One rich run; returns {run_dir, ids: name→event_id, digest} + ``.runs_root``."""
    out = asyncio.run(_make_rich(tmp_path / "runs", "r_rich"))
    out["runs_root"] = tmp_path / "runs"
    out["run_ref"] = "exp/pack/r_rich"
    return out


# --- a clocked lateral run: the shape the confirmatory archive actually has ---- #
#
# Four roles under a 6-day clock, notices arriving in waves with a researcher-side
# classification the agents never see, exception filings and dispositions under
# the ``exception_report_<case>_<office>`` / ``disposition_<case>`` grammar,
# broadcast handoffs (one filing → every peer + the integrator), a commit race,
# a compaction, a lapsed fuse, prompt envelopes, a run-local schedule, captured
# submissions, and a pack ("clockpack") whose derived report is a REGISTERED stub
# renderer — so the seam, the registry, the report store, and every clocked view
# are exercised without the real budget_execution assets.

CLOCK_PACK = "clockpack"
CLOCK_ROLES = ("officer_a", "officer_b", "officer_c")
CLOCK_INTEGRATOR = "fund_integrator"


def _clockpack_render(run_dir: Path, events: list[dict]) -> dict:
    """Deterministic stub report in the budget report's shape (summary/clock/delivery)."""
    day, disposed, lapses, per_agent = 0, {}, [], {}
    for e in events:
        cls, p = e.get("event_class"), e.get("payload") or {}
        if cls == "clock.round":
            day = int(p.get("round_no", day))
        elif cls == "state.committed":
            cid = (p.get("state_commitment") or {}).get("commitment_id") or ""
            if cid.startswith("disposition_"):
                case = "C-S" + cid.split("_cs", 1)[1].upper()
                disposed[case] = day
                a = e.get("agent_id")
                per_agent.setdefault(a, []).append(day)
        elif cls == "capacity.deadline_lapse":
            lapses.append(p.get("case_id"))
    schedule = json.loads((run_dir / "config" / "environment_schedule.json").read_text())
    delivery, seen = [], set()
    for wave in schedule["waves"]:
        for pk in wave["packets"]:
            cl = pk["classification"]
            case = pk["payload"]["case_id"]
            if cl["shell"]["shell_id"] in seen:
                continue  # one delivery row per shell, however many offices were notified
            seen.add(cl["shell"]["shell_id"])
            if cl["rule_coverage"] == "exception":
                outcome = "exception_repaired" if case in disposed else "exception_unresolved"
            else:
                outcome = "rule_applied"
            delivery.append({"case_id": case, "shell_id": cl["shell"]["shell_id"],
                             "wave_id": wave["wave_id"], "type": cl["shell"]["type"],
                             "coverage": cl["rule_coverage"], "magnitude": cl["shell"]["magnitude"],
                             "outcome": outcome, "choice_verdict": None, "choice_source": None,
                             "lost_benefit": 0.0 if outcome != "exception_unresolved"
                             else cl["shell"]["magnitude"]})
    lost = sum(d["lost_benefit"] for d in delivery)
    megabatch = {a: {"n_dispositions": len(ds), "n_rounds": len(set(ds)),
                     "max_per_round": max(ds.count(x) for x in set(ds))}
                 for a, ds in sorted(per_agent.items())}
    outcomes: dict[str, int] = {}
    for d in delivery:
        outcomes[d["outcome"]] = outcomes.get(d["outcome"], 0) + 1
    channel = {"cases": [{"case_id": "C-S1", "decider": "officer_a", "verdict": "correct", "n_facts": 2,
                          "n_present_in_filing": 1, "n_available_to_decider": 2, "n_present_in_disposition": 1,
                          "facts": [{"fact_id": "F-annex", "holder": "officer_a", "packet_id": "w1_s1_a",
                                     "present_in_filing": True, "negated_in_filing": False,
                                     "present_in_report": True, "native_to_decider": True,
                                     "available_to_decider": True, "present_in_disposition": True,
                                     "negated_in_disposition": False},
                                    {"fact_id": "F-afternoon", "holder": "officer_b", "packet_id": "w1_s1_b",
                                     "present_in_filing": False, "negated_in_filing": False,
                                     "present_in_report": False, "native_to_decider": False,
                                     "available_to_decider": True, "present_in_disposition": False,
                                     "negated_in_disposition": False}]}]}
    return {"organization_id": "clock_lateral", "tier": "unprogrammable", "channel": channel,
            "delivery_rule": "stub", "delivery": delivery, "choices": [], "plans": [],
            "summary": {"baseline_benefit": 10.0, "lost_benefit": lost,
                        "retained_benefit": 10.0 - lost, "retained_fraction": (10.0 - lost) / 10.0,
                        "delivery_outcomes": dict(sorted(outcomes.items())),
                        "n_choice_wrong": 0, "n_choice_undetermined": 0, "max_pending": 2,
                        "all_plans_valid": True, "n_lateral_handoffs": 0, "n_referral_handoffs": 0,
                        "clock": {"final_round": day, "n_fuse_lapses": len(lapses),
                                  "n_late_repairs": 0, "disposition_rounds": disposed,
                                  "n_agent_failures": 0, "wind_down": None,
                                  "megabatch": megabatch}}}


def _clockpack_summary(report: dict) -> dict:
    s = report.get("summary") or {}
    o = s.get("delivery_outcomes") or {}
    clock = s.get("clock") or {}
    batches = [v["max_per_round"] for v in (clock.get("megabatch") or {}).values()]
    return {"retained_fraction": s.get("retained_fraction"),
            "n_repaired": o.get("exception_repaired"), "n_unresolved": o.get("exception_unresolved"),
            "clock": clock, "max_batch_per_round": max(batches) if batches else None,
            "wind_down": bool(clock.get("wind_down"))}


def _clockpack_commitment_item(cid: str):
    import re
    m = re.match(r"^(exception_report|disposition)_cs(\d+)(?:_([a-z]))?$", cid or "")
    if not m:
        return None
    return (f"C-S{m.group(2)}", "filing" if m.group(1) == "exception_report" else "disposition",
            f"officer_{m.group(3)}" if m.group(3) else None)


def _clockpack_score_rows(report: dict) -> dict:
    rows = {d["case_id"]: {**d, "verdict": "correct" if d["outcome"] == "exception_repaired" else None,
                           "verdict_source": "structured" if d["outcome"] == "exception_repaired" else None}
            for d in report.get("delivery") or []}
    for cc in (report.get("channel") or {}).get("cases") or []:  # as the budget adapter does
        rows.setdefault(cc["case_id"], {})["channel"] = cc
    return rows


def _clockpack_key_for(run_dir, manifest, item_id):
    if item_id == "C-S1":
        return {"key": {"correct": "annex for screening, morning block for sessions",
                        "incorrect": "sessions keep the gym, screening waits"}, "pinned": True,
                "sha256": "sha256:stubkey"}
    return None


def register_clockpack_renderer() -> None:
    from oaos2.archive.items import ItemAdapter, register_item_adapter
    from oaos2.archive.renderers import DerivedRenderer, register_derived_renderer
    try:
        from oaos2.tasks.plugins.budget_execution.derived import run_outcome
        register_derived_renderer(DerivedRenderer(
            pack_id=CLOCK_PACK, filename="clockpack_trace.json",
            render=_clockpack_render, summary=_clockpack_summary, identity="sha256:stub0001",
            outcome=run_outcome))  # the budget pack's outcome: retained fraction
    except ValueError:
        pass  # already registered in this process
    try:
        register_item_adapter(ItemAdapter(pack_id=CLOCK_PACK, score_rows=_clockpack_score_rows,
                                          key_for=_clockpack_key_for,
                                          commitment_item=_clockpack_commitment_item))
    except ValueError:
        pass


CLOCK_SCHEDULE = {
    "schema_version": 1,
    "waves": [
        {"wave_id": "wave_1", "trigger_commitment_id": "initial_plan", "packets": [
            {"packet_id": "w1_s1_a", "target_scopes": ["officer_a"],
             "classification": {"rule_coverage": "exception", "rule_ref": None,
                                "refs": ["W1-SITE-A"], "arrival_round": 2,
                                "response_deadline_round": 4,
                                "shell": {"shell_id": "S1", "type": "site_closure", "magnitude": 2.0},
                                "expected_scopes": ["officer_a", "officer_b"]},
             "payload": {"case_id": "C-S1", "notice_id": "W1-SITE-A", "type": "site_closure",
                         "text": "The gymnasium closes this quarter; two units of screening need a home."}},
            {"packet_id": "w1_s1_b", "target_scopes": ["officer_b"],
             "classification": {"rule_coverage": "exception", "rule_ref": None,
                                "refs": ["W1-SITE-B"], "arrival_round": 2,
                                "response_deadline_round": 4,
                                "shell": {"shell_id": "S1", "type": "site_closure", "magnitude": 2.0},
                                "expected_scopes": ["officer_a", "officer_b"]},
             "payload": {"case_id": "C-S1", "notice_id": "W1-SITE-B", "type": "site_closure",
                         "text": "The gymnasium closes; the afternoon sessions must move."}},
            {"packet_id": "w1_s2_c", "target_scopes": ["officer_c"],
             "classification": {"rule_coverage": "rule_covered", "rule_ref": "R1_minor_cost_increase",
                                "refs": ["W1-COST-C"], "arrival_round": 3,
                                "shell": {"shell_id": "S2", "type": "cost_increase", "magnitude": 1.0}},
             "payload": {"case_id": "C-S2", "notice_id": "W1-COST-C", "type": "cost_increase",
                         "text": "Rates rise by one unit effective immediately."}},
            {"packet_id": "w1_s3_c", "target_scopes": ["officer_c"],
             "classification": {"rule_coverage": "exception", "rule_ref": None,
                                "refs": ["W1-DLY-C"], "arrival_round": 2,
                                "response_deadline_round": 4,
                                "shell": {"shell_id": "S3", "type": "delay", "magnitude": 1.5},
                                "expected_scopes": ["officer_c"]},
             "payload": {"case_id": "C-S3", "notice_id": "W1-DLY-C", "type": "delay",
                         "text": "The water mains slip a quarter; the repair grants wait on them."}},
        ]},
    ],
}


async def _make_clocked(runs_root: Path, run_id: str) -> dict:
    register_clockpack_renderer()
    rd = RunDir.create(runs_root, "clock_exp", CLOCK_PACK, run_id)
    ext = {
        "difficulty": "unprogrammable", "model_ref": "stub/model", "n_agents": 4,
        "contract_profile": "lateral_clocked", "environment_schedule_variant": "r6w2",
        "clock_spec": {"rounds_total": 6, "calls_per_day": 2, "megabatch": True,
                       "schedule_variant": "r6w2",
                       "plan_deadline_rounds": {"initial_plan": 1, "final_plan": 6}},
        "clock": {"rounds_total": 6, "calls_per_day": 2, "megabatch": True,
                  "schedule_variant": "r6w2",
                  "plan_deadline_rounds": {"initial_plan": 1, "final_plan": 6},
                  "case_rounds": {"C-S1": {"arrival": 2, "deadline": 4},
                                  "C-S2": {"arrival": 3, "deadline": None},
                                  "C-S3": {"arrival": 2, "deadline": 4}}},
        "source_commit": "abc123", "source_dirty": False, "apparatus_sha256": "sha256:apparatus",
        "hidden_reference_sha256s": {"environment_unprogrammable_r6w2": "sha256:stub"},
        "cap_usd": 2.0, "role_prompt_sha256s": {r: "sha256:rp" for r in CLOCK_ROLES},
    }
    rd.manifest_path.write_text(json.dumps({
        "run_id": run_id, "experiment_id": "clock_exp", "organization_id": "clock_lateral",
        "mode": "pilot", "task_pack_id": CLOCK_PACK, "pricing_table_version": "2026-06-01",
        "schema_version": "2026-06-01.v1", "extensions": ext,
    }))
    cfg = rd.root / "config"
    cfg.mkdir(exist_ok=True)
    (cfg / "environment_schedule.json").write_text(json.dumps(CLOCK_SCHEDULE, indent=1))
    (cfg / "resolved.json").write_text(json.dumps({
        "organization": {"id": "clock_lateral", "roles": list(CLOCK_ROLES) + [CLOCK_INTEGRATOR],
                         "topology": {"channels": [[a, b] for a in CLOCK_ROLES for b in CLOCK_ROLES if a < b]
                                      + [[r, CLOCK_INTEGRATOR] for r in CLOCK_ROLES]},
                         "contribution_visibility": "shared_sequential"},
        "roles": [{"role_id": r, "max_calls_per_slot": 8} for r in CLOCK_ROLES + (CLOCK_INTEGRATOR,)],
        "outcome_contract": {"commitments": ["initial_plan", "final_plan"]},
    }))
    for role in CLOCK_ROLES + (CLOCK_INTEGRATOR,):
        (cfg / f"prompt_envelope_{role}.json").write_text(json.dumps({
            "agent_id": role, "role_packet": "officer_cumulative" if role != CLOCK_INTEGRATOR else "integrator_cumulative",
            "commitment": f"office_plan_{role[-1]}" if role != CLOCK_INTEGRATOR else "initial_plan",
            "tier": "unprogrammable",
            "system_prompt": f"You are {role} for the city of Delfield. You may write to any office.",
            "initial_user_text": "# Task materials\nThe Delivery Fund holds 10 units.",
        }))
    submitted = rd.root / "captured" / "submitted"
    submitted.mkdir(parents=True)
    for role in CLOCK_ROLES:
        (submitted / f"office_plan_{role[-1]}.json").write_text(json.dumps(
            {"office": role[-1], "awards": {f"prog_{role[-1]}": 3}}))
    (submitted / "initial_plan.json").write_text(json.dumps({"allocation": {"prog_a": 3, "prog_b": 3, "prog_c": 3}}))
    (submitted / "exception_report_cs1_a.json").write_text(json.dumps({"office": "a", "exception_records": [
        {"exception_id": "C-S1", "trigger_refs": ["W1-SITE-A"], "affected_scopes": ["a", "b"],
         "summary": "Screening stations displaced; the annex is the only nurses-only room."}]}))
    (submitted / "exception_report_cs1_b.json").write_text(json.dumps({"office": "b", "exception_records": [
        {"exception_id": "C-S1", "trigger_refs": ["W1-SITE-B"], "affected_scopes": ["a", "b"],
         "summary": "Afternoon sessions displaced; the morning block is the alternative (per exception_report_cs1_a)."}]}))
    (submitted / "disposition_cs1.json").write_text(json.dumps({
        "case_id": "C-S1", "disposition": "repaired", "repair_ref": "disposition_cs1",
        "selected_option": "annex for screening, morning block for sessions",
        "detail": "Screening moves to the annex; youth sessions take the morning block."}))
    (submitted / "final_plan.json").write_text(json.dumps({"allocation": {"prog_a": 3, "prog_b": 3, "prog_c": 3}}))
    corr = rd.root / "captured" / "agents" / "officer_a" / "correspondence"
    corr.mkdir(parents=True)
    (corr / "day02_w1_s1_a.json").write_text(json.dumps(CLOCK_SCHEDULE["waves"][0]["packets"][0]["payload"]))

    spine = RunSpine(rd.root, run_id=run_id)
    await spine.start()
    ids: dict[str, str] = {}

    async def emit(name, cls, **kw):
        eid = await spine.emit_event(cls, **kw)
        ids[name] = eid
        return eid

    def _sc(cid, agent):
        return {"state_commitment": {"commitment_id": cid, "agent_id": agent,
                                     "kind": "artifact_submission",
                                     "payload_ref": f"submitted/{cid}.json",
                                     "content_hash": "sha256:" + cid},
                "content_hash": "sha256:" + cid}

    async def broadcast(name, sender, cid, cause):
        text = (submitted / f"{cid}.json").read_text()
        for to in CLOCK_ROLES + (CLOCK_INTEGRATOR,):
            if to == sender:
                continue
            await emit(f"{name}_{to}", "handoff", agent_id=sender, caused_by=cause, payload={
                "from_agent": sender, "to_agent": to, "kind": "handoff",
                "handoff_id": f"h_{cid}_{to}", "payload_text": text,
                "handoff_delta": {"handoff_delta_id": f"hd_{cid}_{to}", "handoff_id": f"h_{cid}_{to}",
                                  "narration_ref": None, "formalized_payload_ref": f"submitted/{cid}.json"}})

    async def turn(name, agent, day, observations, cid=None, *, thinking="", calls=1):
        t = f"{agent}.t{day}"
        s0 = await emit(f"{name}_start", "turn.started", agent_id=agent, turn_id=t, caused_by=ids["run_started"], payload={})
        ob = await emit(f"{name}_obs", "agent.observed", agent_id=agent, turn_id=t, caused_by=s0, payload={
            "agent_view": {"agent_id": agent, "turn_id": t, "observation_ids": []},
            "observation_records": [], "observations": observations})
        last = ob
        for k in range(calls):
            mi = await emit(f"{name}_mi{k}", "model.invoked", agent_id=agent, turn_id=t, caused_by=last,
                            payload={"model_ref": "stub/model", "activity_class": "work_modeling"})
            last = await emit(f"{name}_rs{k}", "reasoning.step", agent_id=agent, turn_id=t, caused_by=mi,
                              payload={"narration": f"{agent} weighs the notices.", "thinking": thinking or f"day {day}: {agent} thinks about the annex."})
            await emit(f"{name}_cost{k}", "cost.recorded", agent_id=agent, caused_by=mi,
                       payload={"cost_usd": 0.01, "activity_class": "work_modeling",
                                "token_split": {"input": 100, "cache_read": 400, "cache_write": 0, "output": 50}})
        if cid:
            tc = await emit(f"{name}_tool", "tool.called", agent_id=agent, turn_id=t, caused_by=last, payload={"tool_name": "submit_results"})
            sc = await emit(f"{name}_commit", "state.committed", agent_id=agent, caused_by=tc, payload=_sc(cid, agent))
            await emit(f"{name}_stage", "coordination.stage_advanced", caused_by=sc,
                       payload={"agent_id": agent, "from": cid, "to": "next", "phase": "environment_stage"})
            await emit(f"{name}_tr", "tool.result", agent_id=agent, turn_id=t, caused_by=tc,
                       payload={"tool_name": "submit_results", "submitted": True, "output": f"Submitted `{cid}`."})
            await broadcast(f"{name}_h", agent, cid, sc)
            last = sc
        await emit(f"{name}_end", "turn.completed", agent_id=agent, turn_id=t, caused_by=last, payload={"result": "finish_turn"})

    def notice(day, duty):
        return {"item_id": f"n{day}", "kind": "clock_notice", "source_event_id": None,
                "payload": f"[Fund clock] Day {day} of 6. Your current duty '{duty}' is due by day 4."}

    def env_obs(packet):
        return {"item_id": packet["packet_id"], "kind": "environment_event", "source_event_id": None,
                "payload": packet["payload"]}

    c0 = await emit("run_started", "run.started", payload={"run_id": run_id})
    for role in CLOCK_ROLES + (CLOCK_INTEGRATOR,):
        await emit(f"launch_{role}", "agent.launched", agent_id=role, caused_by=c0, payload={})
    # day 1: office plans + initial plan
    await emit("day1", "clock.round", caused_by=c0, payload={"round_no": 1, "rounds_total": 6})
    for role in CLOCK_ROLES:
        await turn(f"d1_{role}", role, 1, [notice(1, f"office_plan_{role[-1]}")], f"office_plan_{role[-1]}")
    await turn("d1_int", CLOCK_INTEGRATOR, 1, [notice(1, "initial_plan")], "initial_plan")
    # day 2: wave-1 arrivals for C-S1 (a, b) and C-S3 (c); a files; integrator races a slot
    await emit("day2", "clock.round", caused_by=c0, payload={"round_no": 2, "rounds_total": 6})
    packets = CLOCK_SCHEDULE["waves"][0]["packets"]
    for name, pk in (("env_s1_a", packets[0]), ("env_s1_b", packets[1]), ("env_s3_c", packets[3])):
        await emit(name, "environment.event", agent_id=pk["target_scopes"][0], caused_by=ids["d1_int_commit"], payload={
            "environment_event": {"environment_event_id": name, "driver_ref": "deterministic_schedule.v1",
                                  "schedule_ref": "manifest.environment.schedule", "schedule_hash": "sha256:sched",
                                  "wave_id": "wave_1", "packet_id": pk["packet_id"],
                                  "trigger_commitment_id": "initial_plan",
                                  "target_role_id": pk["target_scopes"][0], "payload": pk["payload"]}})
    await turn("d2_a", "officer_a", 2, [notice(2, "exception_report_cs1_a"), env_obs(packets[0])],
               "exception_report_cs1_a", thinking="The annex is nurses-only per the register; the sessions can take mornings.", calls=2)
    await emit("race_int", "intervention.recorded", agent_id=CLOCK_INTEGRATOR, turn_id=f"{CLOCK_INTEGRATOR}.t2", caused_by=ids["d2_a_commit"],
               payload={"kind": "submission_nonconformant_retry", "class": "recorded", "attempt": 1, "max_retries": 2,
                        "problems": ["your payload addresses slot 'disposition_cs1', which is already closed"]})
    # day 3: b files (citing a), a disposes; c gets the rule-covered notice; integrator compacts
    await emit("day3", "clock.round", caused_by=c0, payload={"round_no": 3, "rounds_total": 6})
    await emit("env_s2_c", "environment.event", agent_id="officer_c", caused_by=ids["d1_int_commit"], payload={
        "environment_event": {"environment_event_id": "env_s2_c", "driver_ref": "deterministic_schedule.v1",
                              "schedule_ref": "manifest.environment.schedule", "schedule_hash": "sha256:sched",
                              "wave_id": "wave_1", "packet_id": packets[2]["packet_id"],
                              "trigger_commitment_id": "initial_plan", "target_role_id": "officer_c",
                              "payload": packets[2]["payload"]}})
    await turn("d3_b", "officer_b", 3, [notice(3, "exception_report_cs1_b"), env_obs(packets[1]),
                                        {"item_id": "h1", "kind": "handoff", "source_event_id": ids["d2_a_h_officer_b"],
                                         "payload": (submitted / "exception_report_cs1_a.json").read_text()}],
               "exception_report_cs1_b")
    await emit("compaction", "context.compaction", agent_id=CLOCK_INTEGRATOR, turn_id=f"{CLOCK_INTEGRATOR}.t3", caused_by=ids["d3_b_commit"],
               payload={"budget_tokens": 60000, "messages_summarized": 6, "policy": "summarize",
                        "summary_chars": 900, "tokens_after": 20000, "tokens_before": 61000})
    await turn("d3_a", "officer_a", 3, [notice(3, "disposition_cs1")], "disposition_cs1",
               thinking="Both filings agree: annex for screening, mornings for sessions.")
    # day 4: C-S3's fuse lapses (c never filed)
    await emit("day4", "clock.round", caused_by=c0, payload={"round_no": 4, "rounds_total": 6})
    await emit("lapse", "capacity.deadline_lapse", caused_by=ids["day4"],
               payload={"case_id": "C-S3", "commitment_id": "disposition_cs3", "deadline_round": 4,
                        "round_no": 4, "forced": False})
    await turn("d4_c", "officer_c", 4, [notice(4, "exception_report_cs3_c"), env_obs(packets[3]), env_obs(packets[2])], None)
    await emit("day5", "clock.round", caused_by=c0, payload={"round_no": 5, "rounds_total": 6})
    await emit("day6", "clock.round", caused_by=c0, payload={"round_no": 6, "rounds_total": 6})
    await turn("d6_int", CLOCK_INTEGRATOR, 6, [notice(6, "final_plan")], "final_plan")
    ev = await emit("eval", "evaluation.completed", caused_by=ids["d6_int_commit"],
                    payload={"agent_feedback": {"completed": True}, "commitment_id": "final_plan",
                             "evaluator_ref": "clockpack.score"})
    await emit("outcome", "outcome.closed", caused_by=ev, payload={"outcome_id": "clock_outcome"})
    await spine.finalize("completed")
    (rd.root / "run_status.json").write_text(json.dumps({
        **PASSED_STATUS, "partial_score": 0.9, "preset_id": "clock_lateral", "model_ref": "stub/model",
        "difficulty": "unprogrammable", "clock_label": "r6w2", "rounds_total": 6, "scored": True,
        "cost_usd": 0.12}))
    return {"run_dir": rd.root, "ids": ids, "runs_root": runs_root,
            "run_ref": f"clock_exp/{CLOCK_PACK}/{run_id}"}


@pytest.fixture
def clocked_run(tmp_path):
    """A clocked lateral run under a registered stub pack renderer."""
    return asyncio.run(_make_clocked(tmp_path / "runs", "r_clock_lat"))
