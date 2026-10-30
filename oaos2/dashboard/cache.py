"""Registry cache (DASHBOARD.md §3) — rebuildable, disposable, never authoritative.

``archive.registry.scan_runs`` re-reads every event stream on every scan; fine for
a CLI, too slow for a page load over hundreds of runs. This cache memoizes one
registry row per run dir, keyed by a cheap fingerprint of the files the row
derives from — like ``trace/index.sqlite`` it is a *view*: corrupt or stale, it is
dropped and rebuilt from the streams, never trusted over them. It lives under
``<runs_root>/.dashboard/`` (inside the gitignored run-output tree, beside no run).
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

from oaos2.archive.registry import discover_run_dirs, run_record
from oaos2.archive.renderers import derived_renderer_for, task_pack_id_of

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_dir     TEXT PRIMARY KEY,   -- resolved absolute path
    fingerprint TEXT NOT NULL,
    row_json    TEXT NOT NULL
)
"""

# Bump when the cached row shape changes (e.g. new enrichment fields): a version
# mismatch drops the table so old rows can't serve with fields missing.
_CACHE_VERSION = 14

# Everything a registry row is derived from (registry.run_record reads exactly
# these); if none of them changed, the cached row is byte-equivalent to a rescan.
# The pack report's own inputs (its derived file, the captured submissions, the
# run-local schedule) and the analysis-code identity join the fingerprint per
# run, from the registered renderer — never a pack filename named here.
_ROW_SOURCES = ("trace/events.jsonl", "trace/infra.jsonl", "manifest.json", "run_status.json")
_REPORT_INPUTS = ("captured/submitted", "submitted", "config/environment_schedule.json")

# FastAPI runs sync route handlers in a thread pool.  Serialize scans of the
# same disposable cache within one process; SQLite's busy timeout below covers
# a second dashboard/CLI process.  A busy database is not corrupt and must
# never trigger the destructive rebuild path.
_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _cache_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def _manifest_pins(run_dir: Path) -> dict:
    """The manifest fields provenance classification needs on every registry row
    (a registry row alone can't say whether the run's materials are still current)."""
    try:
        m = json.loads((run_dir / "manifest.json").read_text())
    except (OSError, ValueError):
        m = {}
    ext = m.get("extensions") or {}
    clock = ext.get("clock_spec") or ext.get("clock") or {}
    pins = {
        "task_pack_id": m.get("task_pack_id"),
        "reference_sha256": ext.get("reference_sha256"),
        "hidden_reference_sha256s": ext.get("hidden_reference_sha256s"),
        "task_manifest_sha256": ext.get("task_manifest_sha256"),
        "apparatus_sha256": ext.get("apparatus_sha256"),
        "research_setup_sha256": ext.get("research_setup_sha256"),
        "environment_schedule_sha256": ext.get("environment_schedule_sha256"),
        "clock_spec": clock,
        "cap_output_tokens": ext.get("cap_output_tokens"),
        "source_commit": ext.get("source_commit"),
        "source_dirty": ext.get("source_dirty"),
        "source_worktree_sha256": ext.get("source_worktree_sha256"),
        "contract_profile": ext.get("contract_profile"),
        "schedule_variant": ext.get("environment_schedule_variant")
                            or clock.get("schedule_variant"),
        "clock_label": ext.get("clock_label") or ext.get("environment_schedule_variant")
                       or clock.get("schedule_variant"),
        "rounds_total": clock.get("rounds_total"),
        "cap_usd": ext.get("cap_usd"),
    }
    # In-flight clocked runs have no run_status.json yet; their manifest still
    # carries these declared cell factors.  Do not overwrite legacy row values
    # with None when older manifests lack the pins.
    for key in ("model_ref", "difficulty"):
        if ext.get(key) is not None:
            pins[key] = ext[key]
    return pins


def _stat_part(path: Path, rel: str) -> str:
    try:
        st = path.stat()
    except OSError:
        return f"{rel}:-"
    if path.is_dir():
        try:
            names = sorted(os.listdir(path))
        except OSError:
            names = []
        newest = max((int((path / n).stat().st_mtime_ns) for n in names), default=0)
        return f"{rel}:d{len(names)}:{newest}"
    return f"{rel}:{st.st_size}:{st.st_mtime_ns}"


def fingerprint(run_dir: Path) -> str:
    run_dir = Path(run_dir)
    parts = [_stat_part(run_dir / rel, rel) for rel in _ROW_SOURCES]
    renderer = derived_renderer_for(task_pack_id_of(run_dir))
    if renderer is not None:
        parts.append(_stat_part(run_dir / "derived" / renderer.filename,
                                f"derived/{renderer.filename}"))
        parts += [_stat_part(run_dir / rel, rel) for rel in _REPORT_INPUTS]
        parts.append(f"renderer:{renderer.identity}")
    return "|".join(parts)


def dropbox_ignore(path: Path) -> None:
    """Best-effort: keep a disposable cache dir out of Dropbox sync (runs/ lives in a
    synced folder; a rewritten sqlite + journal on every scan is churn and a
    conflicted-copy risk). Silent when the platform or tool is absent."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["xattr", "-w", "com.dropbox.ignored", "1", str(path)],
                           check=False, capture_output=True, timeout=5)
        elif sys.platform.startswith("linux"):
            subprocess.run(["attr", "-s", "com.dropbox.ignored", "-V", "1", str(path)],
                           check=False, capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass


def dashboard_dir(runs_root: Path) -> Path:
    """Where the dashboard keeps its caches: ``<runs_root>/.dashboard/``, or, when the runs folder cannot be written
    (a published, read-only copy), a folder of its own under the user's cache directory."""
    preferred = Path(runs_root) / ".dashboard"
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        probe = preferred / ".writable"
        probe.touch()
        probe.unlink()
        return preferred
    except OSError:
        import hashlib
        key = hashlib.sha256(str(Path(runs_root).resolve()).encode()).hexdigest()[:16]
        fallback = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "vivarium-dashboard" / key
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


class RegistryCache:
    """Incremental registry over one runs root; ``scan()`` is the only entry point."""

    def __init__(self, runs_root: Path) -> None:
        self.runs_root = Path(runs_root)
        self.db_path = dashboard_dir(self.runs_root) / "registry.sqlite"

    def scan(self, *, rebuild: bool = False) -> list[dict]:
        """Registry rows for every run under the root, recomputing only changed runs.

        ``rebuild=True`` drops the cache first (the recovery path — the cache is
        never repaired, only rebuilt from the streams)."""
        with _cache_lock(self.db_path):
            run_dirs = discover_run_dirs(self.runs_root)
            if rebuild and self.db_path.exists():
                self.db_path.unlink()
            if not run_dirs:
                if self.db_path.exists():
                    self.db_path.unlink()  # nothing left to index
                return []

            if not self.db_path.parent.exists():
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                dropbox_ignore(self.db_path.parent)
            try:
                return self._scan_with_db(run_dirs)
            except sqlite3.OperationalError as exc:
                if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                    raise  # contention is not corruption; never unlink another reader's DB
                self.db_path.unlink(missing_ok=True)
                return self._scan_with_db(run_dirs)
            except sqlite3.DatabaseError:
                # Corrupt/foreign file: disposable by contract — drop and rebuild once.
                self.db_path.unlink(missing_ok=True)
                return self._scan_with_db(run_dirs)

    def _scan_with_db(self, run_dirs: list[Path]) -> list[dict]:
        con = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            con.execute("PRAGMA busy_timeout = 30000")
            if con.execute("PRAGMA user_version").fetchone()[0] != _CACHE_VERSION:
                con.execute("DROP TABLE IF EXISTS runs")  # row shape changed → rebuild
                con.execute(f"PRAGMA user_version = {_CACHE_VERSION}")
            con.execute(_SCHEMA)
            cached = dict(con.execute("SELECT run_dir, fingerprint FROM runs"))
            rows: list[dict] = []
            live = set()
            for rd in run_dirs:
                key, fp = str(rd), fingerprint(rd)
                live.add(key)
                if cached.get(key) == fp:
                    rows.append(json.loads(
                        con.execute("SELECT row_json FROM runs WHERE run_dir = ?", (key,)).fetchone()[0]))
                    continue
                row = run_record(rd)
                row.update(_manifest_pins(rd))
                con.execute("INSERT OR REPLACE INTO runs VALUES (?, ?, ?)",
                            (key, fp, json.dumps(row, sort_keys=True)))
                rows.append(row)
            gone = set(cached) - live
            if gone:
                con.executemany("DELETE FROM runs WHERE run_dir = ?", [(k,) for k in gone])
            con.commit()
        finally:
            con.close()
        rows.sort(key=lambda r: (r.get("experiment_id") or "", r.get("organization_id") or "",
                                 r.get("run_id") or ""))
        return rows
