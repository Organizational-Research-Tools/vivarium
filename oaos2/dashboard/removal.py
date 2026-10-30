"""Remove dead runs from the archive the dashboard reads, and restore them (DASHBOARD.md §4.9c).

A dead run is one that produced no usable record of work: it failed, stalled, was left
empty or unfinished, has an invalid archive, or collapsed (an agent crashed, or no model
call was ever answered). Removal moves the run folder, unchanged, to ``runs/.removed/``
under its original relative path; the registry scan does not descend there, so the run
leaves every page. Restoring moves it back. Nothing inside a run is written or deleted
here; permanent deletion is the researcher's, by emptying ``runs/.removed/`` by hand.

Two kinds of run are never removable from the dashboard, however they ended: confirmatory
runs, whose exclusion or replacement is the study's decision under its registered rules,
and runs in a frozen analysis dataset, which a result of record already reads.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

REMOVED_DIR = ".removed"
LEDGER = "removed.jsonl"
# An unfinished run whose trace has not moved this long is read as interrupted, not
# running. Short enough to clear a crashed launch the same afternoon; long enough that a
# run waiting on one slow model call is never taken for dead.
QUIET_MINUTES = 15

_DEAD_STATUS = {
    "empty": "the run recorded no events",
    "run_failed": "the run failed",
    "stalled": "the run stalled (deadlock timeout)",
    "idle": "the run stopped without finishing and has been idle for days",
    "invalid_archive": "the archive check failed",
}


def _quiet_minutes(run_dir: Path, now: float) -> float | None:
    try:
        newest = max(p.stat().st_mtime for p in (Path(run_dir) / "trace").iterdir() if p.is_file())
    except (OSError, ValueError):
        return None
    return (now - newest) / 60


def dead_reason(row: dict, *, now: float | None = None) -> str | None:
    """Why this registry row counts as dead, or None when it does not."""
    now = time.time() if now is None else now
    status = row.get("status")
    if status in _DEAD_STATUS:
        return _DEAD_STATUS[status]
    if status == "incomplete":
        quiet = _quiet_minutes(Path(row["run_dir"]), now)
        if quiet is not None and quiet >= QUIET_MINUTES:
            return f"the run stopped without finishing; nothing written for {int(quiet)} minutes"
        return None  # still being written, or too recently to tell
    # A crash is the collapse signal. Zero answered calls alone is not: archives written
    # before ``model.responded`` existed count zero although their agents worked.
    if row.get("irregular"):
        if row.get("n_model_calls") == 0:
            return "the run collapsed: agents crashed and no model call was answered"
        return "the run collapsed: an agent crashed"
    return None


def protected_reason(row: dict) -> str | None:
    """Why a dead run must stay in the archive, or None when it may be removed."""
    if row.get("mode") == "confirmatory":
        return "confirmatory run: its exclusion or replacement is decided by the study's registered rules"
    if row.get("in_frozen_dataset"):
        return "part of a frozen analysis dataset"
    return None


def removable(row: dict, *, now: float | None = None) -> tuple[str | None, str | None]:
    """``(dead_reason, protected_reason)``; a run may be removed when the first is set
    and the second is not."""
    dead = dead_reason(row, now=now)
    return dead, (protected_reason(row) if dead else None)


def _removed_root(runs_root: Path) -> Path:
    return Path(runs_root) / REMOVED_DIR


def _prune_empty_parents(start: Path, stop: Path) -> None:
    """Remove now-empty folders from ``start`` up to (not including) ``stop``."""
    d, stop = start, stop.resolve()
    while d.resolve() != stop and stop in d.resolve().parents:
        try:
            d.rmdir()  # only succeeds when empty
        except OSError:
            return
        d = d.parent


def _append_ledger(runs_root: Path, entry: dict) -> None:
    root = _removed_root(runs_root)
    root.mkdir(parents=True, exist_ok=True)
    with open(root / LEDGER, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")


def remove_run(runs_root: Path, run_dir: Path, run_ref: str, *, reason: str, status: str | None) -> Path:
    """Move one run folder to ``runs/.removed/<run_ref>`` and note it in the ledger."""
    runs_root, run_dir = Path(runs_root), Path(run_dir)
    target = _removed_root(runs_root) / run_ref
    if target.exists():
        raise FileExistsError(f"{run_ref} is already in {REMOVED_DIR}/")
    target.parent.mkdir(parents=True, exist_ok=True)
    os.rename(run_dir, target)  # same volume: atomic, nothing copied or rewritten
    _prune_empty_parents(run_dir.parent, runs_root)
    _append_ledger(runs_root, {"action": "removed", "run_ref": run_ref, "status": status,
                               "reason": reason, "at": time.time()})
    return target


def restore_run(runs_root: Path, run_ref: str) -> Path:
    """Move a removed run back to where it was."""
    runs_root = Path(runs_root)
    removed = _removed_root(runs_root).resolve()
    source = (removed / run_ref).resolve()
    if removed not in source.parents or not (source / "trace" / "events.jsonl").exists():
        raise FileNotFoundError(f"no removed run {run_ref!r}")
    target = (runs_root / run_ref).resolve()
    # the run goes back under runs/ and nowhere else: a run_ref with ".." must not move it out (security audit,
    # October 29, 2026)
    if runs_root.resolve() not in target.parents or target == removed or removed in target.parents:
        raise FileNotFoundError(f"no removed run {run_ref!r}")
    if target.exists():
        raise FileExistsError(f"{run_ref} exists again under runs/; not overwriting it")
    target.parent.mkdir(parents=True, exist_ok=True)
    os.rename(source, target)
    _prune_empty_parents(source.parent, removed)
    _append_ledger(runs_root, {"action": "restored", "run_ref": run_ref, "at": time.time()})
    return target


def list_removed(runs_root: Path) -> list[dict]:
    """Runs now in ``runs/.removed/``, newest removal first, with the ledger's note."""
    from oaos2.archive.registry import discover_run_dirs
    removed = _removed_root(runs_root)
    notes: dict[str, dict] = {}
    try:
        for line in (removed / LEDGER).read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("action") == "removed":
                notes[entry.get("run_ref")] = entry
    except OSError:
        pass
    out = []
    for d in discover_run_dirs(removed):
        ref = d.relative_to(removed.resolve()).as_posix()
        note = notes.get(ref) or {}
        out.append({"run_ref": ref, "lineage": ref.split("/", 1)[0], "status": note.get("status"),
                    "reason": note.get("reason"), "at": note.get("at")})
    return sorted(out, key=lambda r: (-(r["at"] or 0), r["run_ref"]))
