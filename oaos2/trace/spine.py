"""Provide the run's shared entry point for recording and finalizing events.

start() recovers saved streams and pending events, then starts the writer.
emit_event() validates and queues a new event; emit() queues an existing Event.
finalize() drains pending work, writes a terminal event, runs INV-1 through
INV-5 and the spool check, and returns an InvariantReport. Callers must treat
a failed report as a failed run. The writer alone assigns sequence numbers
and appends the trace. See trace/invariants.py for each check's scope."""

from __future__ import annotations

import asyncio
from pathlib import Path

from oaos2.trace.emit import make_event
from oaos2.trace.invariants import (
    InvariantReport,
    RunFailed,
    causality_ok,
    run_invariants,
)
from oaos2.trace.schema import Event
from oaos2.trace.spool import DurableEventQueue
from oaos2.trace.writer import TraceWriter


class RunSpine:
    def __init__(self, run_dir: Path, run_id: str, max_depth: int = 1000,
                 event_class_registry=None, phase_name_registry=None):
        self.run_dir = Path(run_dir)
        self.run_id = run_id
        self.queue = DurableEventQueue(self.run_dir, max_depth=max_depth)
        self.writer = TraceWriter(self.run_dir, run_id=run_id)
        # Optional composed vocabularies (M0 §5.2): a pack extends the foundation
        # registries via inherits_from and the runner injects the RESOLVED result
        # here — emission validates against the active registry, never a wider one.
        # None = the foundation registry (make_event's defaults).
        self.event_class_registry = event_class_registry
        self.phase_name_registry = phase_name_registry
        self._task: asyncio.Task | None = None
        self._finalized = False
        self._drained = False
        self._terminal_class_written: str | None = None  # "completed" | "failed"
        self._finalize_lock = asyncio.Lock()
        self.report: InvariantReport | None = None

    async def start(self) -> None:
        # Recovery + spool replay happen synchronously before any producer emits,
        # so the writer's appended set and the queue's INV-4 seed are in place.
        self.writer.open_and_recover(self.queue)
        self._task = asyncio.create_task(self.writer.run_loop(self.queue))

    async def emit(self, event: Event) -> str:
        """Enqueue a pre-built event durably; returns its event_id."""
        task = self._task
        if task is None or self._finalize_lock.locked() or self._finalized:
            raise RuntimeError("trace writer is not accepting events")
        if task.done():
            await task  # propagate the original writer failure
            raise RuntimeError("trace writer has stopped")
        if not self.queue.queue.full():
            await self.queue.put_blocking(event)
        else:
            # A full queue must wake its producers if its sole consumer dies.
            pending = asyncio.create_task(self.queue.put_blocking(event))
            try:
                await asyncio.wait({pending, task}, return_when=asyncio.FIRST_COMPLETED)
                if task.done():
                    await task
                    raise RuntimeError("trace writer has stopped")
                await pending
            finally:
                if not pending.done():
                    pending.cancel()
                    try:
                        await pending
                    except asyncio.CancelledError:
                        pass
        return event.event_id

    async def emit_event(self, event_class: str, **kwargs) -> str:
        """Build (registry-validated) + enqueue an event; returns its event_id."""
        if self.event_class_registry is not None:
            kwargs.setdefault("event_class_registry", self.event_class_registry)
        if self.phase_name_registry is not None:
            kwargs.setdefault("phase_name_registry", self.phase_name_registry)
        event = make_event(event_class, self.run_id, **kwargs)
        return await self.emit(event)

    async def finalize(self, reason: str = "completed", detail: dict | None = None) -> InvariantReport:
        """Drain, write the terminal record last, verify invariants, reclaim spool.

        An invariant violation is a **hard error** (DESIGN §6.3): it is recorded
        as a terminal ``run.failed{reason: causality_violation}`` record *and*
        returned as a non-ok :class:`InvariantReport`. Callers MUST treat a
        non-ok report as a failed run — see :class:`RunFailed`, which the
        orchestrator raises so a violation cannot be silently ignored. The report
        is also retained on ``self.report`` for post-hoc inspection.
        """
        # Mark finalization complete only after a durable terminal and the checks.
        # Track completed stages so a failed attempt can resume through abort().
        # The lock prevents concurrent callers from writing duplicate endings.
        async with self._finalize_lock:
            if self._finalized:
                raise RuntimeError("spine already finalized")
            try:
                return await self._finalize_locked(reason, detail)
            except BaseException as exc:
                self._write_failure_marker(exc)  # writer-independent floor
                raise

    async def _finalize_locked(self, reason: str, detail: dict | None) -> InvariantReport:
        # Drain pending events while the writer is alive. Race the queue's join
        # against writer failure; waiting only on join could hang without a reader.
        # Remember the drain attempt so a retry can proceed to the terminal write.
        if not self._drained:
            task = self._task
            try:
                if task is not None and not task.done():
                    join_task = asyncio.ensure_future(self.queue.queue.join())
                    try:
                        await asyncio.wait({join_task, task},
                                           return_when=asyncio.FIRST_COMPLETED)
                    finally:
                        if not join_task.done():
                            join_task.cancel()  # writer died mid-drain
                            try:
                                await join_task
                            except asyncio.CancelledError:
                                pass
                if task is not None and not task.done():
                    await self.queue.signal_shutdown()
                if task is not None:
                    await asyncio.shield(task)  # cancellation must leave shutdown retryable
            finally:
                self._drained = task is None or task.done()
                if self._drained:
                    self._task = None

        # 2. Decide the terminal record from causality observed so far.
        final_reason = reason
        terminal_detail = dict(detail or {})
        if self.writer.violations or not causality_ok(self.run_dir):
            final_reason = "failed"
            terminal_detail.setdefault("reason", "causality_violation")
        elif reason != "completed":
            terminal_detail.setdefault("reason", reason)
        terminal_class = "completed" if final_reason == "completed" else "failed"

        # 3. Write the terminal record last (writer-synthesized; fsync'd last) —
        #    exactly once across attempts, EXCEPT when a retry's decision
        #    contradicts an already-written "completed" terminal (probe finding 3:
        #    an aborted run must never stand recorded as completed): then a
        #    corrective run.failed supersedes it, and INV-5 admits exactly that
        #    shape (a completed terminal followed only by a failed one).
        needs_terminal = (self._terminal_class_written is None
                          or (self._terminal_class_written == "completed"
                              and terminal_class == "failed"))
        if needs_terminal and self.writer.events_handle is None:
            self.writer.open_files()  # a prior attempt already closed the streams
        if self._terminal_class_written is None:
            self.writer.emit_terminal(terminal_class, terminal_detail)
            self._terminal_class_written = terminal_class
        elif self._terminal_class_written == "completed" and terminal_class == "failed":
            terminal_detail.setdefault("supersedes_terminal", "completed")
            self.writer.emit_terminal("failed", terminal_detail)
            self._terminal_class_written = "failed"
        self.writer.close()
        self.queue.close()

        # 4. Full invariant check over the complete archive (includes INV-5:
        #    terminal-last + uniqueness-or-corrective).
        report = run_invariants(self.run_dir, self.queue, self.writer)
        self.report = report
        self._finalized = True
        if report.ok and final_reason == "completed":
            self.queue.reclaim()  # spool no longer needed; everything durably appended
        return report

    def _write_failure_marker(self, exc: BaseException) -> None:
        """Writer-INDEPENDENT floor (probe finding 4): when finalize itself fails,
        record that fact where a broken writer cannot lose it, so recovery and
        archive readers can detect a terminal-less or mis-terminated archive even
        if every retry also fails. Plain os-level append; never raises."""
        try:
            import os
            marker = self.run_dir / "trace" / "FINALIZE_FAILED"
            marker.parent.mkdir(parents=True, exist_ok=True)
            with open(marker, "a", encoding="utf-8") as fh:
                fh.write(f"{type(exc).__name__}: {exc}\n")
                fh.flush()
                os.fsync(fh.fileno())
        except Exception:  # noqa: BLE001 — the floor must never mask the real error
            pass

    def raise_if_invalid(self) -> None:
        """Raise :class:`RunFailed` if the last finalize found a violation.

        The hard-error contract (DESIGN §6.3) as an explicit call: an
        orchestrator that wants a non-ok run to abort loudly (rather than
        inspecting the returned report) calls this right after ``finalize``.
        """
        report = getattr(self, "report", None)
        if report is not None and not report.ok:
            raise RunFailed("; ".join(report.failures))
