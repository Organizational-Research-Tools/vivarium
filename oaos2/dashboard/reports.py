"""Load saved task reports or cache newly rendered reports for the dashboard.

An existing report under a run's derived/ directory takes precedence. This store
does not check that file against the current renderer or overwrite it. If the
file is absent, render from saved evidence and cache the result in
<runs_root>/.dashboard/reports.sqlite. That cache's key includes the run evidence
and analysis-code identity, so code changes invalidate cached renderings.

The cache can be rebuilt. A saved report can still reflect older analysis code;
its precedence must not be mistaken for a guarantee of current scoring."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from oaos2.archive.renderers import (
    derived_renderer_for,
    load_pack_report_file,
    render_pack_report,
    task_pack_id_of,
)
from oaos2.dashboard.cache import _cache_lock, dashboard_dir, dropbox_ignore, fingerprint

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    run_dir     TEXT PRIMARY KEY,
    key         TEXT NOT NULL,
    identity    TEXT,
    report_json TEXT NOT NULL
)
"""


class ReportStore:
    def __init__(self, runs_root: Path) -> None:
        self.runs_root = Path(runs_root)
        self.db_path = dashboard_dir(self.runs_root) / "reports.sqlite"

    def get(self, run_dir: Path, events: list[dict] | None = None) -> dict:
        """``{"report", "source", "identity", "filename", "error"}`` for one run —
        ``source`` is ``"file"`` (finalize-time), ``"store"`` (rendered earlier at
        this identity), ``"rendered"`` (rendered now and stored), ``"error"``, or
        ``None`` when the pack ships no report."""
        run_dir = Path(run_dir)
        renderer = derived_renderer_for(task_pack_id_of(run_dir))
        if renderer is None:
            return {"report": None, "source": None, "identity": None,
                    "filename": None, "error": None}
        from_file = load_pack_report_file(run_dir, renderer)
        saved = {"report": from_file, "source": "file", "identity": None,
                 "filename": renderer.filename, "error": None}
        missing = [k for k in renderer.expects if not isinstance(from_file, dict) or k not in from_file]
        if from_file is not None and not missing:
            return saved
        # No saved report, or one that predates part of the current analysis (the pack's
        # declared ``expects``): render into this cache. The saved file is never rewritten;
        # if the pack refuses to render (materials changed), the saved report is shown.
        key = fingerprint(run_dir)
        hit = self._lookup(run_dir, key)
        if hit is not None:
            out = {"report": hit, "source": "store", "identity": renderer.identity,
                   "filename": renderer.filename, "error": None}
        else:
            if events is None:  # only a render needs the stream; a store hit never parses it
                from oaos2.archive.transcript import events_in_order
                events = events_in_order(run_dir)
            out = render_pack_report(run_dir, events, renderer)
            if out["report"] is not None:
                self._put(run_dir, key, renderer.identity, out["report"])
        if from_file is not None:
            if out["report"] is None:
                return {**saved, "stale_keys": missing}
            out = {**out, "superseded_file": renderer.filename, "stale_keys": missing}
        return out

    # --- sqlite ------------------------------------------------------------ #

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            dropbox_ignore(self.db_path.parent)
        con = sqlite3.connect(self.db_path, timeout=30.0)
        con.execute("PRAGMA busy_timeout = 30000")
        con.execute(_SCHEMA)
        return con

    def _lookup(self, run_dir: Path, key: str) -> dict | None:
        with _cache_lock(self.db_path):
            try:
                con = self._connect()
                try:
                    row = con.execute("SELECT key, report_json FROM reports WHERE run_dir = ?",
                                      (str(run_dir.resolve()),)).fetchone()
                finally:
                    con.close()
            except sqlite3.DatabaseError:
                self.db_path.unlink(missing_ok=True)  # disposable: drop and rebuild
                return None
        if row is None or row[0] != key:
            return None
        try:
            return json.loads(row[1])
        except ValueError:
            return None

    def _put(self, run_dir: Path, key: str, identity: str, report: dict) -> None:
        with _cache_lock(self.db_path):
            try:
                con = self._connect()
                try:
                    con.execute("INSERT OR REPLACE INTO reports VALUES (?, ?, ?, ?)",
                                (str(run_dir.resolve()), key, identity,
                                 json.dumps(report, sort_keys=True)))
                    con.commit()
                finally:
                    con.close()
            except sqlite3.DatabaseError:
                self.db_path.unlink(missing_ok=True)
