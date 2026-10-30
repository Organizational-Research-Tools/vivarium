"""Read-only accessors over ``runs/`` (DASHBOARD.md §3) — the dashboard's data layer.

Everything here is a pure read of the archive via the ``oaos2.archive`` projections;
nothing writes a run. Runs are addressed by ``run_ref`` — the run dir's POSIX path
relative to the runs root — which doubles as the URL id; ``resolve_run_dir`` is the
one place a ref becomes a path, with containment checked (a ref must land under the
root AND look like a run), so a crafted URL can't read outside the runs tree.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from oaos2.archive.datasets import compute_metrics
from oaos2.archive.registry import _run_status, disposition, eligibility, run_record
from oaos2.dashboard.cache import RegistryCache


def _run_ref(runs_root: Path, run_dir: Path) -> str | None:
    try:
        return Path(run_dir).resolve().relative_to(Path(runs_root).resolve()).as_posix()
    except ValueError:
        return None  # outside the root (shouldn't happen for discovered runs)


IDLE_AFTER_HOURS = 48  # an unfinished run whose record has not moved this long is read as idle


def apply_idle(record: dict, run_dir: Path, *, now: float | None = None) -> dict:
    """Read an unfinished run whose record stopped moving as ``idle`` (DASHBOARD.md §4.9b).

    The archive is not touched and the recorded status is kept as ``recorded_status``;
    ``idle`` is decided at read time from the newest file time under ``trace/``, so it is
    never cached. An idle run is not in flight: it does not hold its experiment
    outcome-blind. It is still unfinished and still needs attention."""
    import time
    if record.get("status") != "incomplete":
        return record
    try:
        newest = max(p.stat().st_mtime for p in (Path(run_dir) / "trace").iterdir() if p.is_file())
    except (OSError, ValueError):
        return record
    idle_s = (now if now is not None else time.time()) - newest
    record["idle_minutes"] = int(idle_s // 60)
    if idle_s > IDLE_AFTER_HOURS * 3600:
        record["recorded_status"] = "incomplete"
        record["status"] = "idle"
    return record


def list_runs(runs_root: Path, *, cache: RegistryCache | None = None,
              rebuild: bool = False) -> list[dict]:
    """Registry rows (cached), each augmented with its URL-addressable ``run_ref``."""
    cache = cache or RegistryCache(runs_root)
    rows = cache.scan(rebuild=rebuild)
    for r in rows:
        r["run_ref"] = _run_ref(runs_root, Path(r["run_dir"]))
        # the top-level directory is the lineage (a batch, a probe, a sweep) — the
        # grouping a reader actually navigates by, which experiment_id alone misses
        r["lineage"] = r["run_ref"].split("/", 1)[0] if r["run_ref"] else None
        apply_idle(r, Path(r["run_dir"]))
        r["eligibility"] = eligibility(r, r.get("pack_eligibility") or [])
    return [r for r in rows if r["run_ref"]]


def resolve_run_dir(runs_root: Path, run_ref: str) -> Path | None:
    """``run_ref`` → run dir, or None. Containment is checked on the *resolved* path
    (symlinks and ``..`` can't escape the root) and the target must hold an event
    stream — the same "is a run" rule the registry scan uses."""
    root = Path(runs_root).resolve()
    candidate = (root / run_ref).resolve()
    if candidate == root or root not in candidate.parents:
        return None
    if not (candidate / "trace" / "events.jsonl").exists():
        return None
    return candidate


def run_detail(run_dir: Path, events: list[dict] | None = None, *,
               reports=None) -> dict:
    """Everything the run-overview page shows, one stream read (DASHBOARD.md §4.2).

    Metrics/disposition are recomputed live rather than read from ``derived/`` so a
    killed or in-flight run (no re-render yet) still gets a faithful page. Pass the
    memoized ``events`` so the page parses the streams once; ``reports`` is the
    dashboard's ``ReportStore`` (the pack report from a finalize-time file, else
    rendered at HEAD and kept under ``runs/.dashboard`` — never written to the run)."""
    run_dir = Path(run_dir)
    if events is None:
        from oaos2.dashboard.events import load_events  # memoized reader
        events = load_events(run_dir)
    record = apply_idle(run_record(run_dir, events=events), run_dir)
    record["eligibility"] = eligibility(record, record.get("pack_eligibility") or [])
    if reports is not None:
        report = reports.get(run_dir, events)
    else:
        from oaos2.archive.renderers import load_pack_report_file
        loaded = load_pack_report_file(run_dir)
        report = {"report": loaded, "source": "file" if loaded is not None else None,
                  "identity": None, "filename": None, "error": None}
    detail = {
        "record": record,
        "disposition": disposition(run_dir, events),
        "metrics": compute_metrics(run_dir, events),
        "manifest": _read_json(run_dir / "manifest.json"),
        "run_status": _run_status(run_dir),
        "resolved_config": _read_json(run_dir / "config" / "resolved.json"),
        "task_report": report["report"],
        "task_report_meta": {k: report.get(k) for k in ("source", "identity", "filename", "error", "superseded_file", "stale_keys")},
        "derived_files": sorted(p.name for p in (run_dir / "derived").glob("*")
                                if p.is_file()) if (run_dir / "derived").exists() else [],
        "annotation_namespaces": sorted(p.stem for p in (run_dir / "annotations").glob("*.jsonl"))
        if (run_dir / "annotations").exists() else [],
    }
    # The audit strip (§4.6 summary): every event class that signals trouble, with counts.
    by_class = detail["metrics"].get("events_by_class") or {}
    detail["audit_classes"] = {c: n for c, n in sorted(by_class.items()) if is_audit_class(c)}
    return detail


# Event classes that signal trouble — the audit views, Story, Flow, agent profiles and
# the live view all key on this one rule. A timeout (the platform filled in for a
# missing report), a refused commit, and an assessment or finalization left incomplete
# are platform problems. A task's own refusals (the lab interface declining a measurement request, a scorer
# refusing credit), a deadline lapse, or an invalid repair attempt are outcomes the
# task pack shows, so "refused", "lapse" and "invalid" are deliberately not markers.
AUDIT_MARKERS = ("violation", "denied", "failed", "blocked", "oom", "disk_exceeded",
                 "capability_gap", "mismatch", "deadlock", "cap_blocked", "wind_down",
                 "timed_out", "timeout", "incomplete", "commit_refused")


def is_audit_class(event_class: str) -> bool:
    return any(m in (event_class or "") for m in AUDIT_MARKERS)


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError):
        return None


# --- registry-page shaping (filters + per-arm aggregates) ------------------- #

_FILTER_KEYS = {"status": "status", "lineage": "lineage", "experiment": "experiment_id",
                "organization": "organization_id", "model": "model_ref",
                "difficulty": "difficulty", "mode": "mode", "clock": "clock_label"}


def filter_rows(rows: list[dict], *, q: str | None = None, **filters: str | None) -> list[dict]:
    """Exact-match column filters (including mode and logical-clock condition)
    plus a substring match ``q`` over run_id."""
    out = rows
    for key, value in filters.items():
        if value:
            col = _FILTER_KEYS[key]  # unknown filter name = caller bug, fail loud
            out = [r for r in out if r.get(col) == value]
    if q:
        needle = q.lower()
        out = [r for r in out if needle in (r.get("run_id") or "").lower()]
    return out


def facet_values(rows: list[dict]) -> dict[str, list[str]]:
    """Distinct non-null values per filterable column (populates the filter selects)."""
    return {name: sorted({r.get(col) for r in rows if r.get(col)})
            for name, col in _FILTER_KEYS.items()}


# Keep saved identities, not today's provenance category: two stale versions are
# still different setups. The complete serialized values decide grouping; the
# short digest is only a display label.
_SUMMARY_FACTORS = ("experiment_id", "organization_id", "task_pack_id", "difficulty",
                    "clock_label", "mode", "model_ref", "role_model_refs", "task_condition")
_SUMMARY_PINS = ("research_setup_sha256", "apparatus_sha256", "task_manifest_sha256",
                 "hidden_reference_sha256s", "reference_sha256", "contract_profile",
                 "environment_schedule_sha256", "schedule_variant", "clock_spec",
                 "cap_usd", "cap_output_tokens", "parity_regime", "context_budget",
                 "report_source", "report_identity")


ELIGIBLE = ("eligible", "in analysis dataset")


def n_eligible(rows: list[dict]) -> int:
    return sum(1 for r in rows if (r.get("eligibility") or {}).get("label") in ELIGIBLE)


def outcome_digest(rows: list[dict]) -> str | None:
    """One line over the eligible runs' task outcomes: counts by category when the task
    names kinds of outcome, else the mean of a numeric outcome. Descriptive only; a
    study's registered analysis decides what the runs show."""
    kept = [r for r in rows if r.get("outcome") and (r.get("eligibility") or {}).get("label") in ELIGIBLE]
    if not kept or len({r.get("task_pack_id") for r in kept}) > 1:
        return None  # nothing eligible, or outcomes of different tasks that do not add up
    outs = [r["outcome"] for r in kept]
    cats: dict[str, int] = {}
    for o in outs:
        if o.get("category"):
            cats[o["category"]] = cats.get(o["category"], 0) + 1
    if cats:
        return " · ".join(f"{n} {c}" for c, n in sorted(cats.items(), key=lambda kv: (-kv[1], kv[0])))
    vals = [o["value"] for o in outs if isinstance(o.get("value"), (int, float))]
    if not vals:
        return None
    mean = sum(vals) / len(vals)
    head = outs[0]["label"].split(" ", 1)[0]  # the outcome's own word, e.g. "retained"
    shown = f"{mean * 100:.1f}%" if head == "retained" else f"{mean:.3f}"
    return f"mean {head} {shown} (n={len(vals)})"


def arm_summary(rows: list[dict]) -> list[dict]:
    """Exploratory means within saved conditions, without registered exclusions.

    Preserve requirement tier, clock, mode, model assignments, and setup pins.
    Legacy rows without a setup fingerprint stay separate: matching a lone
    answer-key hash cannot establish that their materials and settings agree.
    """
    groups: dict[str, tuple[dict, list[dict]]] = {}
    for index, row in enumerate(rows):
        factors = {key: row.get(key) for key in _SUMMARY_FACTORS}
        pins = {key: row.get(key) for key in _SUMMARY_PINS if row.get(key) is not None}
        setup_pinned = bool(row.get("research_setup_sha256") or row.get("apparatus_sha256"))
        identity = {"factors": factors, "pins": pins}
        if not setup_pinned:
            identity["unpooled_run"] = row.get("run_ref") or row.get("run_id") or row.get("run_dir") or index
        key = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        if key not in groups:
            groups[key] = ({**factors, "setup_pinned": setup_pinned,
                            "material_pins": pins,
                            "material_identity": hashlib.sha256(key.encode()).hexdigest()[:12]}, [])
        groups[key][1].append(row)
    out = []
    for key in sorted(groups):
        condition, members = groups[key]
        scored = [r["partial_score"] for r in members if r.get("partial_score") is not None]
        retained = [r["retained_fraction"] for r in members
                    if r.get("retained_fraction") is not None]
        costs = [r["cost_usd"] for r in members if r.get("cost_usd") is not None]
        out.append({
            **condition,
            "n_runs": len(members),
            "n_passed": sum(1 for r in members if r.get("status") == "passed"),
            "n_scored": sum(1 for r in members if r.get("scored")),
            "n_censored": sum(1 for r in members if r.get("censored")),
            "n_floor": sum(1 for r in members if r.get("floor_regime")),
            "n_irregular": sum(1 for r in members if r.get("irregular")),
            "mean_partial_score": (sum(scored) / len(scored)) if scored else None,
            "mean_retained": (sum(retained) / len(retained)) if retained else None,
            "n_rendered": sum(1 for r in members if r.get("report_source") == "rendered"),
            "total_cost_usd": sum(costs) if costs else None,
            "n_unknown_usage": sum(r.get("n_unknown_usage") or 0 for r in members),
            "n_eligible": n_eligible(members),
            "outcome_digest": outcome_digest(members),
        })
    return out
