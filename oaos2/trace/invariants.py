"""Check event ordering, dependencies, accounting, and run closure.

INV-1 requires a sequence starting at zero without gaps or collisions. INV-2
rejects cycles and INV-3 requires every predecessor to exist earlier in order;
both include causal links and structural parent_event_id links. INV-4 checks
queue/writer accounting; the separate spool check compares saved event IDs.
INV-5 checks the permitted ending of a nonempty experiment stream, allowing a
final run.failed to correct an earlier run.completed.

index_fingerprint compares the ordered contents of rebuilt SQLite indexes,
not their file bytes: database page layout can differ for equivalent contents.
See the individual checks for scope and empty/missing-stream behavior."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


class RunFailed(Exception):
    """A finalize-time invariant violation; the run is invalid (DESIGN §6.3)."""


@dataclass
class InvariantReport:
    ok: bool = True
    failures: list[str] = field(default_factory=list)

    def fail(self, message: str) -> None:
        self.ok = False
        self.failures.append(message)


def load_all_events(run_dir: Path) -> list[dict]:
    """The total order: the union of both streams, sorted by ``sequence_number``."""
    rows: list[dict] = []
    for name in ("events.jsonl", "infra.jsonl"):
        p = Path(run_dir) / "trace" / name
        if p.exists():
            with open(p) as f:
                rows.extend(json.loads(line) for line in f if line.strip())
    rows.sort(key=lambda e: e["sequence_number"])
    return rows


def check_inv1(events: list[dict], report: InvariantReport) -> None:
    for i, event in enumerate(events):
        if event["sequence_number"] != i:
            report.fail(
                f"INV-1: position {i} has seq={event['sequence_number']} (gap or collision)"
            )
            return


def _ordering_predecessors(event: dict) -> list[str]:
    """Return causal links and the structural parent used for ordering checks.

    Both must precede the child event and neither may introduce a cycle.
    A structural parent groups events; it does not by itself establish a
    causal contribution to the scientific outcome."""
    preds = list(event.get("caused_by_event_ids", []))
    parent = event.get("parent_event_id")
    if parent:
        preds.append(parent)
    return preds


def check_inv2(events: list[dict], report: InvariantReport) -> None:
    parents = {e["event_id"]: _ordering_predecessors(e) for e in events}
    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {nid: WHITE for nid in parents}

    def visit(node: str) -> bool:
        color[node] = GREY
        for p in parents.get(node, ()):  # follow ALL causes
            pc = color.get(p, BLACK)
            if pc == GREY:
                report.fail(f"INV-2: causal cycle through {node} -> {p}")
                return False
            if pc == WHITE and not visit(p):
                return False
        color[node] = BLACK
        return True

    for nid in list(parents):
        if color[nid] == WHITE and not visit(nid):
            return


def check_inv3(events: list[dict], report: InvariantReport) -> None:
    seq_map = {e["event_id"]: e["sequence_number"] for e in events}
    for event in events:
        for cause_id in _ordering_predecessors(event):
            cause_seq = seq_map.get(cause_id)
            if cause_seq is None:
                report.fail(
                    f"INV-3: event {event['event_id']} cites unknown cause {cause_id}"
                )
            elif cause_seq >= event["sequence_number"]:
                report.fail(
                    f"INV-3: cause seq={cause_seq} >= effect seq={event['sequence_number']} "
                    f"(event {event['event_id']})"
                )


def check_inv4(run_dir: Path, queue, writer, report: InvariantReport) -> None:
    """enqueued + writer_synthesized == appended + recovery_tail (M1 §5)."""
    from oaos2.trace.writer import TraceWriter

    appended = TraceWriter._count_lines(
        Path(run_dir) / "trace" / "events.jsonl"
    ) + TraceWriter._count_lines(Path(run_dir) / "trace" / "infra.jsonl")
    lhs = queue.enqueue_count + writer.writer_synthesized
    rhs = appended + writer.recovery_tail_count
    if lhs != rhs:
        report.fail(
            f"INV-4: enqueued={queue.enqueue_count} + synthesized={writer.writer_synthesized} "
            f"!= appended={appended} + recovered={writer.recovery_tail_count} (Δ={lhs - rhs})"
        )


def check_no_drops_via_spool(run_dir: Path, queue, report: InvariantReport) -> None:
    """Cross-crash no-drop: every spooled event_id appears in the appended union.

    This is the robust, set-based no-drop check (M1 §6) — independent of the
    counter identity — used by the fault-injection gate. It tolerates the spool
    having been reclaimed (empty spool ⇒ nothing to check).
    """
    spooled = queue.spooled_event_ids()
    if not spooled:
        return
    appended = {e["event_id"] for e in load_all_events(run_dir)}
    missing = spooled - appended
    if missing:
        report.fail(f"no-drop: {len(missing)} enqueued event(s) never appended: {sorted(missing)[:5]}")


def causality_ok(run_dir: Path) -> bool:
    """INV-2 + INV-3 over disk so far (used to decide the terminal record)."""
    events = load_all_events(run_dir)
    r = InvariantReport()
    check_inv2(events, r)
    check_inv3(events, r)
    return r.ok


_TERMINAL_CLASSES = ("run.completed", "run.failed")


def check_inv5(run_dir: Path, report: InvariantReport) -> None:
    """Check the ending of a nonempty events.jsonl experiment stream.

    The last event must be terminal. Normally there is one terminal event;
    the only permitted pair is run.completed followed by a final run.failed
    that corrects it. Infrastructure events do not determine the run ending.
    A missing or empty experiment stream returns no violation from this check."""
    p = Path(run_dir) / "trace" / "events.jsonl"
    if not p.exists():
        return  # missing stream is INV-1/INV-4's problem, not INV-5's
    with open(p) as f:
        spine_events = [json.loads(line) for line in f if line.strip()]
    spine_events.sort(key=lambda e: e["sequence_number"])
    if not spine_events:
        return  # empty archive is INV-1's problem, not INV-5's
    terminals = [e for e in spine_events if e["event_class"] in _TERMINAL_CLASSES]
    if not terminals:
        report.fail("INV-5: no terminal record (run.completed/run.failed)")
        return
    if spine_events[-1]["event_class"] not in _TERMINAL_CLASSES:
        report.fail(
            f"INV-5: last spine event is {spine_events[-1]['event_class']!r}, "
            "not a terminal record — the terminal must be written last")
    if len(terminals) == 1:
        return
    if (len(terminals) == 2 and terminals[0]["event_class"] == "run.completed"
            and terminals[1]["event_class"] == "run.failed"):
        return  # the one sanctioned corrective supersede
    report.fail(
        f"INV-5: {len(terminals)} terminal records "
        f"({[t['event_class'] for t in terminals]}) — only one terminal, or a "
        "completed superseded by a final failed, is a valid archive ending")


def run_invariants(run_dir: Path, queue, writer) -> InvariantReport:
    """Full finalize check (INV-1…5 + cross-crash no-drop)."""
    report = InvariantReport()
    events = load_all_events(run_dir)
    check_inv1(events, report)
    check_inv2(events, report)
    check_inv3(events, report)
    check_inv4(run_dir, queue, writer, report)
    check_inv5(run_dir, report)
    check_no_drops_via_spool(run_dir, queue, report)
    return report


# --------------------------------------------------------------------------- #
# Index-rebuild equivalence (M1 §8 Q2): logical, not byte-identical.
# --------------------------------------------------------------------------- #


def index_fingerprint(index_path: Path) -> str:
    """Hash a canonical ``SELECT … ORDER BY sequence_number`` over the index."""
    conn = sqlite3.connect(index_path)
    try:
        rows = conn.execute(
            """SELECT sequence_number, event_id, event_class, run_id, agent_id,
                      turn_id, phase_class, phase_name, audience, channel
               FROM events ORDER BY sequence_number"""
        ).fetchall()
        edges = conn.execute(
            "SELECT child_event_id, parent_event_id FROM causal_edges "
            "ORDER BY child_event_id, parent_event_id"
        ).fetchall()
    finally:
        conn.close()
    h = hashlib.sha256()
    h.update(json.dumps(rows, sort_keys=True).encode())
    h.update(json.dumps(edges, sort_keys=True).encode())
    return h.hexdigest()
