"""Writer failures and interrupted spool appends must not strand intact evidence."""
import asyncio
import json

import pytest

from oaos2.trace.emit import make_event
from oaos2.trace.invariants import load_all_events
from oaos2.trace.spine import RunSpine
from oaos2.trace.spool import DurableEventQueue


async def test_writer_death_releases_blocked_producer_and_full_queue_finalize(tmp_path):
    spine = RunSpine(tmp_path, "r", max_depth=1)
    fail = asyncio.Event()

    async def dying_writer(queue):
        await fail.wait()
        raise OSError("test writer failure")

    spine.writer.run_loop = dying_writer
    await spine.start()
    await spine.emit_event("run.started")
    producer = asyncio.create_task(spine.emit_event("turn.started"))
    await asyncio.sleep(0.01)
    assert not producer.done()
    fail.set()
    with pytest.raises(OSError, match="test writer failure"):
        await asyncio.wait_for(producer, 1)
    with pytest.raises(OSError):
        await asyncio.wait_for(spine.emit_event("turn.started"), 1)
    with pytest.raises(OSError):
        await asyncio.wait_for(spine.finalize("failed"), 1)
    assert (tmp_path / "trace/FINALIZE_FAILED").exists()
    report = await asyncio.wait_for(spine.finalize("failed"), 1)
    assert not report.ok  # unappended events remain in the spool for recovery
    assert (tmp_path / "trace/spool/spool.log").exists()


@pytest.mark.parametrize("tail", [b'{"enqueued": "unfinished', b'{"text":"\xe2'])
async def test_torn_spool_preserves_and_replays_complete_prefix(tmp_path, tail):
    queue = DurableEventQueue(tmp_path)
    event = make_event("run.started", "r")
    queue._spool(event)
    queue.close()
    with queue.spool_path.open("ab") as handle:
        handle.write(tail)
    spine = RunSpine(tmp_path, "r")
    await spine.start()
    await spine.emit_event("turn.started", caused_by=event.event_id)
    report = await spine.finalize("completed")
    assert report.ok, report.failures
    events = load_all_events(tmp_path)
    assert sum(e["event_id"] == event.event_id for e in events) == 1
    restart = next(e for e in events if e["event_class"] == "writer.restarted")
    assert (tmp_path / restart["payload"]["incomplete_spool_tail"]).read_bytes() == tail


async def test_interior_spool_corruption_is_not_silently_dropped(tmp_path):
    queue = DurableEventQueue(tmp_path)
    queue.close()
    original = b'{invalid}\n' + json.dumps({"enqueued": "later"}).encode()
    queue.spool_path.write_bytes(original)
    spine = RunSpine(tmp_path, "r")
    try:
        with pytest.raises(ValueError):
            await spine.start()
        assert queue.spool_path.read_bytes() == original
    finally:
        spine.writer.close()
        spine.queue.close()


async def test_cancelled_finalize_retries_without_closing_a_live_writer(tmp_path):
    spine = RunSpine(tmp_path, "r")
    release = asyncio.Event()
    real_loop = spine.writer.run_loop

    async def waiting_writer(queue):
        await release.wait()
        await real_loop(queue)

    spine.writer.run_loop = waiting_writer
    await spine.start()
    await spine.emit_event("run.started")
    finalizing = asyncio.create_task(spine.finalize("completed"))
    await asyncio.sleep(0.01)
    finalizing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await finalizing
    assert not spine._drained and spine._task is not None and not spine._task.done()
    release.set()
    report = await asyncio.wait_for(spine.finalize("failed"), 1)
    assert report.ok, report.failures
    assert spine._task is None
