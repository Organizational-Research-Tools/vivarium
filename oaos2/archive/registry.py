"""Index run settings, recorded endings, and saved task scores.

A disposition describes how the event record ends. No terminal event means
incomplete, which can describe an active or interrupted run. A deadlock timeout
marks stalled work; run.failed takes precedence over completion. run_status.json
supplies saved scores and archive-check results. Unscored, below-threshold work,
and run failure are separate statuses. Missing data is not evidence of success."""

from __future__ import annotations

import json
from pathlib import Path

from oaos2.archive.datasets import compute_metrics
from oaos2.archive.transcript import events_in_order


def _run_status(run_dir: Path) -> dict | None:
    sp = Path(run_dir) / "run_status.json"
    if sp.exists():
        try:
            return json.loads(sp.read_text())
        except (ValueError, OSError):
            return None
    return None


def disposition(run_dir: Path, events: list[dict] | None = None) -> dict:
    """Classify how a run ended, from the trace alone (works for killed runs too)."""
    events = events if events is not None else events_in_order(run_dir)
    if not events:
        return {"disposition": "empty", "terminal": None, "terminal_reason": None, "stopped_by_pi": False,
                "outcome_closed": False, "irregular": False, "agent_failed": False}
    classes = [e.get("event_class") for e in events]
    has_completed = "run.completed" in classes
    has_failed = "run.failed" in classes
    has_deadlock = "run.deadlock_timeout" in classes
    agent_failed = "agent.failed" in classes
    outcome_closed = "outcome.closed" in classes
    stopped = "run.stop_requested" in classes  # the PI's clean stop (experiments/stop.py)

    terminal_reason = None
    if has_failed:
        disp = "failed"
        terminal_reason = next((e.get("payload", {}).get("reason")
                                for e in events if e.get("event_class") == "run.failed"), None)
    elif has_deadlock:
        # A stalled run still finalizes as run.completed after the supervisor timeout
        # (the finally-block teardown runs), so the deadlock signal — not the terminal
        # record — is what marks it stalled.
        disp = "stalled"
    elif not has_completed:
        disp = "incomplete"  # no terminal record: active or interrupted
    else:
        disp = "completed"
        if stopped:
            terminal_reason = "stopped_by_pi"
    return {
        "disposition": disp,
        "stopped_by_pi": stopped,
        "terminal": "run.failed" if has_failed else ("run.completed" if has_completed else None),
        "terminal_reason": terminal_reason,
        "outcome_closed": outcome_closed,
        "agent_failed": agent_failed,
        "irregular": agent_failed or has_failed,
    }


def _status(disp: dict, st: dict | None) -> str:
    """Collapse disposition + persisted score into the single headline status."""
    d = disp["disposition"]
    if d == "empty":
        return "empty"
    if d == "failed":
        return "run_failed"
    if d == "stalled":
        return "stalled"
    if d == "incomplete":
        return "incomplete"
    # completed:
    if st is not None and st.get("archive_valid") is False:
        return "invalid_archive"
    if st is None or not disp["outcome_closed"]:
        return "unscored"
    # Current clocked evaluators can close a valid outcome while deliberately
    # deferring scoring.  ``passed: false`` is then a placeholder, not a failed
    # score; ``scored`` is the authoritative discriminator.
    if st.get("scored") is False:
        return "unscored"
    return "passed" if st.get("passed") else "failed_score"


def derived_report_summary(run_dir: Path, events: list[dict], *,
                           task_pack_id: str | None = None) -> tuple[dict, dict]:
    """The pack's registered report, flattened to registry columns, plus where it
    came from: ``(columns, meta)`` with ``meta.source`` ∈ {None, "file",
    "rendered", "error"}.  A file written at finalize (or by a sweep) wins; an
    archive without one is rendered in memory from the frozen streams and the
    hash-pinned assets (never written here — the registry is a reader); a
    renderer failure (pin drift, missing payload) surfaces as ``error`` rather
    than as blank columns pretending the run had no report."""
    from oaos2.archive.renderers import (derived_renderer_for, load_pack_report_file,
                                         render_pack_report, task_pack_id_of)
    run_dir = Path(run_dir)
    renderer = derived_renderer_for(task_pack_id or task_pack_id_of(run_dir))
    if renderer is None:
        return {}, {"source": None, "identity": None, "filename": None, "error": None}
    report = load_pack_report_file(run_dir, renderer)
    stale = report is not None and any(not isinstance(report, dict) or k not in report
                                       for k in getattr(renderer, "expects", ()))
    if report is not None and not stale:
        try:
            return renderer.summary(report), {"source": "file", "identity": None,
                                              "filename": renderer.filename, "error": None}
        except Exception as exc:  # noqa: BLE001 — a malformed file is an error, not silence
            return {}, {"source": "error", "identity": None, "filename": renderer.filename,
                        "error": f"unreadable report file: {type(exc).__name__}: {exc}"[:400]}
    # No saved report, or one that predates the pack's current analysis (``expects``):
    # render. A saved file that cannot be superseded (pinned materials changed) is used.
    out = render_pack_report(run_dir, events, renderer)
    meta = {k: out[k] for k in ("source", "identity", "filename", "error")}
    if out["report"] is None:
        if stale:
            try:
                return renderer.summary(report), {"source": "file", "identity": None,
                                                  "filename": renderer.filename, "error": None}
            except Exception:  # noqa: BLE001
                pass
        return {}, meta
    return renderer.summary(out["report"]), meta


def task_pack_id_of_dir(run_dir: Path) -> str | None:
    from oaos2.archive.renderers import task_pack_id_of
    return task_pack_id_of(run_dir)


def _task_condition(summary: dict, pack_id: str | None) -> str | None:
    """``key=value · …`` over the pack's declared condition keys, or None."""
    from oaos2.archive.renderers import derived_renderer_for
    renderer = derived_renderer_for(pack_id) if pack_id else None
    keys = getattr(renderer, "condition_keys", ()) if renderer else ()
    parts = [f"{k.replace('_', ' ')} {summary[k]}" for k in keys if summary.get(k) is not None]
    return " · ".join(parts) or None


def _outcome(summary: dict, pack_id: str | None, st: dict | None) -> dict | None:
    """The task's central outcome for this run (DerivedRenderer.outcome). A task that
    declares none is one whose scorer's pass/fail is its outcome, and shows that."""
    from oaos2.archive.renderers import derived_renderer_for
    renderer = derived_renderer_for(pack_id) if pack_id else None
    hook = getattr(renderer, "outcome", None) if renderer else None
    if hook is not None:
        try:
            out = hook(summary)
        except Exception as exc:  # noqa: BLE001 — shown, not fatal
            return {"label": f"outcome unreadable: {type(exc).__name__}", "category": "error"}
        if out:
            # the scorer's verdict stays visible beside a task-defined outcome
            verdict = _scorer_verdict(st)
            if verdict and "scorer" not in out:
                out = {**out, "scorer": verdict["label"]}
            return out
    return _scorer_verdict(st)


def _scorer_verdict(st: dict | None) -> dict | None:
    """The scorer's pass/fail, for a task whose scorer's verdict is its outcome (the
    default: a task replaces it only by declaring its own outcome)."""
    if not st or st.get("scored") is False or st.get("passed") is None:
        return None
    verdict = "passed" if st.get("passed") else "failed"
    score = st.get("partial_score")
    return {"label": verdict, "category": verdict,
            "value": score if isinstance(score, (int, float)) else None,
            "detail": f"score {score:.3f}" if isinstance(score, (int, float)) else None}


# Why a run cannot enter results under the platform's completion criteria. A study's
# registered rules decide inclusion; these are the conditions no study can waive.
def eligibility(record: dict, pack_problems: list[str]) -> dict:
    status = record.get("status")
    if status == "incomplete":
        return {"label": "in progress", "reasons": []}
    reasons = []
    if status in ("run_failed", "stalled", "empty", "idle"):
        reasons.append({"run_failed": "the run failed", "stalled": "the run stalled and was force-closed",
                        "empty": "the record is empty",
                        "idle": "the run stopped without finishing"}[status])
    elif status == "invalid_archive":
        reasons.append("the archive failed its checks")
    elif not record.get("outcome_closed"):
        reasons.append("the outcome was not closed")
    if record.get("censored"):
        reasons.append("censored: the clock was wound down or an agent crashed")
    if record.get("report_error"):
        reasons.append("the task report could not be computed")
    reasons += list(pack_problems or [])
    out = {"label": "eligible" if not reasons else "not eligible", "reasons": reasons}
    # flagged, not excluded: the study's registered disposition decides (DerivedRenderer.notes)
    if record.get("pack_notes"):
        out["notes"] = list(record["pack_notes"])
    return out


def _pack_hook(summary: dict, pack_id: str | None, name: str) -> list[str]:
    from oaos2.archive.renderers import derived_renderer_for
    renderer = derived_renderer_for(pack_id) if pack_id else None
    hook = getattr(renderer, name, None) if renderer else None
    try:
        return list(hook(summary)) if hook is not None else []
    except Exception as exc:  # noqa: BLE001
        return [f"{name} rule failed: {type(exc).__name__}"]


def _pack_eligibility(summary: dict, pack_id: str | None) -> list[str]:
    return _pack_hook(summary, pack_id, "eligibility")


def run_record(run_dir: Path, events: list[dict] | None = None) -> dict:
    """One registry row: config + disposition + score for a single run.

    ``events`` lets a caller that already parsed the streams (the dashboard's
    memoized reader) share them; otherwise the streams are read once here."""
    run_dir = Path(run_dir)
    events = events if events is not None else events_in_order(run_dir)
    m = compute_metrics(run_dir, events)
    disp = disposition(run_dir, events)
    st = _run_status(run_dir)
    summary, report_meta = derived_report_summary(run_dir, events,
                                                  task_pack_id=m.get("task_pack_id"))
    clock_summary = summary.get("clock") or {}
    max_batch = summary.get("max_batch_per_round")
    scored = (st or {}).get("scored")
    if scored is None and st is not None:
        scored = (st.get("partial_score") is not None or st.get("passed") is True)
    censored = bool(clock_summary.get("wind_down") or m.get("clock_wind_down")
                    or m.get("n_agent_failures"))
    return {
        "run_id": m.get("run_id") or run_dir.name,
        "experiment_id": m.get("experiment_id"),
        "organization_id": m.get("organization_id") or (st or {}).get("preset_id"),
        "mode": m.get("mode"),
        # Run-level primary (manifest pin, else first invoked, else status); the full
        # invoked list + per-role map (C1h) are preserved, never collapsed.
        "model_ref": m.get("model_ref") or (st or {}).get("model_ref"),
        "model_refs": sorted(m.get("model_refs") or []),
        "role_model_refs": m.get("role_model_refs") or (st or {}).get("role_model_refs") or {},
        "difficulty": (st or {}).get("difficulty"),
        "scored": scored,
        "clock_label": (st or {}).get("clock_label"),
        "rounds_total": (st or {}).get("rounds_total"),
        "status": _status(disp, st),
        "disposition": disp["disposition"],
        "terminal_reason": disp["terminal_reason"],
        "irregular": disp["irregular"],
        "outcome_closed": disp["outcome_closed"],
        "passed": (st or {}).get("passed"),
        "partial_score": (st or {}).get("partial_score"),
        "label": (st or {}).get("label"),
        "scorer_label": (st or {}).get("scorer_label"),
        "parity_regime": (st or {}).get("parity_regime"),
        "exposure_confounded": (st or {}).get("exposure_confounded"),
        "cost_usd": (st or {}).get("cost_usd"),
        # calls that ended without a usage report: cost_usd is then a lower bound
        "n_unknown_usage": sum(1 for e in events if e.get("event_class") == "model.invocation_failed"
                               and (e.get("payload") or {}).get("usage_status") == "unknown"),
        "n_agents": m.get("n_agents"),
        "n_turns": m.get("n_turns"),
        "n_model_calls": m.get("n_model_calls"),
        "n_protocol_violations": m.get("n_protocol_violations"),
        "n_handoffs": m.get("n_handoffs"),
        "n_board_posts": m.get("n_board_posts"),
        "n_notes": m.get("n_notes"),
        "final_round": clock_summary.get("final_round", m.get("final_round")),
        "n_deadline_lapses": clock_summary.get("n_fuse_lapses", m.get("n_deadline_lapses")),
        "n_slot_ceilings": m.get("n_slot_ceilings"),
        "censored": censored,
        "floor_regime": max_batch is not None and max_batch <= 1,
        "max_batch_per_round": max_batch,
        "retained_fraction": summary.get("retained_fraction"),
        "n_repaired": summary.get("n_repaired"),
        "n_unresolved": summary.get("n_unresolved"),
        "n_covered_unhandled": summary.get("n_covered_unhandled"),
        "n_choice_wrong": summary.get("n_choice_wrong"),
        "n_choice_undetermined": summary.get("n_choice_undetermined"),
        "n_lateral_handoffs": summary.get("n_lateral_handoffs"),
        # Where the pack report came from: a finalize-time file, a render at HEAD
        # (stamped with the analysis-code identity), an error, or no pack report.
        # The pack's condition as the run recorded it (DerivedRenderer.condition_keys),
        # e.g. an institution arm, kept apart from its results.
        "task_condition": _task_condition(summary, m.get("task_pack_id") or task_pack_id_of_dir(run_dir)),
        "outcome": _outcome(summary, m.get("task_pack_id") or task_pack_id_of_dir(run_dir), st),
        "pack_eligibility": _pack_eligibility(summary, m.get("task_pack_id") or task_pack_id_of_dir(run_dir)),
        "pack_notes": _pack_hook(summary, m.get("task_pack_id") or task_pack_id_of_dir(run_dir), "notes"),
        "report_source": report_meta.get("source"),
        "report_identity": report_meta.get("identity"),
        "report_error": report_meta.get("error"),
        "event_count": m.get("event_count"),
        "run_dir": str(run_dir),
    }


# Directories a run dir owns that can never contain another run: the walk does
# not descend into them (a pilot archive holds ~15k directories, most of them
# raw/ and captured/ payload trees; pruning turns a 1 s scan into ~0.07 s).
_PRUNE_DIRS = frozenset({"raw", "captured", "container_mount", "filesystem", "derived",
                         "visible", "annotations", "config", "spool", "submitted",
                         ".dashboard", ".removed", "__pycache__"})


def discover_run_dirs(runs_root: Path) -> list[Path]:
    """Every run dir under the root — a dir whose ``trace/`` holds ``events.jsonl``
    (so a stray directory merely NAMED "trace" is never a phantom run). Sorted."""
    import os
    runs_root = Path(runs_root)
    if not runs_root.exists():
        return []
    found: set[Path] = set()

    def _walk(d: Path) -> None:
        try:
            with os.scandir(d) as it:
                entries = [e for e in it if e.is_dir(follow_symlinks=False)]
        except OSError:
            return
        for e in entries:
            if e.name == "trace":
                if os.path.exists(os.path.join(e.path, "events.jsonl")):
                    found.add(Path(d).resolve())
                continue  # never descend into a trace/
            if e.name in _PRUNE_DIRS:
                continue
            _walk(Path(e.path))

    _walk(runs_root)
    return sorted(found)


def scan_runs(runs_root: Path) -> list[dict]:
    """Every run under ``runs_root`` (any dir with a ``trace/``), as registry rows.

    Sorted by (experiment, organization, run_id) for a stable, scannable listing.
    """
    run_dirs = discover_run_dirs(runs_root)
    rows = [run_record(rd) for rd in run_dirs]
    rows.sort(key=lambda r: (r.get("experiment_id") or "", r.get("organization_id") or "",
                             r.get("run_id") or ""))
    return rows


def render_run_registry(runs_root: Path) -> str:
    """A human-scannable table of all runs (status, config, score, cost)."""
    rows = scan_runs(runs_root)
    head = f"# Run registry — {len(rows)} run(s) under {runs_root}\n"
    if not rows:
        return head + "(no runs found)\n"
    cols = [("status", 15), ("experiment_id", 18), ("organization_id", 24), ("model_ref", 22),
            ("difficulty", 10), ("score", 7), ("cost", 8), ("run_id", 0)]

    def _cell(value: str, w: int) -> str:
        s = str(value)
        if not w:
            return s
        return (s[: w - 1] + "…") if len(s) > w else s.ljust(w)  # truncate-then-pad to width

    lines = [head, "  ".join(_cell(name, w) for name, w in cols)]
    for r in rows:
        score = "" if r.get("partial_score") is None else f"{r['partial_score']:.3f}"
        cost = "" if r.get("cost_usd") is None else f"${r['cost_usd']:.2f}"
        flag = " ⚠" if r.get("irregular") else ""
        vals = {
            "status": (r["status"] + flag), "experiment_id": r.get("experiment_id") or "—",
            "organization_id": r.get("organization_id") or "—", "model_ref": r.get("model_ref") or "—",
            "difficulty": r.get("difficulty") or "—", "score": score, "cost": cost,
            "run_id": r.get("run_id") or "—",
        }
        lines.append("  ".join(_cell(vals[name], w) for name, w in cols))
    return "\n".join(lines) + "\n"


def write_registry(runs_root: Path, *, jsonl: Path | None = None, csv_path: Path | None = None) -> dict:
    """Write the registry as JSONL and/or CSV (for analysis); returns counts by status."""
    from collections import Counter

    rows = scan_runs(runs_root)
    if jsonl is not None:
        Path(jsonl).parent.mkdir(parents=True, exist_ok=True)
        Path(jsonl).write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    if csv_path is not None:
        import csv as _csv
        Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
        fields = [k for k in rows[0]] if rows else []
        with Path(csv_path).open("w", newline="") as f:
            w = _csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r in rows:
                w.writerow(r)
    return dict(Counter(r["status"] for r in rows))
