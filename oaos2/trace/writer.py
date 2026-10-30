"""Append events through one host-side writer per run.

The writer assigns sequence_number across events.jsonl and infra.jsonl. It waits
until required predecessors are written before appending a dependent event, and
accounts for queued, synthesized, and recovered entries. Routing uses each
event's actual audience/channel fields. Synchronous ingest, append, and recovery
methods are wrapped by an asynchronous dequeue loop. See trace/invariants.py
for final checks and trace/spool.py for durable queuing."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path

from oaos2.trace import index_db
from oaos2.trace.routing import Stream, assert_routing_guardrail, route
from oaos2.trace.schema import Event
from oaos2.trace.spool import SHUTDOWN, DurableEventQueue, fsync_dir

# Events the WRITER itself creates (never enqueued by a producer). Used to seed
# INV-4 counters on recovery so the no-drop identity holds across restarts (§5).
WRITER_SYNTHESIZED_CLASSES = frozenset(
    {
        "run.recovered",
        "writer.restarted",
        "spine.causality_cycle",
        "spine.reorder_flush",
        "spine.queue_depth",
        "spine.write_latency",
        "index.rebuilt",
        # The terminal record is written *by the writer* as the last fsync'd line
        # (DESIGN §6.4), so for INV-4 accounting it is writer-synthesized, not an
        # enqueued producer event.
        "run.completed",
        "run.failed",
    }
)

TERMINAL_CLASSES = frozenset({"run.completed", "run.failed"})


class TraceWriter:
    def __init__(self, run_dir: Path, run_id: str = "", observability_interval: int = 1000):
        self.run_dir = Path(run_dir)
        self.run_id = run_id
        # Self-observability cadence (M1 §8 Q5, nice-to-have): emit
        # ``spine.queue_depth``/``spine.write_latency`` every N appended producer
        # events. Defaults high so short traces emit none; set 0 to disable.
        self.observability_interval = observability_interval
        self._processed_since_obs = 0
        self._enqueue_seed = 0  # INV-4 seed applied to the queue on recovery (§5)
        self.events_file = self.run_dir / "trace" / "events.jsonl"
        self.infra_file = self.run_dir / "trace" / "infra.jsonl"
        self.index_file = self.run_dir / "trace" / "index.sqlite"

        self.current_sequence = 0
        self.event_id_to_sequence: dict[str, int] = {}
        self.appended_ids: set[str] = set()  # for spool replay + cross-crash no-drop
        self.events_handle = None
        self.infra_handle = None
        self.index_conn: sqlite3.Connection | None = None

        # INV-3 prevention: hold an event until all its causes are appended.
        self.pending: list[Event] = []
        self.max_pending = 8192  # > queue depth; overflow ⇒ dangling/cyclic cause

        # INV-4 counters (per stream).
        self.appended_events = 0
        self.appended_infra = 0
        self.writer_synthesized = 0
        self.recovery_tail_count = 0

        # Anomalies found at append time (fatal at finalize).
        self.violations: list[dict] = []

        self.is_healthy = True
        self.last_write_timestamp = time.time()

    # -- lifecycle ---------------------------------------------------------- #

    def open_files(self) -> None:
        self.events_file.parent.mkdir(parents=True, exist_ok=True)
        self.events_handle = open(self.events_file, "a")
        self.infra_handle = open(self.infra_file, "a")
        self.index_conn = sqlite3.connect(self.index_file)
        self._init_index_schema()

    def open_and_recover(self, queue: DurableEventQueue | None = None) -> None:
        """Open streams, recover any unclean state, replay un-appended spool entries.

        Seeds the queue's INV-4 ``enqueue_count`` (so the no-drop identity holds
        across this restart, §5) *before* replay, then replays. On an unclean
        restart (or any spool replay), announce ``writer.restarted`` so blocked
        producers re-check and unblock (M1 §8 Q4).
        """
        self.open_files()
        unclean = self._recover_if_needed()
        replayed = 0
        if queue is not None:
            queue.enqueue_count += self._enqueue_seed  # seed BEFORE replay (§5)
            replayed = queue.replay_unappended(self)
        recovered_tail = queue.recovered_tail_ref if queue is not None else None
        if unclean or replayed or recovered_tail:
            self.writer_synthesized += 1
            self._append(
                Event(
                    event_class="writer.restarted",
                    run_id=self.run_id,
                    payload={"resumed_at_seq": self.current_sequence, "replayed": replayed,
                             **({"incomplete_spool_tail": recovered_tail} if recovered_tail else {})},
                )
            )

    async def run_loop(self, queue: DurableEventQueue) -> None:
        """Async dequeue loop. ``open_and_recover`` must be called first (sync).

        Each dequeue is matched with ``task_done`` so the orchestrator can await
        ``queue.join()`` to know every enqueued event has been processed.
        """
        try:
            while True:
                item = await queue.get()
                if item is SHUTDOWN:
                    queue.queue.task_done()
                    break
                self.ingest(item)  # type: ignore[arg-type]
                self.last_write_timestamp = time.time()
                self._maybe_emit_observability(queue)
                queue.queue.task_done()
        except Exception:
            self.is_healthy = False  # runner supervision restarts the writer
            raise
        finally:
            self._flush_pending(reason="shutdown")

    def _maybe_emit_observability(self, queue: DurableEventQueue) -> None:
        """Every ``observability_interval`` ingests, append writer-synthesized
        ``spine.queue_depth`` + ``spine.write_latency`` infra events (M1 §8 Q5)."""
        if not self.observability_interval:
            return
        self._processed_since_obs += 1
        if self._processed_since_obs < self.observability_interval:
            return
        self._processed_since_obs = 0
        depth = queue.queue.qsize()
        for cls, payload in (
            ("spine.queue_depth", {"queue_depth": depth}),
            ("spine.write_latency", {"last_write_age_s": time.time() - self.last_write_timestamp}),
        ):
            self.writer_synthesized += 1
            self._append(Event(event_class=cls, run_id=self.run_id, payload=payload))

    def emit_terminal(self, reason: str, detail: dict | None = None) -> None:
        """Write the terminal record (``run.completed``/``run.failed``) last (§6.4).

        Writer-synthesized for INV-4 accounting; routed to the spine (researcher/
        formal). ``caused_by`` is empty (a run-level marker), so it appends
        immediately rather than buffering.
        """
        from oaos2.trace.emit import make_event

        cls = "run.completed" if reason == "completed" else "run.failed"
        ev = make_event(cls, self.run_id, payload=detail or {})
        self.writer_synthesized += 1
        self.ingest(ev)

    # -- reorder buffer (INV-3 prevention) ---------------------------------- #

    def ingest(self, event: Event) -> None:
        """Append ``event`` once ALL its causes are on disk; else buffer it (§4)."""
        if self._cause_satisfied(event):
            self._append(event)
            self._drain_pending()
        else:
            self.pending.append(event)
            if len(self.pending) > self.max_pending:
                self._flush_one_stuck(reason="buffer_overflow")

    @staticmethod
    def _ordering_predecessors(event: Event) -> list[str]:
        """Causes that must be on disk before ``event`` (DESIGN §6.3): the
        multi-parent ``caused_by_event_ids`` plus the single structural
        ``parent_event_id`` nesting edge, so ``seq(parent) < seq(child)`` is
        structural for nesting too, not only for causal edges."""
        preds = list(event.caused_by_event_ids)
        if event.parent_event_id:
            preds.append(event.parent_event_id)
        return preds

    def _cause_satisfied(self, event: Event) -> bool:
        return all(
            c in self.event_id_to_sequence for c in self._ordering_predecessors(event)
        )

    def _drain_pending(self) -> None:
        """Cascade: appending an event may complete others. Preserve arrival order."""
        progress = True
        while progress:
            progress = False
            ready = [ev for ev in self.pending if self._cause_satisfied(ev)]
            if ready:
                ready_obj_ids = {id(ev) for ev in ready}
                self.pending = [ev for ev in self.pending if id(ev) not in ready_obj_ids]
                for ev in ready:
                    self._append(ev)
                progress = True

    def _flush_one_stuck(self, reason: str) -> None:
        """Overflow valve: release only the single oldest stuck event (bounded damage)."""
        ev = self.pending.pop(0)
        self.writer_synthesized += 1
        self._append(
            Event(
                event_class="spine.reorder_flush",
                run_id=ev.run_id,
                payload={
                    "reason": reason,
                    "stuck_event_id": ev.event_id,
                    "missing": [
                        c
                        for c in self._ordering_predecessors(ev)
                        if c not in self.event_id_to_sequence
                    ],
                },
            )
        )
        self._append(ev)
        self._drain_pending()

    def _flush_pending(self, reason: str) -> None:
        """Shutdown only: whatever is still buffered is genuinely unsatisfiable."""
        if not self.pending:
            return
        self.writer_synthesized += 1
        self._append(
            Event(
                event_class="spine.reorder_flush",
                run_id="",
                payload={"reason": reason, "count": len(self.pending)},
            )
        )
        stranded, self.pending = self.pending, []
        for ev in stranded:
            self._append(ev)

    # -- append ------------------------------------------------------------- #

    def _append(self, event: Event) -> None:
        """Assign seq, check INV-2/INV-3, route, fsync, index."""
        event.sequence_number = self.current_sequence
        self.current_sequence += 1
        self._check_causal_dag(event)
        self._write_event(event)
        self._fsync(event)
        self._update_index(event)
        self.event_id_to_sequence[event.event_id] = event.sequence_number
        self.appended_ids.add(event.event_id)

    def _write_event(self, event: Event) -> None:
        stream = route(event)
        assert_routing_guardrail(event, stream)
        handle = self.events_handle if stream is Stream.EVENTS else self.infra_handle
        handle.write(json.dumps(asdict(event)) + "\n")
        handle.flush()
        if stream is Stream.EVENTS:
            self.appended_events += 1
        else:
            self.appended_infra += 1

    def _fsync(self, event: Event) -> None:
        stream = route(event)
        handle = self.events_handle if stream is Stream.EVENTS else self.infra_handle
        os.fsync(handle.fileno())

    def _check_causal_dag(self, event: Event) -> None:
        """INV-2/INV-3 at append time (cheap, because the reorder buffer guarantees
        causes are already appended for the common path; a miss here means the
        event was released by the overflow/shutdown flush — a cycle/dangling cause)."""
        if event.event_id in self.event_id_to_sequence:
            self._note_violation("duplicate_event_id", event, detail=event.event_id)
            return
        for c in self._ordering_predecessors(event):
            cause_seq = self.event_id_to_sequence.get(c)
            if cause_seq is None or cause_seq >= event.sequence_number:
                self._note_violation("causality_out_of_order", event, detail=c)

    def _note_violation(self, kind: str, event: Event, detail: str) -> None:
        """Record an INV-2/INV-3 anomaly to infra. Non-fatal here; fatal at finalize."""
        self.violations.append(
            {"kind": kind, "event_id": event.event_id, "detail": detail}
        )
        rec = Event(
            event_class="spine.causality_cycle",
            run_id=event.run_id,
            payload={"kind": kind, "event_id": event.event_id, "detail": detail},
        )
        rec.sequence_number = self.current_sequence
        self.current_sequence += 1
        self.writer_synthesized += 1
        self.infra_handle.write(json.dumps(asdict(rec)) + "\n")
        self.infra_handle.flush()
        os.fsync(self.infra_handle.fileno())
        self.appended_infra += 1
        self.appended_ids.add(rec.event_id)
        self.event_id_to_sequence[rec.event_id] = rec.sequence_number

    # -- index (delegates to index_db so online + rebuild are identical) ----- #

    def _init_index_schema(self) -> None:
        index_db.init_schema(self.index_conn)

    def _update_index(self, event: Event) -> None:
        problem = index_db.update(self.index_conn, asdict(event))
        if problem == "missing_paused_turn_id":
            # The chat.requested payload contract (M0 §3) was violated. We've
            # already assigned a seq; record it (non-fatal here, surfaced as a
            # protocol concern). Avoid re-noting if this *is* a violation event.
            if event.event_class != "spine.causality_cycle":
                self._note_violation("missing_paused_turn_id", event, detail=event.event_id)

    # -- recovery ----------------------------------------------------------- #

    def _recover_if_needed(self) -> bool:
        """Recover BOTH streams; rebuild the cause map + index on any unclean restart.

        Returns True iff the restart was unclean (torn tail, missing terminal
        record, or index/log divergence). Index rebuild is unconditional on any
        unclean restart — never gated on ``truncated`` alone (M1 §4).
        """
        truncated = 0
        max_seq = -1
        self.event_id_to_sequence = {}
        self.appended_ids = set()
        synthesized_on_disk = 0

        for path in (self.events_file, self.infra_file):
            if not path.exists():
                continue
            with open(path, "r") as f:
                lines = f.readlines()
            if not lines:
                continue
            try:
                json.loads(lines[-1])
            except json.JSONDecodeError:
                with open(path, "w") as f:
                    f.writelines(lines[:-1])
                    f.flush()
                    os.fsync(f.fileno())
                fsync_dir(path.parent)
                lines = lines[:-1]
                truncated += 1
            for line in lines:
                if not line.strip():
                    continue
                rec = json.loads(line)
                self.event_id_to_sequence[rec["event_id"]] = rec["sequence_number"]
                self.appended_ids.add(rec["event_id"])
                max_seq = max(max_seq, rec["sequence_number"])
                if rec["event_class"] in WRITER_SYNTHESIZED_CLASSES:
                    synthesized_on_disk += 1

        self.current_sequence = max_seq + 1
        self.appended_events = self._count_lines(self.events_file)
        self.appended_infra = self._count_lines(self.infra_file)
        self.recovery_tail_count = truncated

        # Seed INV-4 counters so the no-drop identity holds across this restart
        # (M1 §5 derivation): writer_synthesized := prior synthesized lines; the
        # queue's enqueue_count is seeded to (prior enqueued-appended + torn tail).
        # We expose the enqueue seed for the orchestrator to apply to the queue.
        self.writer_synthesized = synthesized_on_disk
        prior_appended = self.appended_events + self.appended_infra
        self._enqueue_seed = (prior_appended - synthesized_on_disk) + truncated

        nothing_on_disk = max_seq < 0
        unclean = (not nothing_on_disk) and (
            truncated > 0
            or not self._terminal_record_present()
            or self._index_diverges_from_log()
        )
        if unclean:
            self._rebuild_index_from_disk()
            self.writer_synthesized += 1  # run.recovered is writer-created
            self._append(
                Event(
                    event_class="run.recovered",
                    run_id="",
                    payload={
                        "reason": "interrupted",
                        "recovered": True,
                        "streams_truncated": truncated,
                    },
                )
            )
        return unclean

    def _terminal_record_present(self) -> bool:
        """True iff a clean shutdown wrote a terminal record as the last spine line."""
        if not self.events_file.exists():
            return False
        last_class = None
        with open(self.events_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    last_class = json.loads(line)["event_class"]
                except json.JSONDecodeError:
                    return False
        return last_class in TERMINAL_CLASSES

    def _index_diverges_from_log(self) -> bool:
        """True if the index's max sequence_number trails the log's (clean-tail crash)."""
        if not self.index_file.exists():
            return True
        try:
            conn = sqlite3.connect(self.index_file)
            row = conn.execute("SELECT MAX(sequence_number) FROM events").fetchone()
            conn.close()
        except sqlite3.Error:
            return True
        indexed_max = row[0] if row and row[0] is not None else -1
        return indexed_max != self.current_sequence - 1

    def _rebuild_index_from_disk(self) -> None:
        """Reconstruct index.sqlite from BOTH streams (unified seq order, §4).

        Uses the shared ``index_db.rebuild`` so the recovery rebuild is byte-for-
        byte the same logic as the CI equivalence gate, then reopens the fresh
        index for continued online updates and records ``index.rebuilt``.
        """
        if self.index_conn:
            self.index_conn.close()
        index_db.rebuild(self.run_dir, self.index_file)
        self.index_conn = sqlite3.connect(self.index_file)
        rows = self._count_lines(self.events_file) + self._count_lines(self.infra_file)
        self.writer_synthesized += 1
        self._append(Event(event_class="index.rebuilt", run_id=self.run_id, payload={"rows": rows}))

    # -- helpers ------------------------------------------------------------ #

    @staticmethod
    def _count_lines(path: Path) -> int:
        if not path.exists():
            return 0
        with open(path, "r") as f:
            return sum(1 for line in f if line.strip())

    def close(self) -> None:
        if self.events_handle:
            self.events_handle.close()
            self.events_handle = None
        if self.infra_handle:
            self.infra_handle.close()
            self.infra_handle = None
        if self.index_conn:
            self.index_conn.close()
            self.index_conn = None
