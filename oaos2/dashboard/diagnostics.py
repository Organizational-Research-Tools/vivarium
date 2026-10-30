"""Find recorded patterns that may need inspection in a run archive.

Rules read events, saved status, and derived reports, then supply a review
priority and supporting event links where available. Their explanations are
diagnostic hypotheses, not automatic study exclusions or causal findings.
Severity definitions are shared with dashboard/glossary.py.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

_SEVERITY_ORDER = {"critical": 0, "serious": 1, "warning": 2, "info": 3}

# --- the rule registry (DASHBOARD.md §4.10): foundation rules read foundation
# event classes; a pack registers rules that know its own commitment grammar via
# its ``oaos2.tasks.plugins.<pack>.derived`` module — never a branch in here.
Rule = Callable[[Path, list, dict], list]
_FOUNDATION_RULES: list[Rule] = []
_PACK_RULES: dict[str, list[Rule]] = {}


def register_rule(fn: Rule, *, pack_id: str | None = None) -> Rule:
    (_PACK_RULES.setdefault(pack_id, []) if pack_id else _FOUNDATION_RULES).append(fn)
    return fn


def finding(fid, severity, title, text, evs=()) -> dict:
    return {"id": fid, "severity": severity, "title": title, "detail": text,
            "event_ids": _ids(list(evs))}


def _find(events, cls):
    return [e for e in events if e.get("event_class") == cls]


def _ids(evs, cap=20):
    return [e.get("event_id") for e in evs[:cap]]


def diagnose(run_dir: Path, events: list[dict], detail: dict) -> list[dict]:
    """All findings for a run, most severe first. ``detail`` is ``store.run_detail``."""
    f: list[dict] = []
    disp = detail["disposition"]
    status = detail["run_status"] or {}
    manifest_ext = (detail["manifest"] or {}).get("extensions") or {}

    def add(fid, severity, title, text, evs=()):
        f.append({"id": fid, "severity": severity, "title": title, "detail": text,
                  "event_ids": _ids(list(evs))})

    # --- archive trustworthiness -------------------------------------------- #
    if disp["disposition"] == "empty":
        add("empty", "critical", "Empty trace", "No events — nothing to interpret.")
        return f
    if status.get("archive_valid") is False:
        add("archive_invalid", "critical", "Archive invariants FAILED",
            "INV-1…4 did not hold at finalize; treat every derived number as suspect.")
    unknown_usage = [e for e in _find(events, "model.invocation_failed")
                     if (e.get("payload") or {}).get("usage_status") == "unknown"]
    if disp["disposition"] == "failed":
        cancelled = [e for e in unknown_usage if (e.get("payload") or {}).get("error") == "CancelledError"]
        add("run_failed", "critical", "Terminal run.failed",
            f"reason: {disp.get('terminal_reason') or '?'}"
            + ("; a model call was cancelled mid-flight (CancelledError), as an outer timeout or "
               "an interruption would do: check the launcher's record before reading this as the "
               "organization's failure" if cancelled else ""),
            _find(events, "run.failed") + cancelled)
    if unknown_usage:
        add("unknown_usage", "serious", f"Model usage unknown ×{len(unknown_usage)}",
            "These calls ended without a usage report, so the recorded cost is a lower bound: the "
            "provider may have billed them. Do not read the missing usage as zero.", unknown_usage)
    if disp["disposition"] == "incomplete":
        add("killed", "serious", "No terminal record",
            "No terminal event is recorded. The run may be active or interrupted; "
            "inspect execution status before deciding whether recovery is needed.")
    if disp["disposition"] == "stalled":
        add("stalled", "serious", "Supervisor deadlock timeout fired",
            "The run stalled and was force-closed; the outcome (if any) postdates a deadlock.",
            _find(events, "run.deadlock_timeout"))
    for cls, title in (("isolation.violation", "Isolation violation"),
                       ("capture.failed", "Artifact capture failed"),
                       ("docker.oom", "Container OOM"),
                       ("docker.disk_exceeded", "Container disk limit exceeded"),
                       ("docker.capability_gap", "Backend capability gap")):
        evs = _find(events, cls)
        if evs:
            add(cls, "serious" if cls != "isolation.violation" else "critical",
                f"{title} ×{len(evs)}", "", evs)
    if _find(events, "agent.failed"):
        evs = _find(events, "agent.failed")
        add("agent_failed", "serious", f"Agent crashed ×{len(evs)}",
            "; ".join(str((e.get('payload') or {}).get('error', ''))[:80] for e in evs[:3]), evs)
    evs = _find(events, "coordination.report_timeout")
    if evs:
        add("report_timeout", "serious", f"Report deadline passed; the platform filed for the role ×{len(evs)}",
            "The coordination procedure committed an empty report so the run could continue. "
            "What the recipients received from these roles was the platform's, not the agent's.", evs)
    evs = _find(events, "docker.launch_failed")
    if evs:
        add("docker_launch_failed", "serious", f"Container launch failed ×{len(evs)}", "", evs)
    evs = _find(events, "clock.wind_down")
    if evs:
        add("clock_wind_down", "serious", "Clock run was wound down",
            "Wind-down sets the archive's censored flag. Inspect what remained open and "
            "apply the study's rules for exclusion or separate reporting.", evs)

    # --- validity threats ---------------------------------------------------- #
    if status.get("exposure_confounded"):
        add("exposure", "serious", "Exposure confounded",
            "Realized model exposure differed from the declared arm — a cross-cell confound.")
    if manifest_ext.get("source_dirty"):
        digest = manifest_ext.get("source_worktree_sha256")
        suffix = f" Pinned worktree {str(digest)[:20]}…." if digest else ""
        add("source_dirty", "warning", "Run used a dirty source tree",
            "The source commit alone does not reconstruct this apparatus; compare the "
            "pinned worktree/apparatus hashes before pooling it with clean-source runs." + suffix)
    report_summary = ((detail.get("task_report") or {}).get("summary") or {})
    clock_report = report_summary.get("clock") or {}
    batches = [v.get("max_per_round") for v in (clock_report.get("megabatch") or {}).values()
               if isinstance(v, dict) and v.get("max_per_round") is not None]
    if batches and max(batches) <= 1:
        add("floor_regime", "serious", "Mechanical floor regime",
            "No agent completed more than one disposition per round. This run is not "
            "evidence about usable parallel capacity, even if its outcome is otherwise valid.")
    evs = _find(events, "cost.cap_blocked_dispatch")
    if evs:
        add("cap_blocked", "serious", f"Cost cap blocked dispatch ×{len(evs)}",
            "Agents were cut off by the budget mid-run; the outcome is budget-truncated, "
            "not a free completion.", evs)
    cap = manifest_ext.get("cap_usd")
    total = (detail["metrics"] or {}).get("total_cost_usd") or 0.0
    if cap and total >= 0.9 * cap:
        add("near_cap", "warning", f"Spend ${total:.2f} ≥ 90% of the ${cap:.2f} cap",
            "Recorded spending is near the cap. Check blocked-dispatch and warning events "
            "before attributing a choice to budget pressure.")
    forced = _forced_assent(events)
    if forced:
        add("forced_assent", "serious", "Deliberation assent was budget-forced",
            "The platform recorded budget-forced assent for these participants; this "
            "does not establish freely reached substantive agreement: "
            + ", ".join(sorted(forced["agents"])), forced["events"])
    backstops = [e for e in _find(events, "conversation.closed")
                 if _closed_by_backstop(e)]
    if backstops:
        add("conv_backstop", "warning",
            f"Conversation closed by backstop, not consensus ×{len(backstops)}",
            "reason: " + ", ".join(str((e.get('payload') or {}).get('reason')) for e in backstops),
            backstops)
    if (disp["disposition"] == "completed" and disp["outcome_closed"]
            and (detail["run_status"] is None or status.get("scored") is False)):
        add("unscored", "warning", "Outcome closed without a saved scoring verdict",
            "The status file is missing or marks the run unscored. Inspect evaluation "
            "events and the task report to distinguish deliberate deferral from a missing result.")

    # --- protocol & coordination -------------------------------------------- #
    evs = _find(events, "protocol.violation")
    if evs:
        reasons: dict[str, int] = {}
        for e in evs:
            r = str((e.get("payload") or {}).get("reason", "?"))
            reasons[r] = reasons.get(r, 0) + 1
        add("protocol", "warning", f"Protocol violations ×{len(evs)}",
            ", ".join(f"{r}×{n}" for r, n in sorted(reasons.items())), evs)
    for cls, title in (("handoff_extraction_failed", "Handoff extraction failed"),
                       ("handoff_stub_injected", "Handoff stub injected"),
                       ("relay.blocked", "Relay blocked"),
                       ("tool.denied", "Tool calls denied"),
                       ("file.reconciliation_mismatch", "File reconciliation mismatch"),
                       ("evaluation.failed", "Evaluator raised"),
                       ("model.invocation_failed", "Model invocation failed"),
                       ("chat.timed_out", "Chat requests timed out"),
                       ("outcome.commit_refused", "Commitments refused by the commit path")):
        evs = _find(events, cls)
        if evs:
            add(cls, "warning", f"{title} ×{len(evs)}", "", evs)

    # --- by-design constraints that fired (context, not problems) ------------ #
    for cls, title, note in (
            ("capacity.deadline_lapse", "Case deadlines lapsed",
             "graded lateness in the experiment, not a protocol fault"),
            ("capacity.slot_ceiling", "Per-slot capacity ceilings fired",
             "the declared fallback was used after a role exhausted a case-level call budget"),
            ("context.compaction", "Context compacted",
             "the context budget bound — a treatment observable, not a fault"),
            ("context.pressure_warning", "Context pressure warned", ""),
            ("intervention.recorded", "Interventions recorded",
             "check validity classes on the audit page")):
        evs = _find(events, cls)
        if evs:
            add(cls, "info", f"{title} ×{len(evs)}", note, evs)

    # registered rules: foundation, then the run's pack (loaded on demand)
    from oaos2.archive.renderers import ensure_pack_renderers
    pack_id = (detail["manifest"] or {}).get("task_pack_id")
    ensure_pack_renderers(pack_id)
    for rule in _FOUNDATION_RULES + _PACK_RULES.get(pack_id, []):
        try:
            f.extend(rule(run_dir, events, detail))
        except Exception as exc:  # noqa: BLE001 — a broken rule is itself a finding
            add(f"rule_error:{getattr(rule, '__name__', '?')}", "warning",
                f"Diagnostic rule {getattr(rule, '__name__', '?')} failed",
                f"{type(exc).__name__}: {exc}"[:200])
    # Any other problem-class event (store.is_audit_class) that no rule above names —
    # a task pack's own failure classes included — is still reported, never dropped.
    from oaos2.dashboard.store import is_audit_class
    named = {eid for x in f for eid in x.get("event_ids") or []}
    rest: dict[str, list] = {}
    for e in events:
        cls = e.get("event_class") or ""
        if is_audit_class(cls) and e.get("audience") != "infrastructure" \
                and cls not in _NAMED_ABOVE and e.get("event_id") not in named:
            rest.setdefault(cls, []).append(e)
    for cls, evs in sorted(rest.items()):
        add(f"unlisted:{cls}", "warning", f"{cls} ×{len(evs)}",
            "A recorded failure or refusal with no specific rule; open the events.", evs)
    f.sort(key=lambda x: _SEVERITY_ORDER.get(x["severity"], 9))
    return f


# Classes the foundation list above already reports (the catch-all skips them).
_NAMED_ABOVE = frozenset({
    "run.failed", "run.deadlock_timeout", "isolation.violation", "capture.failed", "docker.oom",
    "docker.disk_exceeded", "docker.capability_gap", "agent.failed", "clock.wind_down",
    "coordination.report_timeout", "docker.launch_failed", "cost.cap_blocked_dispatch",
    "protocol.violation", "handoff_extraction_failed", "handoff_stub_injected", "relay.blocked",
    "tool.denied", "file.reconciliation_mismatch", "evaluation.failed", "model.invocation_failed",
    "chat.timed_out", "outcome.commit_refused"})


# --- foundation rules for the clocked apparatus --------------------------------- #

@register_rule
def commit_races(run_dir: Path, events: list[dict], detail: dict) -> list[dict]:
    """Submissions the platform bounced (nonconformant retries), by day and role —
    the commit races a lateral cell shows when several roles hold the same slot."""
    from oaos2.archive.clock import day_index
    days = day_index(events)
    evs = [e for e in events if e.get("event_class") == "intervention.recorded"
           and (e.get("payload") or {}).get("kind") == "submission_nonconformant_retry"]
    if not evs:
        return []
    by: dict[tuple, int] = {}
    for e in evs:
        key = (days.get(e.get("event_id")), e.get("agent_id") or "·")
        by[key] = by.get(key, 0) + 1
    text = ", ".join(f"day {d}: {a} ×{n}" if d is not None else f"{a} ×{n}"
                     for (d, a), n in sorted(by.items(), key=lambda kv: (kv[0][0] if kv[0][0] is not None else -1, kv[0][1])))
    return [finding("commit_races", "warning", f"Submissions bounced ×{len(evs)}",
                    "the platform refused a payload (wrong slot, slot already closed, missing field) — "
                    "inspect the refusal reason before calling it a race or a duty misread: " + text, evs)]


@register_rule
def compaction_in_open_window(run_dir: Path, events: list[dict], detail: dict) -> list[dict]:
    """A context compaction while the compacting role had items open — the point at
    which notice bodies can drop out of a decision's reach."""
    from oaos2.archive.items import build_items
    comps = [e for e in events if e.get("event_class") == "context.compaction"]
    if not comps:
        return []
    items = build_items(run_dir, events, manifest=detail["manifest"] or {},
                        report=detail["task_report"])["items"]
    hits = []
    for e in comps:
        seq = e.get("sequence_number") or 0
        role = e.get("agent_id")
        n_open = 0
        for it in items:
            arrived = min((a["seq"] for a in it["arrivals"] if a["seq"] is not None), default=None)
            if arrived is None or arrived > seq:
                continue
            d = it["disposition"]
            if d and (d["seq"] or 0) <= seq:
                continue
            involved = (role in it["notified_roles"] or role in it["committers_allowed"]
                        or role in it.get("received_by", []) or role in it.get("observed", {})
                        or not it["notified_roles"])
            if involved:
                n_open += 1
        if n_open:
            hits.append((e, n_open))
    if not hits:
        return []
    text = "; ".join(f"{e.get('agent_id')} with {n} open" for e, n in hits)
    return [finding("compaction_open", "warning", f"Context compacted with items open ×{len(hits)}",
                    "the compacting role held undisposed items it was notified on or may commit — "
                    "read its later dispositions for dropped notice bodies: " + text,
                    [e for e, _ in hits])]


@register_rule
def ceiling_days(run_dir: Path, events: list[dict], detail: dict) -> list[dict]:
    """Days on which a role used every call of its daily ceiling."""
    from oaos2.archive.clock import day_index
    ext = (detail["manifest"] or {}).get("extensions") or {}
    cpd = (ext.get("clock_spec") or ext.get("clock") or {}).get("calls_per_day")
    if not cpd:
        return []
    days = day_index(events)
    calls: dict[tuple, int] = {}
    for e in events:
        if e.get("event_class") == "model.invoked" and e.get("agent_id"):
            key = (e.get("agent_id"), days.get(e.get("event_id")))
            calls[key] = calls.get(key, 0) + 1
    full = sorted((role, d) for (role, d), n in calls.items() if n >= cpd)
    if not full:
        return []
    by_role: dict[str, list[int]] = {}
    for role, d in full:
        by_role.setdefault(role, []).append(d)
    text = "; ".join(f"{r}: days {', '.join(str(x) for x in ds)}" for r, ds in sorted(by_role.items()))
    return [finding("ceiling_days", "info", f"Daily call ceiling reached on {len(full)} role-day(s)",
                    f"{cpd} calls per role per day — capacity bound where it lists: " + text)]


@register_rule
def zero_cost_completed(run_dir: Path, events: list[dict], detail: dict) -> list[dict]:
    """Flag recorded invocations with zero saved cost for execution/pricing review."""
    status = detail["run_status"] or {}
    cost = status.get("cost_usd")
    if cost is None or cost > 0 or detail["disposition"]["disposition"] != "completed":
        return []
    if not any(e.get("event_class") == "model.invoked" for e in events):
        return []
    return [finding("zero_cost", "serious", "Completed with $0 recorded spend",
                    "Invocations are recorded with zero saved cost. This can reflect simulated "
                    "execution, a zero-priced model, or missing accounting; inspect the "
                    "adapter, price table, and usage records before interpreting it.")]


@register_rule
def cost_over_cap(run_dir: Path, events: list[dict], detail: dict) -> list[dict]:
    ext = (detail["manifest"] or {}).get("extensions") or {}
    cap = ext.get("cap_usd")
    total = (detail["metrics"] or {}).get("total_cost_usd") or 0.0
    if not cap or total <= cap:
        return []
    return [finding("over_cap", "serious", f"Spend ${total:.2f} exceeds the ${cap:.2f} cap",
                    "the recorded ledger passed the declared per-cell cap")]


def _closed_by_backstop(e: dict) -> bool:
    reason = str((e.get("payload") or {}).get("reason") or "")
    return bool(reason) and reason not in ("mutual_done", "consensus", "agent_done")


def _forced_assent(events: list[dict]) -> dict | None:
    """Budget-forced assent, wherever the runtime recorded it: a commit payload's
    ``budget_forced`` list or ``consensus_free: false`` interpretation flags."""
    agents: set[str] = set()
    evs = []
    for e in events:
        p = e.get("payload") or {}
        candidates = [p]
        sc = p.get("state_commitment")
        if isinstance(sc, dict):
            candidates.append(sc)
        for c in candidates:
            forced = c.get("budget_forced")
            interp = c.get("interpretation")
            if isinstance(interp, dict) and interp.get("budget_forced"):
                forced = interp["budget_forced"]
            if forced:
                agents.update(str(a) for a in forced)
                evs.append(e)
    return {"agents": agents, "events": evs} if evs else None
