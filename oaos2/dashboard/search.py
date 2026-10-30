"""Cross-run full-text search (DASHBOARD.md §4.13) — a disposable FTS index.

What the reader actually greps for: what was filed, said, thought, and received.
The index holds, per run, one document per filing (the broadcast collapsed to its
formalized ref), each reasoning step, each volley and message, each captured
submission, and each correspondence letter — keyed to the event or file so a hit
opens the exact place.  Built lazily per run on the trace, indexed files, and extractor identity under
``runs/.dashboard/search.sqlite``; dropped and rebuilt like every other cache.
Scope is required (a lineage or an experiment) so a first search never indexes
the whole archive.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from oaos2.archive.clock import day_index
from oaos2.dashboard.cache import _cache_lock, _stat_part, dashboard_dir, dropbox_ignore, fingerprint

_SCHEMA = """
CREATE TABLE IF NOT EXISTS indexed (run_dir TEXT PRIMARY KEY, fingerprint TEXT NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS docs USING fts5(
    run_ref UNINDEXED, run_dir UNINDEXED, event_id UNINDEXED, kind UNINDEXED,
    role UNINDEXED, day UNINDEXED, path UNINDEXED, text, tokenize='unicode61');
"""


def _docs_for(run_dir: Path, run_ref: str, events: list[dict]) -> list[tuple]:
    days = day_index(events)
    out: list[tuple] = []
    seen_refs: set = set()
    for e in events:
        cls = e.get("event_class")
        p = e.get("payload") or {}
        eid, role, day = e.get("event_id"), e.get("agent_id"), days.get(e.get("event_id"))
        if cls == "handoff":
            ref = (p.get("handoff_delta") or {}).get("formalized_payload_ref")
            key = (p.get("from_agent"), ref)
            if ref and key in seen_refs:
                continue
            seen_refs.add(key)
            text = p.get("payload_text") or ""
            if text:
                out.append((run_ref, str(run_dir), eid, "filing", p.get("from_agent") or role, day, ref, text))
        elif cls == "reasoning.step":
            text = "\n".join(x for x in (p.get("narration"), p.get("thinking")) if x)
            if text:
                out.append((run_ref, str(run_dir), eid, "thinking", role, day, None, text))
        elif cls == "conversation.volley":
            if p.get("text"):
                out.append((run_ref, str(run_dir), eid, "volley", p.get("speaker") or role, day, None, p["text"]))
        elif cls == "message.sent":
            text = p.get("payload_text") or p.get("text") or ""
            if text:
                out.append((run_ref, str(run_dir), eid, "message", role, day, None, text))
        elif cls == "environment.event":
            ee = p.get("environment_event") or {}
            pl = ee.get("payload") if isinstance(ee.get("payload"), dict) else {}
            if pl.get("text"):
                out.append((run_ref, str(run_dir), eid, "notice", ee.get("target_role_id") or role, day,
                            ee.get("packet_id"), f"{pl.get('notice_id') or ''} {pl.get('case_id') or ''}\n{pl['text']}"))
    for base in ("captured/submitted", "submitted"):
        d = run_dir / base
        if d.is_dir():
            for f in sorted(d.glob("*.json")):
                try:
                    out.append((run_ref, str(run_dir), None, "submitted", None, None,
                                f"{base}/{f.name}", f.read_text(errors="replace")))
                except OSError:
                    continue
            break
    for f in sorted((run_dir / "captured" / "agents").glob("*/correspondence/*.json")):
        try:
            out.append((run_ref, str(run_dir), None, "letter", f.parent.parent.name, None,
                        str(f.relative_to(run_dir)), f.read_text(errors="replace")))
        except OSError:
            continue
    return out


def search_fingerprint(run_dir: Path) -> str:
    """Invalidate search when any indexed file or the extraction code changes.

    Registry dependencies alone omit correspondence and submissions for packs
    without derived reports. Include each file, not just its parent directory:
    editing an existing file does not necessarily change the directory's mtime.
    """
    parts = [fingerprint(run_dir), hashlib.sha256(Path(__file__).read_bytes()).hexdigest()]
    for base in ("captured/submitted", "submitted"):
        directory = run_dir / base
        parts.append(_stat_part(directory, base))
        for path in sorted(directory.glob("*.json")):
            parts.append(_stat_part(path, str(path.relative_to(run_dir))))
    for path in sorted((run_dir / "captured" / "agents").glob("*/correspondence/*.json")):
        parts.append(_stat_part(path, str(path.relative_to(run_dir))))
    return "|".join(parts)


class SearchIndex:
    def __init__(self, runs_root: Path) -> None:
        self.runs_root = Path(runs_root)
        self.db_path = dashboard_dir(self.runs_root) / "search.sqlite"

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            dropbox_ignore(self.db_path.parent)
        con = sqlite3.connect(self.db_path, timeout=30.0)
        con.execute("PRAGMA busy_timeout = 30000")
        con.executescript(_SCHEMA)
        return con

    def ensure(self, rows: list[dict], load_events) -> dict:
        """Index (or re-index) every run in ``rows`` whose fingerprint changed.
        Returns ``{"indexed": n, "reused": n}``."""
        indexed = reused = 0
        with _cache_lock(self.db_path):
            try:
                con = self._connect()
            except sqlite3.DatabaseError:
                self.db_path.unlink(missing_ok=True)
                con = self._connect()
            try:
                have = dict(con.execute("SELECT run_dir, fingerprint FROM indexed"))
                for r in rows:
                    run_dir = Path(r["run_dir"])
                    fp = search_fingerprint(run_dir)
                    if have.get(str(run_dir)) == fp:
                        reused += 1
                        continue
                    docs = _docs_for(run_dir, r["run_ref"], load_events(run_dir))
                    con.execute("DELETE FROM docs WHERE run_dir = ?", (str(run_dir),))
                    con.executemany("INSERT INTO docs VALUES (?, ?, ?, ?, ?, ?, ?, ?)", docs)
                    con.execute("INSERT OR REPLACE INTO indexed VALUES (?, ?)", (str(run_dir), fp))
                    indexed += 1
                con.commit()
            finally:
                con.close()
        return {"indexed": indexed, "reused": reused}

    def query(self, q: str, run_dirs: list[str], *, limit: int = 200) -> list[dict]:
        if not q.strip() or not run_dirs:
            return []
        with _cache_lock(self.db_path):
            con = self._connect()
            try:
                placeholders = ",".join("?" for _ in run_dirs)
                try:
                    cur = con.execute(
                        f"SELECT run_ref, event_id, kind, role, day, path, "
                        f"snippet(docs, 7, '[', ']', '…', 18) FROM docs "
                        f"WHERE docs MATCH ? AND run_dir IN ({placeholders}) "
                        f"ORDER BY rank LIMIT ?", (q, *run_dirs, limit))
                    rows = cur.fetchall()
                except sqlite3.OperationalError as exc:  # a bad FTS query, not a bug
                    return [{"error": str(exc)}]
            finally:
                con.close()
        return [{"run_ref": r[0], "event_id": r[1], "kind": r[2], "role": r[3], "day": r[4],
                 "path": r[5], "snippet": r[6]} for r in rows]
