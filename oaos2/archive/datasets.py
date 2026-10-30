"""Run metrics + analysis-dataset export (DESIGN §17.3, §6.6, principle 7).

Transcripts, dashboards, metrics, datasets are all *derived* from the one archive
(design principle 7). ``compute_metrics`` is the pure aggregation backing both
``derived/metrics.json`` and the flat analysis row; ``run_row`` flattens a run to a
single record and ``runs_to_jsonl``/``runs_to_csv`` stack many runs (a sweep) into
an analysis-ready table. No wall-clock enters the output, so it re-renders identically.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from oaos2.archive.transcript import events_in_order


def _manifest(run_dir: Path) -> dict:
    mp = Path(run_dir) / "manifest.json"
    if mp.exists():
        try:
            return json.loads(mp.read_text())
        except (ValueError, OSError):
            return {}
    return {}


def compute_metrics(run_dir: Path, events: list[dict] | None = None) -> dict:
    """Aggregate, fully-derived metrics for one run (DESIGN §6.6 self-observability +
    §17.3 ``metrics.json``). Pure function of the trace + manifest. ``events`` may be
    preloaded to avoid re-reading the stream."""
    events = events if events is not None else events_in_order(run_dir)
    # Coerce a missing OR null event_class to "?" — a torn/partial event with an explicit
    # null key would otherwise put a None bucket in the Counter and crash the sort below
    # (None < str), taking the whole run registry down with it.
    by_class = Counter((e.get("event_class") or "?") for e in events)
    manifest = _manifest(run_dir)

    input_tokens = output_tokens = 0
    cost_usd = 0.0
    model_refs: list[str] = []
    intervention_classes: Counter = Counter()
    n_notes = 0  # agent-initiated private notes: message.sent with the foundation kind "note"
    for e in events:
        cls, p = e.get("event_class"), (e.get("payload") or {})
        if cls == "message.sent" and p.get("kind") == "note":
            n_notes += 1
        if cls == "model.responded":
            u = p.get("usage") or {}
            input_tokens += u.get("input", 0) or 0
            output_tokens += u.get("output", 0) or 0
        elif cls == "model.invoked":
            ref = p.get("model_ref")
            if ref and ref not in model_refs:
                model_refs.append(ref)
        elif cls == "cost.recorded":
            cost_usd += p.get("cost_usd", 0.0) or 0.0
        elif cls == "intervention.recorded":
            intervention_classes[p.get("class", "unknown")] += 1

    agents = []
    for e in events:
        a = e.get("agent_id")
        if a and a not in agents:
            agents.append(a)

    ext = manifest.get("extensions") or {}
    return {
        "run_id": manifest.get("run_id"),
        "experiment_id": manifest.get("experiment_id"),
        "task_pack_id": manifest.get("task_pack_id"),
        "organization_id": manifest.get("organization_id"),
        "mode": manifest.get("mode"),
        # Primary = the RUN-LEVEL ref the manifest pins (what roles inherit); an
        # unpinned legacy archive falls back to the first provider invoked. The
        # full invoked list and the per-role map (C1h) ride beside it.
        "model_ref": ext.get("model_ref") or (model_refs[0] if model_refs else None),
        "model_refs": model_refs,
        "role_model_refs": dict(sorted((ext.get("role_model_refs") or {}).items())),
        "pricing_table_version": manifest.get("pricing_table_version"),
        "n_agents": len(agents),
        "agents": agents,
        "event_count": len(events),
        "n_turns": by_class.get("turn.completed", 0),
        "n_model_calls": by_class.get("model.responded", 0),
        "n_tool_calls": by_class.get("tool.called", 0),
        "n_tool_denied": by_class.get("tool.denied", 0),
        "n_commitments": by_class.get("state.committed", 0),
        "n_handoffs": by_class.get("handoff", 0),
        "n_conversations": by_class.get("conversation.opened", 0),
        # Voluntary communication (M8 §7): posts and notes are what agents chose to
        # say; retrievals are explicit reads. Delivery, retrieval, and recognition
        # stay separate counts — none of them measures understanding.
        "n_messages": by_class.get("message.sent", 0),
        "n_board_posts": by_class.get("board.posted", 0),
        "n_notes": n_notes,
        "n_board_reads": by_class.get("board.retrieved", 0),
        "n_note_reads": by_class.get("notes.retrieved", 0),
        "n_protocol_violations": by_class.get("protocol.violation", 0),
        # Logical-clock and capacity observables.  These remain generic trace
        # counts: task-specific constructs (retained benefit, repaired cases,
        # censoring rules) stay in the pack's downstream trace analysis.
        "n_clock_rounds": by_class.get("clock.round", 0),
        "final_round": _final_round(events),
        "n_deadline_lapses": by_class.get("capacity.deadline_lapse", 0),
        "n_slot_ceilings": by_class.get("capacity.slot_ceiling", 0),
        "clock_wind_down": by_class.get("clock.wind_down", 0) > 0,
        "n_agent_failures": by_class.get("agent.failed", 0),
        "n_interventions": sum(intervention_classes.values()),
        "interventions_by_class": dict(intervention_classes),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_cost_usd": round(cost_usd, 6),
        "outcome_closed": by_class.get("outcome.closed", 0) > 0,
        "run_completed": by_class.get("run.completed", 0) > 0,
        "events_by_class": dict(sorted(by_class.items())),
    }


def _final_round(events: list[dict]) -> int | None:
    """Highest logical round observed, independent of wall-clock ordering."""
    rounds = []
    for e in events:
        if e.get("event_class") != "clock.round":
            continue
        p = e.get("payload") or {}
        value = p.get("round_no")
        if value is None:
            value = p.get("round") if p.get("round") is not None else p.get("round_index")
        try:
            rounds.append(int(value))
        except (TypeError, ValueError):
            pass
    return max(rounds) if rounds else None


# --- flat analysis rows (one per run; stack a sweep) ----------------------- #

_ROW_FIELDS = [
    "run_id", "experiment_id", "task_pack_id", "organization_id", "mode",
    "n_agents", "n_turns", "n_model_calls", "n_tool_calls", "n_tool_denied",
    "n_commitments", "n_handoffs", "n_conversations", "n_protocol_violations",
    "n_messages", "n_board_posts", "n_notes", "n_board_reads", "n_note_reads",
    "n_interventions", "input_tokens", "output_tokens", "total_cost_usd",
    "outcome_closed", "run_completed", "event_count",
]


_MODEL_FIELDS = ["model_ref", "model_refs", "role_model_refs"]


def run_row(run_dir: Path) -> dict:
    """One flat analysis row for a run. ``model_ref`` is the run-level primary;
    ``model_refs`` (every provider invoked, sorted) and ``role_model_refs`` (the
    manifest's per-role map, C1h) are kept whole rather than collapsed."""
    m = compute_metrics(run_dir)
    row = {k: m.get(k) for k in _ROW_FIELDS}
    row["model_ref"] = m.get("model_ref")
    row["model_refs"] = sorted(m.get("model_refs") or [])
    row["role_model_refs"] = m.get("role_model_refs") or {}
    return row


def runs_to_jsonl(run_dirs: list[Path], out_path: Path) -> Path:
    """Stack many runs (a sweep) into a JSONL analysis dataset."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        for rd in run_dirs:
            f.write(json.dumps(run_row(rd), sort_keys=True) + "\n")
    return out_path


def runs_to_csv(run_dirs: list[Path], out_path: Path) -> Path:
    """Stack many runs into a CSV analysis dataset (stable column order; the
    list/map model fields are JSON-encoded so the CSV stays one row per run)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [run_row(rd) for rd in run_dirs]
    fields = _ROW_FIELDS + _MODEL_FIELDS
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v, sort_keys=True) if isinstance(v, (list, dict)) else v)
                        for k, v in r.items()})
    return out_path
