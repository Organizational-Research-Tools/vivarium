"""A voluntary public board and private notes, as registered task actions (M8 §7).

The board is the one channel every agent in an organization can read; a note goes
to one named role. Both are agent-initiated: until this module, a message could only
be produced by a protocol relay, never by an agent's own decision, so nothing about
voluntary exchange was observable. Study PC1 is the named research use; any pack can
declare these actions in its manifest (``module: oaos2.communication.board``).

What is recorded, and kept apart (design §5): delivery (``board.posted`` with the
recipients, ``message.sent`` for a note), retrieval (``board.retrieved``,
``notes.retrieved`` with the range returned), and rendering into an agent's next turn
(the protocol's inbound hook). None of these is recognition; that is coded later from
what the agent does. Delivered items also wake an agent that is waiting, through the
protocol-supplied ``on_delivered`` hook, because a wait ends when a result or a
message arrives.

The board's state is a run-scoped object attached by the coordination protocol to
every role's tool context (``protocol_state["board"]``); its history is reproducible
from the ``board.posted`` events and is never written anywhere else.

The forum form (October 10, 2026; PC1, the PI): with ``Board.forum`` a post opens a thread
(``start_thread``, with a subject) or answers a post (``reply``); the other agents' mailboxes
get a one-line notice, not the text (the laboratory's own posts still arrive in full);
``board_index`` lists the threads a page at a time,
newest activity first, and ``read_thread`` / ``read_post`` return the text. In a Claude
Haiku 4.5 run of the supplier form every post reached every lab in full, one lab's prompt
passed the provider's 200,000-token limit and the run ended. Every opening is recorded on
``board.retrieved`` (``view``: index, thread or post; ``seqs``: the posts returned), so
which posts a lab opened is on the trace. Without ``forum`` nothing changes.
"""

from __future__ import annotations

import json

import asyncio
from dataclasses import dataclass, field

from oaos2.agents.tools import ToolResult
from oaos2.communication.mailbox import MailboxItem
from oaos2.communication.messages import MessageIntent
from oaos2.ulid import new_ulid

_TEXT_CAP = 4000  # verbatim on the trace, like message.sent's payload_text cap


@dataclass
class Board:
    """Run-scoped board log and per-agent note history."""

    posts: list[dict] = field(default_factory=list)  # {seq, author, text, event_id}
    notes: dict[str, list[dict]] = field(default_factory=dict)  # recipient -> [{seq, author, text, event_id}]
    note_counter: int = 0
    # Optional protocol hook awaited after a delivery: (agent_id, cause_event_id) -> None.
    # The repair pool uses it to wake a waiting agent (M8 §8).
    on_delivered: object | None = None
    # The forum form (module docstring); set from a preset's ``board`` settings by ``configure``.
    forum: bool = False
    post_cap: int = _TEXT_CAP  # characters; a longer forum post is refused, not cut
    index_page: int = 15  # threads per index page
    thread_page: int = 6  # posts per read_thread call
    opened: dict[str, set] = field(default_factory=dict)  # agent -> post seqs it has opened or written
    publish_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def attach(self, tool_ctx) -> None:
        tool_ctx.protocol_state["board"] = self

    def configure(self, settings: dict | None) -> None:
        """Apply a preset's ``board`` settings: ``{form: forum, post_cap, index_page, thread_page}``."""
        settings = dict(settings or {})
        unknown = set(settings) - {"form", "post_cap", "index_page", "thread_page"}
        if unknown:  # a misspelled setting would otherwise pass and change nothing
            raise ValueError(f"unknown board setting(s) {sorted(unknown)}; the board accepts form, post_cap, "
                             "index_page and thread_page")
        form = str(settings.get("form") or "flat")
        if form not in ("flat", "forum"):
            raise ValueError(f"board form must be 'flat' or 'forum', not {form!r}")
        self.forum = form == "forum"
        for key in ("post_cap", "index_page", "thread_page"):
            if key in settings:
                value = int(settings[key])
                if value < 1 or (key == "post_cap" and value > _TEXT_CAP):
                    raise ValueError(f"board {key} must be positive" + (f" and at most {_TEXT_CAP}"
                                                                        if key == "post_cap" else ""))
                setattr(self, key, value)

    def threads(self) -> list[list[dict]]:
        """The threads, each its posts in order, newest activity first."""
        by_thread: dict[int, list[dict]] = {}
        for p in self.posts:
            by_thread.setdefault(p.get("thread") or p["seq"], []).append(p)
        return sorted(by_thread.values(), key=lambda t: t[-1]["seq"], reverse=True)

    def post_by_seq(self, seq: int) -> dict | None:
        return self.posts[seq - 1] if 1 <= seq <= len(self.posts) else None


def _board(ctx) -> Board:
    board = ctx.protocol_state.get("board")
    if board is None:
        raise RuntimeError("board action used without a board attached by the procedure")
    return board


def _render_post(post: dict) -> str:
    if post.get("subject") is not None:  # a forum post
        where = (f"thread #{post['thread']} \"{post['subject']}\"" if post["thread"] == post["seq"] else
                 f"reply in thread #{post['thread']} \"{post['subject']}\"" + (
                     f", to #{post['reply_to']}" if post.get("reply_to") not in (None, post["thread"]) else ""))
        return f"[board #{post['seq']}, {where}] {post['author']}: {post['text']}"
    return f"[board #{post['seq']}] {post['author']}: {post['text']}"


def _notice(post: dict) -> str:
    """What a forum post puts in the other agents' mailboxes: one line, without the text."""
    if post["thread"] == post["seq"]:
        return f"[board] {post['author']} started thread #{post['thread']} \"{post['subject']}\" (post #{post['seq']})."
    return (f"[board] {post['author']} replied in thread #{post['thread']} \"{post['subject']}\" "
            f"(post #{post['seq']}).")


def _subject_from(text: str) -> str:
    """A subject for a post that has none (the laboratory's open topic, or a flat post on a forum
    board): a leading bracketed title, else the first sentence, at most 80 characters."""
    text = " ".join(text.split())
    if text.startswith("[") and "]" in text[:120]:
        return text[1:text.index("]")].strip()[:80]
    first = text.split(". ")[0]
    return first if len(first) <= 80 else first[:77].rstrip() + "..."


async def _publish(board: Board, rs, spine, *, author: str, text: str, recipients: list[str],
                   agent_id: str | None = None, turn_id: str | None = None, caused_by: str | None = None,
                   subject: str | None = None, reply_to: int | None = None, wake: bool = True) -> dict:
    """Record a post once and deliver it: in full on a flat board, as a notice on a forum."""
    # Emission can yield when the trace queue is full. Reserve and append together,
    # or concurrent publishers can acquire the same post/thread ID.
    async with board.publish_lock:
        seq = len(board.posts) + 1
        payload = {"seq": seq, "text": text[:_TEXT_CAP], "recipients": recipients}
        if agent_id is None:
            payload["author"] = author
        if board.forum:
            parent = board.post_by_seq(reply_to) if reply_to else None
            thread = (parent.get("thread") or parent["seq"]) if parent else seq
            subject = (board.post_by_seq(thread) or {}).get("subject") if parent else (subject or _subject_from(text))
            # The laboratory's opening topic is start-of-run material, delivered in full.
            payload.update({"subject": subject, "thread": thread, "reply_to": reply_to,
                            "delivery": "full" if agent_id is None else "notice"})
        kwargs = {"agent_id": agent_id, "turn_id": turn_id, "caused_by": caused_by} if agent_id else {}
        posted = await spine.emit_event("board.posted", payload=payload, **kwargs)
        record = {"seq": seq, "author": author, "text": text[:_TEXT_CAP], "event_id": posted}
        if board.forum:
            record.update({"subject": payload["subject"], "thread": payload["thread"], "reply_to": reply_to})
            board.opened.setdefault(author, set()).add(seq)
        board.posts.append(record)
    from oaos2.kernel.runtime import _deliver
    for target in recipients:
        await _deliver(MailboxItem(item_id=new_ulid(), kind="board_post",
                                   payload=_notice(record) if payload.get("delivery") == "notice" else _render_post(record),
                                   source_event_id=posted), target, rs)
        if wake:
            await _wake(board, target, posted)
    return record


async def _wake(board: Board, agent_id: str, cause: str | None) -> None:
    hook = board.on_delivered
    if hook is not None:
        await hook(agent_id, cause)


def _recipients(ctx) -> list[str]:
    return sorted(a.agent_id for a in ctx.rs.agents.values() if a.agent_id != ctx.agent_id and not a.retired)


def _too_long(board: Board, text: str) -> ToolResult | None:
    if board.forum and len(text) > board.post_cap:
        return ToolResult(text=f"Not posted: a post is limited to {board.post_cap:,} characters and this one has "
                               f"{len(text):,}. Shorten it, or split it into a post and replies.")
    return None


def _posted_text(record: dict, n: int) -> str:
    if record.get("subject") is None:
        return f"Posted to the board as #{record['seq']}; delivered to {n} other agent(s)."
    where = (f"started thread #{record['thread']}" if record["thread"] == record["seq"]
             else f"replied in thread #{record['thread']}")
    return f"Posted as #{record['seq']}: {where} \"{record['subject']}\"; {n} other agent(s) notified."


async def post(args: dict, ctx, *, turn_id: str, caused_by: str) -> ToolResult:
    """Post to the board: recorded once with every recipient, delivered to each other
    active agent's mailbox, rendered into their next turn by the protocol's inbound
    hook. Delivery is not reading; reading is not recognition. On a forum board a post
    starts a thread whose subject is taken from the text."""
    board = _board(ctx)
    text = str(args.get("text") or "").strip()
    if not text:
        return ToolResult(text="A post needs a text.")
    if (refusal := _too_long(board, text)) is not None:
        return refusal
    recipients = _recipients(ctx)
    record = await _publish(board, ctx.rs, ctx.rs.spine, author=ctx.agent_id, text=text, recipients=recipients,
                            agent_id=ctx.agent_id, turn_id=turn_id, caused_by=caused_by)
    ctx.rs.kick_scheduler()
    return ToolResult(text=_posted_text(record, len(recipients)))


async def start_thread(args: dict, ctx, *, turn_id: str, caused_by: str) -> ToolResult:
    """Forum: open a thread with a subject and a first post; the others get a notice."""
    board = _board(ctx)
    subject = " ".join(str(args.get("subject") or "").split())
    text = str(args.get("text") or "").strip()
    if not subject or not text:
        return ToolResult(text="A thread needs a subject and a text.")
    if len(subject) > 80:
        return ToolResult(text=f"Not posted: a subject is limited to 80 characters and this one has {len(subject)}.")
    if (refusal := _too_long(board, text)) is not None:
        return refusal
    recipients = _recipients(ctx)
    record = await _publish(board, ctx.rs, ctx.rs.spine, author=ctx.agent_id, text=text, recipients=recipients,
                            agent_id=ctx.agent_id, turn_id=turn_id, caused_by=caused_by, subject=subject)
    ctx.rs.kick_scheduler()
    return ToolResult(text=_posted_text(record, len(recipients)))


async def reply(args: dict, ctx, *, turn_id: str, caused_by: str) -> ToolResult:
    """Forum: answer a post; the reply joins that post's thread and the others get a notice."""
    board = _board(ctx)
    try:
        to = int(str(args.get("post_id") or "").lstrip("#"))
    except (TypeError, ValueError):
        to = 0
    text = str(args.get("text") or "").strip()
    if board.post_by_seq(to) is None:
        return ToolResult(text=f"Not posted: there is no post #{args.get('post_id')}; the board has "
                               f"{len(board.posts)} post(s).")
    if not text:
        return ToolResult(text="A reply needs a text.")
    if (refusal := _too_long(board, text)) is not None:
        return refusal
    recipients = _recipients(ctx)
    record = await _publish(board, ctx.rs, ctx.rs.spine, author=ctx.agent_id, text=text, recipients=recipients,
                            agent_id=ctx.agent_id, turn_id=turn_id, caused_by=caused_by, reply_to=to)
    ctx.rs.kick_scheduler()
    return ToolResult(text=_posted_text(record, len(recipients)))


async def open_topic(board: Board, rs, author: str, text: str, spine) -> str:
    """A post made by the laboratory rather than an agent (September 25, 2026: the PI's open
    topic for collective deliberation). Recorded as ``board.posted`` with no agent and the
    author in the payload, delivered to every active agent's mailbox like any post."""
    recipients = sorted(a.agent_id for a in rs.agents.values() if not a.retired)
    record = await _publish(board, rs, spine, author=author, text=text, recipients=recipients, wake=False)
    return record["event_id"]


def _int_arg(args: dict, key: str) -> int:
    try:
        return int(str(args.get(key) or 0).lstrip("#"))
    except (TypeError, ValueError):
        return 0


async def read_board(args: dict, ctx, *, turn_id: str, caused_by: str) -> ToolResult:
    """Return the board's history from a sequence number; records the range returned.
    On a forum board, the index of threads instead (``board_index``)."""
    board = _board(ctx)
    if board.forum:
        return await board_index(args, ctx, turn_id=turn_id, caused_by=caused_by)
    since = _int_arg(args, "since_seq")
    selected = [p for p in board.posts if p["seq"] > since]
    await ctx.rs.spine.emit_event(
        "board.retrieved", agent_id=ctx.agent_id, turn_id=turn_id, caused_by=caused_by,
        payload={"since_seq": since,
                 "from_seq": selected[0]["seq"] if selected else None,
                 "to_seq": selected[-1]["seq"] if selected else None,
                 "count": len(selected), "board_length": len(board.posts)})
    if not selected:
        return ToolResult(text="The board has no posts" + (f" after #{since}." if since else "."))
    return ToolResult(text="Board:\n" + "\n".join(_render_post(p) for p in selected))


async def board_index(args: dict, ctx, *, turn_id: str, caused_by: str) -> ToolResult:
    """Forum: the threads, a page at a time, newest activity first, without their text."""
    board = _board(ctx)
    threads = board.threads()
    pages = max(1, -(-len(threads) // board.index_page))
    page = min(max(1, _int_arg(args, "page") or 1), pages)
    shown = threads[(page - 1) * board.index_page: page * board.index_page]
    seen = board.opened.get(ctx.agent_id, set())
    await ctx.rs.spine.emit_event(
        "board.retrieved", agent_id=ctx.agent_id, turn_id=turn_id, caused_by=caused_by,
        payload={"view": "index", "page": page, "pages": pages, "threads": [t[0]["seq"] for t in shown],
                 "count": 0, "seqs": [], "from_seq": None, "to_seq": None, "board_length": len(board.posts)})
    if not threads:
        return ToolResult(text="The board has no threads yet.")
    lines = [f"Board index, page {page} of {pages} ({len(threads)} thread(s), {len(board.posts)} post(s); "
             "newest activity first). Open a thread with read_thread, one post with read_post."]
    for t in shown:
        first, last = t[0], t[-1]
        unread = sum(1 for p in t if p["seq"] not in seen)
        lines.append(f"  #{first['seq']} \"{first['subject']}\" by {first['author']}: {len(t)} post(s)"
                     + (f", latest #{last['seq']} by {last['author']}" if len(t) > 1 else "")
                     + (f"; {unread} unread" if unread else ""))
    return ToolResult(text="\n".join(lines))


async def _record_opened(board: Board, ctx, turn_id: str, caused_by: str, view: str, shown: list[dict],
                         **extra) -> None:
    board.opened.setdefault(ctx.agent_id, set()).update(p["seq"] for p in shown)
    seqs = [p["seq"] for p in shown]
    await ctx.rs.spine.emit_event(
        "board.retrieved", agent_id=ctx.agent_id, turn_id=turn_id, caused_by=caused_by,
        payload={"view": view, "seqs": seqs, "count": len(seqs), "from_seq": seqs[0] if seqs else None,
                 "to_seq": seqs[-1] if seqs else None, "board_length": len(board.posts), **extra})


async def read_thread(args: dict, ctx, *, turn_id: str, caused_by: str) -> ToolResult:
    """Forum: a thread's posts in full, a few at a time, from its first unread post (or
    ``from_post``)."""
    board = _board(ctx)
    thread_id = _int_arg(args, "thread_id")
    first = board.post_by_seq(thread_id)
    if first is None or first.get("thread") != thread_id:
        return ToolResult(text=f"There is no thread #{args.get('thread_id')}; board_index lists the threads.")
    posts = [p for p in board.posts if p.get("thread") == thread_id]
    seen = board.opened.get(ctx.agent_id, set())
    start = _int_arg(args, "from_post")
    if not start:
        start = next((p["seq"] for p in posts if p["seq"] not in seen), posts[0]["seq"])
    rest = [p for p in posts if p["seq"] >= start]
    shown = rest[:board.thread_page]
    await _record_opened(board, ctx, turn_id, caused_by, "thread", shown, thread=thread_id)
    head = (f"Thread #{thread_id} \"{first['subject']}\", {len(posts)} post(s); "
            + (f"posts #{shown[0]['seq']} to #{shown[-1]['seq']}:" if shown else f"no post from #{start}."))
    more = rest[board.thread_page:]
    tail = ([f"{len(more)} more: read_thread with thread_id={thread_id}, from_post={more[0]['seq']}."]
            if more else [])
    return ToolResult(text="\n".join([head, *(_render_post(p) for p in shown), *tail]))


async def read_post(args: dict, ctx, *, turn_id: str, caused_by: str) -> ToolResult:
    """Forum: one post in full."""
    board = _board(ctx)
    p = board.post_by_seq(_int_arg(args, "post_id"))
    if p is None:
        return ToolResult(text=f"There is no post #{args.get('post_id')}; the board has {len(board.posts)} post(s).")
    await _record_opened(board, ctx, turn_id, caused_by, "post", [p], thread=p.get("thread"))
    return ToolResult(text=_render_post(p))



def recipient_names(raw) -> list[str]:
    """Recipient names from a tool argument: a list, a comma-separated string, or a list the model
    wrote as a JSON string (`'["lab_a"]'`, `'"firm_c"'`), which the agents sometimes do (October 12,
    2026). Quotes and brackets around a name are not part of it; order is kept, repeats dropped."""
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = None
            if isinstance(parsed, list):
                raw = parsed
        if isinstance(raw, str):
            raw = text.split(",")
    names = (str(x).strip().strip("[]").strip().strip("\"'").strip() for x in (raw or []))
    return list(dict.fromkeys(n for n in names if n))


async def send_note(args: dict, ctx, *, turn_id: str, caused_by: str) -> ToolResult:
    """Send a private note to one named role through the router (its channel and
    kind checks apply). A note to a role that does not exist is refused; the refusal
    is on the call record, since arguments are recorded on ``tool.called``."""
    board = _board(ctx)
    to_roles = recipient_names(args.get("to_roles") or args.get("to_role") or "")
    text = str(args.get("text") or "").strip()
    if not text:
        return ToolResult(text="A note needs a text.")
    if not to_roles:
        return ToolResult(text="A note needs a recipient (to_role, or several as to_roles).")
    rs = ctx.rs
    # One note to several agents (September 25, 2026): the labs sent the same text to four
    # partners in four calls. Each delivery is its own message.sent, as before.
    refused, delivered_to = [], []
    from oaos2.kernel.runtime import _send_message
    sender = rs.agents[ctx.agent_id]
    body = f"[note from {ctx.agent_id}] {text[:_TEXT_CAP]}"
    for to_role in to_roles:
        if to_role not in rs.agents:
            known = sorted(a for a in rs.agents if a != ctx.agent_id)
            refused.append(f"no agent named {to_role!r} (agents you can write to: {', '.join(known) or 'none'})")
            continue
        if to_role == ctx.agent_id:
            refused.append("you cannot send a note to yourself")
            continue
        if rs.agents[to_role].retired:
            refused.append(f"{to_role} has retired from the run")
            continue
        delivered = await _send_message(
            MessageIntent(to_agent=to_role, payload=body, kind="note"), sender, rs, caused_by)
        if not delivered:
            refused.append(f"{to_role}: the organization's channels do not permit it (recorded)")
            continue
        board.note_counter += 1
        sent_event = delivered[0][1]
        board.notes.setdefault(to_role, []).append(
            {"seq": board.note_counter, "author": ctx.agent_id, "text": text[:_TEXT_CAP],
             "event_id": sent_event})
        await _wake(board, to_role, sent_event)
        delivered_to.append(to_role)
    rs.kick_scheduler()
    if not delivered_to:
        return ToolResult(text="Note refused: " + "; ".join(refused) + ".")
    out = f"Note delivered to {', '.join(delivered_to)}."
    if refused:
        out += " Not delivered, refused: " + "; ".join(refused) + "."
    return ToolResult(text=out)


async def read_notes(args: dict, ctx, *, turn_id: str, caused_by: str) -> ToolResult:
    """Return the notes this agent has received, in order; records the retrieval."""
    board = _board(ctx)
    try:
        since = int(args.get("since_seq") or 0)
    except (TypeError, ValueError):
        since = 0
    mine = [n for n in board.notes.get(ctx.agent_id, []) if n["seq"] > since]
    await ctx.rs.spine.emit_event(
        "notes.retrieved", agent_id=ctx.agent_id, turn_id=turn_id, caused_by=caused_by,
        payload={"since_seq": since, "count": len(mine),
                 "from_seq": mine[0]["seq"] if mine else None,
                 "to_seq": mine[-1]["seq"] if mine else None})
    if not mine:
        return ToolResult(text="You have received no notes" + (f" after #{since}." if since else ".")
                               + " New notes reach you automatically at your next turn.")
    return ToolResult(text="Notes:\n" + "\n".join(
        f"[note {n['seq']} from {n['author']}] {n['text']}" for n in mine))
