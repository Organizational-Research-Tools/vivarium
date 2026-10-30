"""Keep pending events on disk until the trace writer has recorded them.

Each event is written and flushed to trace/spool/spool.log before it enters
the bounded in-memory queue. When the queue is full, producers wait for space;
the queue records this delay as spine.backpressure. Recovery replays saved
events that were not appended before interruption. Successful finalization
removes the spool; it is not reclaimed periodically during a run.

A spool is the temporary disk record used for crash recovery. Its durability
depends on successful filesystem writes and fsync, the request to flush data."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path

from oaos2.trace.schema import Event


def fsync_dir(directory: Path) -> None:
    """fsync the directory fd so a newly-created/renamed dirent is durable (M1 §3.2).

    An fsync of a file alone does not guarantee its directory entry survives a
    crash; the containing directory must be fsync'd too.
    """
    fd = os.open(directory, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


# Sentinel placed on the queue to tell the writer loop to drain and stop.
SHUTDOWN = object()


class DurableEventQueue:
    """Bounded in-memory queue with a write-ahead durable spool (M1 §6)."""

    def __init__(self, run_dir: Path, max_depth: int = 1000):
        self.run_dir = Path(run_dir)
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_depth)
        self.spool_dir = self.run_dir / "trace" / "spool"
        self.spool_dir.mkdir(parents=True, exist_ok=True)
        self.spool_path = self.spool_dir / "spool.log"
        self.spool_handle = open(self.spool_path, "a")
        fsync_dir(self.spool_dir)  # the dirent for spool.log must be durable

        # INV-4 accounting (M1 §3.3, §5).
        self.enqueue_count = 0
        self.backpressure_event_count = 0
        self.recovered_tail_ref: str | None = None

    # -- write-ahead spool -------------------------------------------------- #

    def _spool(self, event: Event) -> None:
        """Append + fsync an enqueue marker before the event is visible (M1 §6)."""
        line = json.dumps({"enqueued": event.event_id, "event": event.to_dict()})
        self.spool_handle.write(line + "\n")
        self.spool_handle.flush()
        os.fsync(self.spool_handle.fileno())

    async def put_blocking(self, event: Event) -> None:
        """Enqueue an event durably; block (never drop) under backpressure.

        Write-ahead to the spool first, then enqueue. If the in-memory queue is
        full, synthesize and enqueue a ``spine.backpressure`` infra event (also
        spooled, so it is durable and INV-4-accountable), then block on the
        original event (M1 §3.3).
        """
        self._spool(event)
        try:
            self.queue.put_nowait(event)
            self.enqueue_count += 1
        except asyncio.QueueFull:
            backpressure = Event(
                event_class="spine.backpressure",
                run_id=event.run_id,
                payload={"queue_depth": self.queue.qsize()},
            )
            self._spool(backpressure)
            await self.queue.put(backpressure)  # waits for space
            self.enqueue_count += 1
            self.backpressure_event_count += 1
            await self.queue.put(event)  # now block on the original
            self.enqueue_count += 1

    async def get(self) -> object:
        return await self.queue.get()

    def qsize(self) -> int:
        return self.queue.qsize()

    async def signal_shutdown(self) -> None:
        await self.queue.put(SHUTDOWN)

    # -- recovery ----------------------------------------------------------- #

    def _entries(self, *, recover_tail: bool = False) -> list[dict]:
        if not self.spool_path.exists():
            return []
        data = self.spool_path.read_bytes()
        lines = data.splitlines(keepends=True)
        entries = []
        offset = 0
        for index, line in enumerate(lines):
            if line.strip():
                try:
                    entry = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    # Repair only an interrupted last append, retaining its bytes.
                    # Interior or newline-terminated corruption still fails loudly.
                    if not recover_tail or index != len(lines) - 1 or line.endswith(b"\n"):
                        raise
                    digest = hashlib.sha256(line).hexdigest()
                    tail = self.spool_dir / f"incomplete-{digest}.bin"
                    with tail.open("wb") as handle:
                        handle.write(line)
                        handle.flush()
                        os.fsync(handle.fileno())
                    fsync_dir(self.spool_dir)
                    with self.spool_path.open("r+b") as handle:
                        handle.truncate(offset)
                        handle.flush()
                        os.fsync(handle.fileno())
                    self.recovered_tail_ref = str(tail.relative_to(self.run_dir))
                    break
                entries.append(entry)
            offset += len(line)
        else:
            if recover_tail and data and not data.endswith(b"\n"):
                self.spool_handle.write("\n")
                self.spool_handle.flush()
                os.fsync(self.spool_handle.fileno())
        return entries

    def replay_unappended(self, writer: "object") -> int:
        """Re-ingest spool entries whose event has not yet been appended (M1 §6).

        Called on restart, *after* the writer has recovered the trace streams (so
        ``writer.appended_ids`` reflects what already landed). Replays in spool
        order, directly into the writer (the sole consumer), and counts each as an
        enqueue for INV-4. An event enqueued just before a crash is therefore
        re-appended exactly once.
        """
        if not self.spool_path.exists():
            return 0
        replayed = 0
        for entry in self._entries(recover_tail=True):
            if entry["enqueued"] in writer.appended_ids:  # type: ignore[attr-defined]
                continue
            event = Event.from_dict(entry["event"])
            writer.ingest(event)  # type: ignore[attr-defined]
            self.enqueue_count += 1
            replayed += 1
        return replayed

    def spooled_event_ids(self) -> set[str]:
        """The set of event_ids ever enqueued (for the cross-crash no-drop check)."""
        return {entry["enqueued"] for entry in self._entries()}

    def close(self) -> None:
        if self.spool_handle:
            self.spool_handle.close()

    def reclaim(self) -> None:
        """Remove the spool after a clean finalize (everything is durably appended)."""
        self.close()
        if self.spool_path.exists():
            self.spool_path.unlink()
