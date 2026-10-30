"""Build and update a searchable SQLite index of both event streams.

The writer uses the same schema and update rules as rebuild(). The index can be
recreated from events ordered by sequence_number; it is not an independent
record of the run. Rebuilding does not append log events. Compare logical rows,
not SQLite file bytes, when checking equivalence. See trace/invariants.py."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS events (
            sequence_number INTEGER PRIMARY KEY,
            event_id TEXT UNIQUE,
            event_class TEXT,
            run_id TEXT,
            agent_id TEXT,
            turn_id TEXT,
            phase_class TEXT,
            phase_name TEXT,
            audience TEXT,
            channel TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS causal_edges (
            child_event_id TEXT,
            parent_event_id TEXT,
            PRIMARY KEY (child_event_id, parent_event_id)
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_edge_child ON causal_edges(child_event_id)")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS paused_turns (
            paused_turn_id TEXT PRIMARY KEY,
            parent_turn_id TEXT,
            paused_at_seq INTEGER,
            resolved_at_seq INTEGER
        )"""
    )
    conn.commit()


def update(conn: sqlite3.Connection, event: dict) -> str | None:
    """Index one event (passed as its serialized dict). Returns a problem note or None.

    The ``chat.requested`` payload contract (M0 §3) requires ``paused_turn_id``;
    a missing key is reported back so the caller can record a protocol violation.
    """
    problem: str | None = None
    conn.execute(
        """INSERT OR REPLACE INTO events
           (sequence_number, event_id, event_class, run_id, agent_id, turn_id,
            phase_class, phase_name, audience, channel)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event["sequence_number"],
            event["event_id"],
            event["event_class"],
            event.get("run_id"),
            event.get("agent_id"),
            event.get("turn_id"),
            event.get("phase_class"),
            event.get("phase_name"),
            event.get("audience"),
            event.get("channel"),
        ),
    )
    # The causal-edge graph spans the multi-parent ``caused_by_event_ids`` plus
    # the single structural ``parent_event_id`` nesting edge (DESIGN §6.3), so
    # the index — and the rebuild fingerprint over it — reflect both.
    edge_parents = list(event.get("caused_by_event_ids", []))
    structural_parent = event.get("parent_event_id")
    if structural_parent:
        edge_parents.append(structural_parent)
    for parent in edge_parents:
        conn.execute(
            "INSERT OR IGNORE INTO causal_edges (child_event_id, parent_event_id) VALUES (?, ?)",
            (event["event_id"], parent),
        )
    payload = event.get("payload", {}) or {}
    if event["event_class"] == "chat.requested":
        paused_turn_id = payload.get("paused_turn_id")
        if paused_turn_id is None:
            problem = "missing_paused_turn_id"
        else:
            conn.execute(
                """INSERT OR REPLACE INTO paused_turns
                   (paused_turn_id, parent_turn_id, paused_at_seq) VALUES (?, ?, ?)""",
                (paused_turn_id, event.get("turn_id"), event["sequence_number"]),
            )
    if event["event_class"] == "agent.resumed":
        paused_turn_id = payload.get("paused_turn_id")
        if paused_turn_id is not None:
            conn.execute(
                "UPDATE paused_turns SET resolved_at_seq = ? WHERE paused_turn_id = ?",
                (event["sequence_number"], paused_turn_id),
            )
    conn.commit()
    return problem


def _load_unified(run_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for name in ("events.jsonl", "infra.jsonl"):
        p = Path(run_dir) / "trace" / name
        if p.exists():
            with open(p) as f:
                rows.extend(json.loads(line) for line in f if line.strip())
    rows.sort(key=lambda e: e["sequence_number"])
    return rows


def rebuild(run_dir: Path, target_path: Path | None = None) -> Path:
    """Reconstruct the index from both streams (unified seq order); no log writes."""
    target = Path(target_path) if target_path else Path(run_dir) / "trace" / "index.sqlite"
    if target.exists():
        target.unlink()
    conn = sqlite3.connect(target)
    try:
        init_schema(conn)
        for event in _load_unified(run_dir):
            update(conn, event)
    finally:
        conn.close()
    return target
