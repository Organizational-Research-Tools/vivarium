"""Separate what happened in a run from what changed around it (DASHBOARD.md §4.9a).

A **run condition** is recorded in the run and changes how its result may be read:
a censored clock, a mechanical floor, a crash, an ending that is not a completion.
An **archive note** is a fact about the repository then or now: materials that have
since changed, a launch from uncommitted code, no pin to compare, a task report that
cannot be recomputed against today's library. Conditions are shown where the run is
read; notes belong to the Record view. Nothing here hides a fact; it decides placement.
"""

from __future__ import annotations

UNFINISHED = ("run_failed", "stalled", "incomplete", "idle", "empty", "invalid_archive")

_CONDITIONS = (
    ("censored", "censored", "critical",
     "The clock was wound down or an agent failed with the outcome still open. Do not read this as an ordinary result."),
    ("floor_regime", "mechanical floor", "critical",
     "No role completed more than one disposition per round; this is not evidence about usable parallel capacity."),
    ("irregular", "irregular", "serious",
     "Something crashed during this run: an agent or the run itself. Read the audit before using the result."),
)


def run_conditions(record: dict) -> list[dict]:
    """Recorded conditions that change how this run's result may be read."""
    out = [{"key": key, "label": label, "severity": sev, "text": text}
           for key, label, sev, text in _CONDITIONS if record.get(key)]
    status = record.get("status")
    if status in UNFINISHED:
        out.append({"key": "unfinished", "label": str(status).replace("_", " "), "severity": "serious",
                    "text": "The run did not reach an ordinary completion; saved results are partial."})
    return out


def report_state(record: dict, provenance: str | None, report_meta: dict | None) -> dict:
    """Why a task report is missing, in the run's terms rather than the renderer's.

    ``kind``: ``ok`` (a report exists or the pack has none), ``unfinished`` (the run never
    produced what the report reads), ``not_recomputable`` (the pinned materials differ from
    today's library, so the pack refuses to recompute), or ``error`` (unexplained)."""
    meta = report_meta or {}
    error = meta.get("error")
    if meta.get("source") != "error" and not error:
        return {"kind": "ok", "text": None, "error": None}
    if record.get("status") in UNFINISHED:
        return {"kind": "unfinished", "error": error,
                "text": "The run did not finish, so the task report has nothing to read."}
    if provenance == "stale_materials":
        return {"kind": "not_recomputable", "error": error,
                "text": "No report was saved with this run, and the task refuses to recompute one "
                        "because the run's pinned materials differ from today's library."}
    return {"kind": "error", "error": error,
            "text": "The task report failed for a reason the archive does not explain."}


def archive_notes(record: dict, provenance: str | None, reasons: list[str] | None,
                  report: dict, *, source_dirty: bool = False) -> list[dict]:
    """Facts about the repository then or now; shown in Record, summarized elsewhere."""
    notes = []
    if provenance == "stale_materials":
        notes.append({"key": "stale_materials", "label": "materials changed since",
                      "text": "The library has changed since this run. Read its score with its saved "
                              "materials; the study's rules decide comparability.",
                      "detail": list(reasons or [])})
    elif provenance == "superseded":
        notes.append({"key": "superseded", "label": "removed apparatus",
                      "text": "Historical record of a removed apparatus; it makes no claim about the current experiment.",
                      "detail": list(reasons or [])})
    elif provenance == "unknown":
        notes.append({"key": "unknown", "label": "no pin to compare",
                      "text": "The run carries no reference pin the library check can compare.",
                      "detail": list(reasons or [])})
    if source_dirty:
        notes.append({"key": "source_dirty", "label": "uncommitted source",
                      "text": "Launched from uncommitted code. The run pins its worktree and apparatus "
                              "hashes; the commit alone does not reconstruct what ran.", "detail": []})
    if report["kind"] in ("not_recomputable", "unfinished"):
        notes.append({"key": "report_" + report["kind"], "label": "no task report",
                      "text": report["text"], "detail": [report["error"]] if report.get("error") else []})
    return notes


def row_attention(row: dict) -> list[str]:
    """Labels for the one attention marker in lists: run conditions plus unexplained errors."""
    labels = [c["label"] for c in run_conditions(row)]
    if report_state(row, row.get("provenance"),
                    {"source": row.get("report_source"), "error": row.get("report_error")})["kind"] == "error":
        labels.append("report error")
    return labels


_MATERIAL_PINS = (("task_manifest_sha256", "task manifest"),
                  ("reference_sha256", "scoring reference"),
                  ("hidden_reference_sha256s", "hidden references"),
                  ("environment_schedule_sha256", "environment schedule"))


def material_versions(rows: list[dict]) -> list[dict]:
    """Saved material pins that take more than one value across these runs.

    Drift matters where runs are compared, so the experiment page reports it once instead
    of every run page warning about it. Whether the versions are comparable is the
    study's decision; this only counts distinct saved values."""
    import json
    out = []
    for field, label in _MATERIAL_PINS:
        counts: dict[str, int] = {}
        for r in rows:
            value = r.get(field)
            if value in (None, "", [], {}):
                continue
            key = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
            counts[key] = counts.get(key, 0) + 1
        if len(counts) > 1:
            out.append({"field": field, "label": label,
                        "versions": sorted(counts.values(), reverse=True)})
    return out
