"""The forum form of the board (October 10, 2026), offline: threads and replies, a one-line notice in the
other agents' mailboxes instead of the text, a paged index, the text only when a lab opens a thread or a
post, every opening recorded, and a length cap that refuses rather than cuts. The flat board is unchanged."""
from __future__ import annotations

import itertools
import asyncio
from types import SimpleNamespace

import pytest

from oaos2.communication import board as B


class _Spine:
    def __init__(self):
        self.events, self._ids = [], itertools.count(1)

    async def emit_event(self, cls, payload=None, **kw):
        eid = f"e{next(self._ids)}"
        self.events.append({"event_class": cls, "event_id": eid, "payload": payload or {}, **kw})
        return eid


@pytest.fixture
def world(monkeypatch):
    delivered: list[tuple[str, str]] = []

    async def deliver(item, target, rs):
        delivered.append((target, item.payload))
        return item.item_id

    monkeypatch.setattr("oaos2.kernel.runtime._deliver", deliver)
    spine = _Spine()
    agents = {a: SimpleNamespace(agent_id=a, retired=False) for a in ("lab_a", "lab_b", "lab_c")}
    rs = SimpleNamespace(agents=agents, spine=spine, kick_scheduler=lambda: None)
    board = B.Board()

    def ctx(agent):
        return SimpleNamespace(agent_id=agent, rs=rs, protocol_state={"board": board})

    return SimpleNamespace(board=board, ctx=ctx, spine=spine, delivered=delivered, rs=rs)


async def _call(fn, ctx, **args):
    return (await fn(args, ctx, turn_id="t", caused_by="c")).text


async def test_a_forum_delivers_notices_and_opens_text_on_request(world):
    world.board.configure({"form": "forum", "post_cap": 2000, "index_page": 2, "thread_page": 2})
    out = await _call(B.start_thread, world.ctx("lab_a"), subject="Variant J8H", text="Should we use J8H? " * 5)
    assert out.startswith("Posted as #1: started thread #1")
    # the others get the subject only
    assert sorted(t for t, _ in world.delivered) == ["lab_b", "lab_c"]
    assert all(p == '[board] lab_a started thread #1 "Variant J8H" (post #1).' for _, p in world.delivered)
    await _call(B.reply, world.ctx("lab_b"), post_id=1, text="No: the regulator excludes it.")
    await _call(B.start_thread, world.ctx("lab_c"), subject="Heat panels", text="I have two spare panels.")
    await _call(B.reply, world.ctx("lab_c"), post_id=2, text="Agreed with lab_b.")
    posted = [e["payload"] for e in world.spine.events if e["event_class"] == "board.posted"]
    assert [(p["seq"], p["thread"], p["reply_to"]) for p in posted] == [(1, 1, None), (2, 1, 1), (3, 3, None), (4, 1, 2)]
    assert posted[3]["subject"] == "Variant J8H" and posted[3]["delivery"] == "notice"
    assert "Agreed with lab_b." in posted[3]["text"]  # the text stays on the trace

    # the index: newest activity first, unread counts per reader, paged
    index = await _call(B.board_index, world.ctx("lab_a"))
    assert index.splitlines()[0].startswith("Board index, page 1 of 1 (2 thread(s), 4 post(s)")
    assert index.splitlines()[1] == '  #1 "Variant J8H" by lab_a: 3 post(s), latest #4 by lab_c; 2 unread'
    assert index.splitlines()[2] == '  #3 "Heat panels" by lab_c: 1 post(s); 1 unread'
    assert "Should we use" not in index

    # read_thread starts at the first unread post and pages
    thread = await _call(B.read_thread, world.ctx("lab_a"), thread_id=1)
    assert "posts #2 to #4" in thread and "No: the regulator excludes it." in thread and "Agreed" in thread
    assert "Should we use" not in thread
    again = await _call(B.read_thread, world.ctx("lab_b"), thread_id=1)  # lab_b has not opened #1
    assert "posts #1 to #2" in again and "1 more: read_thread with thread_id=1, from_post=4." in again
    one = await _call(B.read_post, world.ctx("lab_b"), post_id=3)
    assert one.startswith('[board #3, thread #3 "Heat panels"] lab_c: I have two spare panels.')
    opened = [e["payload"] for e in world.spine.events if e["event_class"] == "board.retrieved"]
    assert [(o["view"], o.get("seqs")) for o in opened] == [("index", []), ("thread", [2, 4]), ("thread", [1, 2]),
                                                           ("post", [3])]
    assert "Heat panels\" by lab_c: 1 post(s); 1 unread" in (await _call(B.board_index, world.ctx("lab_a")))
    await _call(B.read_post, world.ctx("lab_a"), post_id=3)
    assert "unread" not in (await _call(B.board_index, world.ctx("lab_a")))  # everything opened or written


async def test_forum_posts_over_the_cap_are_refused_not_cut(world):
    world.board.configure({"form": "forum", "post_cap": 2000})
    out = await _call(B.start_thread, world.ctx("lab_a"), subject="Long", text="x" * 2001)
    assert out.startswith("Not posted: a post is limited to 2,000 characters and this one has 2,001")
    assert not world.board.posts and not world.delivered
    assert (await _call(B.reply, world.ctx("lab_a"), post_id=9, text="hi")).startswith("Not posted: there is no post #9")
    assert "no thread #5" in await _call(B.read_thread, world.ctx("lab_a"), thread_id=5)


async def test_the_laboratory_topic_and_a_flat_post_open_threads_on_a_forum(world):
    world.board.configure({"form": "forum"})
    await B.open_topic(world.board, world.rs, "laboratory",
                       "[Open topic: collective deliberation about the task] This topic stays open.", world.spine)
    await _call(B.post, world.ctx("lab_b"), text="Panels available. Ask me.")
    assert [(p["subject"], p["thread"]) for p in world.board.posts] == [
        ("Open topic: collective deliberation about the task", 1), ("Panels available", 2)]
    # the laboratory's topic arrives in full (start-of-run material); a lab's post as a notice
    assert world.delivered[0] == ("lab_a", '[board #1, thread #1 "Open topic: collective deliberation about the task"] '
                                           'laboratory: [Open topic: collective deliberation about the task] This topic stays open.')
    assert world.delivered[-1] == ("lab_c", '[board] lab_b started thread #2 "Panels available" (post #2).')
    # read_board on a forum is the index
    assert (await _call(B.read_board, world.ctx("lab_a"))).startswith("Board index")


async def test_the_flat_board_is_unchanged(world):
    await _call(B.post, world.ctx("lab_a"), text="x" * 4500)
    assert world.delivered[0] == ("lab_b", "[board #1] lab_a: " + "x" * 4000)  # full text, cut at 4,000 as before
    payload = world.spine.events[0]["payload"]
    assert set(payload) == {"seq", "text", "recipients"}
    assert (await _call(B.read_board, world.ctx("lab_b"))).startswith("Board:\n[board #1] lab_a: ")


async def test_concurrent_posts_keep_unique_ids_when_the_trace_queue_yields(world):
    world.board.configure({"form": "forum"})
    emit = world.spine.emit_event

    async def delayed_emit(*args, **kwargs):
        await asyncio.sleep(0)  # a full real trace queue also yields to other publishers
        return await emit(*args, **kwargs)

    world.spine.emit_event = delayed_emit
    await asyncio.gather(*(_call(B.start_thread, world.ctx(lab), subject=lab, text="body")
                           for lab in ("lab_a", "lab_b", "lab_c")))
    assert [p["seq"] for p in world.board.posts] == [1, 2, 3]
    assert [p["thread"] for p in world.board.posts] == [1, 2, 3]
    await _call(B.reply, world.ctx("lab_a"), post_id=3, text="reply")
    assert world.board.posts[-1]["thread"] == 3 and world.board.posts[-1]["subject"] == "lab_c"


@pytest.mark.parametrize("settings", [{"form": "threads"}, {"form": "forum", "post_cap": 0},
                                      {"form": "forum", "post_cap": 5000}, {"index_page": -1}])
def test_malformed_settings_are_refused(settings):
    with pytest.raises(ValueError):
        B.Board().configure(settings)
