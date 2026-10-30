"""The live view (DASHBOARD.md §4.2f): follow a run while it is being written.

Two readers. ``tail_events`` reads only the bytes appended to the event streams since
the last poll, so following a long run does not reparse a stream of tens of
megabytes every few seconds; a line is taken only once its newline has been
written, and a stream that shrank or was replaced is read again from the start.
``live_state`` turns the events read so far into what the page shows: where each
agent is, which declared group it belongs to, who dealt with whom within and
across groups, and the story items after the reader's last position.

Everything is read, nothing is written. "Working", "waiting", and "retired" name
the last recorded lifecycle event for an agent; they say nothing about what the
model is doing between events. Groups are read from declared role settings (the
role packet or the attention scope in the organization preset); the platform has
no separate workgroup declaration, and a grouping is a reading aid, not a
treatment the run assigned.
"""

from __future__ import annotations

import bisect
import json
import threading
import time
from collections import OrderedDict
from pathlib import Path

from oaos2.dashboard.organization import BOARD, graph, interaction_counts
from oaos2.dashboard.store import is_audit_class

_STREAMS = ("trace/events.jsonl", "trace/infra.jsonl")
_TAILS = 8  # a reader follows a few runs at once; each tail holds its events
_TERMINAL = ("run.completed", "run.failed", "run.deadlock_timeout")
GROUP_BYS = ("auto", "packet", "attention", "none")
FEED_FIRST = 300  # items sent on the first poll; older ones stay in the Story view
RECENT = 40  # an edge is highlighted when one of its acts is this close to the end
POLL_MS = 3000


class _Tail:
    def __init__(self) -> None:
        self.offsets: dict[str, tuple[int, int]] = {}  # stream → (inode, byte offset)
        self.events: list[dict] = []
        self.keys: list[int] = []  # sequence numbers, parallel to events
        self.version = 0  # bumps whenever events change, for memoizing derived state
        self.lock = threading.RLock()  # read() restarts itself after a reset

    def _reset(self) -> None:
        self.offsets.clear()
        self.events.clear()
        self.keys.clear()

    def read(self, run_dir: Path) -> list[dict]:
        with self.lock:
            for rel in _STREAMS:
                path = run_dir / rel
                try:
                    st = path.stat()
                except OSError:
                    continue
                inode, offset = self.offsets.get(rel, (st.st_ino, 0))
                if inode != st.st_ino or st.st_size < offset:
                    self._reset()  # the stream was replaced or cut: read everything again
                    return self.read(run_dir)
                if st.st_size == offset:
                    continue
                with open(path, "rb") as f:
                    f.seek(offset)
                    chunk = f.read(st.st_size - offset)
                end = chunk.rfind(b"\n")
                if end < 0:
                    continue  # a line is being written; take it on the next poll
                for line in chunk[: end + 1].splitlines():
                    if not line.strip():
                        continue
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue  # a damaged line stays visible in the Trace view
                    seq = e.get("sequence_number")
                    seq = seq if isinstance(seq, int) else -1
                    i = bisect.bisect_right(self.keys, seq)
                    self.keys.insert(i, seq)
                    self.events.insert(i, e)
                self.offsets[rel] = (st.st_ino, offset + end + 1)
                self.version += 1
            return self.events


_tails: OrderedDict[str, _Tail] = OrderedDict()
_tails_lock = threading.Lock()


def tail_events(run_dir: Path) -> tuple[list[dict], int]:
    """Events read so far in writer order, and a version that changes when they do."""
    key = str(Path(run_dir).resolve())
    with _tails_lock:
        tail = _tails.get(key)
        if tail is None:
            tail = _tails[key] = _Tail()
        _tails.move_to_end(key)
        while len(_tails) > _TAILS:
            _tails.popitem(last=False)
    events = tail.read(Path(run_dir))
    return events, tail.version


def is_unfinished(run_dir: Path, *, idle_after_s: float, now: float | None = None) -> bool:
    """Whether a run may still be written: not finalized (no ``run_status.json``), a
    non-empty stream with no terminal event near its end, and a record that moved
    within ``idle_after_s``. Only the streams' last bytes are read, so the run rail
    can ask this on every page without reparsing a long run."""
    run_dir = Path(run_dir)
    if (run_dir / "run_status.json").exists():
        return False
    # An ABANDONED.json note beside the trace (never inside it) records a run stopped before it could write
    # a closing event, with when and why; such a run is not live (September 26, 2026).
    if (run_dir / "ABANDONED.json").exists():
        return False
    newest, size = 0.0, 0
    for rel in _STREAMS:
        path = run_dir / rel
        try:
            st = path.stat()
        except OSError:
            continue
        newest, size = max(newest, st.st_mtime), size + st.st_size
        with open(path, "rb") as f:
            f.seek(max(0, st.st_size - 65536))
            tail = f.read()
        if any(f'"{cls}"'.encode() in tail for cls in _TERMINAL):
            return False
    if not size:
        return False
    return ((time.time() if now is None else now) - newest) <= idle_after_s


# --- groups ------------------------------------------------------------------ #

def _group_of(role: dict, by: str) -> str | None:
    if by == "packet":
        return role.get("role_packet")
    if by == "attention":
        scope = role.get("attention")
        return str(scope).split("/", 1)[0] if scope else None
    return None


def groups(agents: list[str], roles: dict[str, dict], by: str) -> tuple[str, dict[str, str]]:
    """``(grouping used, {agent: group})``. ``auto`` takes the first declared setting
    that divides the organization into at least two groups, one with several members;
    otherwise everyone is in one group. Agents the preset does not declare (a platform
    coordinator) keep their own name as their group."""
    def split(key: str) -> dict[str, str]:
        return {a: (_group_of(roles[a], key) or a) if a in roles else a for a in agents}

    if by == "auto":
        for key in ("attention", "packet"):
            m = split(key)
            sizes = [list(m.values()).count(g) for g in set(m.values())]
            if len(sizes) >= 2 and max(sizes) >= 2:
                return key, m
        return "none", {a: "everyone" for a in agents}
    if by in ("packet", "attention"):
        return by, split(by)
    return "none", {a: "everyone" for a in agents}


# --- agent state ------------------------------------------------------------- #

def _agent_rows(events: list[dict], agents: list[str]) -> dict[str, dict]:
    rows = {a: {"agent": a, "state": "not started", "last_seq": None, "last_ts": None,
                "doing": "", "posts": 0, "notes": 0, "submissions": 0, "milestones": 0, "calls": 0,
                "cost_usd": 0.0, "problems": 0} for a in agents}
    for e in events:
        a = e.get("agent_id")
        if a not in rows:
            continue
        r, cls, p = rows[a], e.get("event_class") or "", e.get("payload") or {}
        r["last_seq"], r["last_ts"] = e.get("sequence_number"), e.get("timestamp")
        if r["state"] in ("retired", "failed"):
            pass  # a retired or failed agent does not come back; later events are cleanup
        elif cls in ("agent.launched", "turn.started", "agent.woken", "agent.resumed"):
            r["state"] = "working"
        elif cls == "agent.waiting":
            r["state"] = "waiting"
        elif cls == "turn.completed":
            r["state"] = "between turns"
        elif cls == "turn.paused":
            r["state"] = "paused"
        elif cls in ("agent.retired", "agent.failed"):
            r["state"] = "retired" if cls == "agent.retired" else "failed"
        if cls == "tool.called":
            r["doing"] = f"called {p.get('tool_name') or '?'}"
        elif cls == "board.posted":
            r["posts"] += 1
            r["doing"] = "posted to the board"
        elif cls == "message.sent" and p.get("kind") == "note":
            r["notes"] += 1
            r["doing"] = f"sent a note to {p.get('to')}"
        elif cls == "state.committed":
            r["submissions"] += 1
            r["doing"] = "submitted"
        elif cls == "model.responded":
            r["calls"] += 1
        elif cls == "cost.recorded":
            r["cost_usd"] += p.get("cost_usd", 0.0) or 0.0
        elif is_audit_class(cls) and e.get("audience") != "infrastructure":
            r["problems"] += 1
    for r in rows.values():
        r["cost_usd"] = round(r["cost_usd"], 4)
    return rows


def _flows(counts: dict, member: dict[str, str]) -> list[dict]:
    """Directed acts between groups (posts to the board excluded: they go to everyone)."""
    out: dict[tuple[str, str], int] = {}
    for (a, b), kinds in counts.items():
        if b == BOARD or a not in member or b not in member:
            continue
        key = (member[a], member[b])
        out[key] = out.get(key, 0) + sum(kinds.values())
    return [{"from": g1, "to": g2, "n": n, "within": g1 == g2}
            for (g1, g2), n in sorted(out.items())]


def live_state(run_dir: Path, events: list[dict], *, roles: dict[str, dict],
               exchanges: list[dict], by: str = "auto", recent: int = RECENT,
               milestones: list[dict] = ()) -> dict:
    """What the live page shows besides the feed. Nothing here depends on the time
    of reading, so it can be kept until the streams change; ``live_clock`` adds the
    elapsed times."""
    agents: list[str] = []
    for e in events:
        a = e.get("agent_id")
        if a and a not in agents and a != "coordination":
            agents.append(a)
    for a in roles:
        if a not in agents:
            agents.append(a)
    used, member = groups(agents, roles, by)
    rows = _agent_rows(events, agents)
    for m in milestones:  # the task's own turning points by this agent (a report, a concern)
        if m.get("from") in rows:
            rows[m["from"]]["milestones"] += 1
    grouped: dict[str, list[dict]] = {}
    for a in agents:
        grouped.setdefault(member[a], []).append(rows[a])
    last = events[-1] if events else {}
    last_seq = last.get("sequence_number") if events else -1
    g = graph(events, exchanges, agents)
    # An edge is "recent" when one of its acts is among the last `recent` positions.
    cutoff = (last_seq or 0) - recent
    fresh = interaction_counts([e for e in events if (e.get("sequence_number") or 0) > cutoff],
                               [x for x in exchanges if (x.get("seq") or 0) > cutoff], agents)
    for edge in g["edges"]:
        edge["recent"] = (edge["from"], edge["to"]) in fresh
    ended = next((e.get("event_class") for e in reversed(events)
                  if e.get("event_class") in _TERMINAL), None)
    if ended is None and (Path(run_dir) / "run_status.json").exists():
        ended = "run_status.json"
    return {
        "n_events": len(events), "last_seq": last_seq, "ended": ended,
        "last_ts": last.get("timestamp"),
        "cost_usd": round(sum(r["cost_usd"] for r in rows.values()), 4),
        "group_by": used, "groups": [{"name": k, "agents": v} for k, v in grouped.items()],
        "member": member, "flows": _flows(interaction_counts(events, exchanges, agents), member),
        "graph": g, "agents": agents, "standings": standings(events, pack_of(run_dir)),
    }


# A task pack's live standings panel (who holds which credits, who would succeed now), registered by the pack's
# archive-side readers module (``oaos2.tasks.plugins.<pack>.derived``, imported on demand): the engine names no task.
_STANDINGS: dict = {}


def register_standings(pack_id: str, panel) -> None:
    """``panel(events) -> dict | None``: the pack's standings for the live page, None for a run without them."""
    _STANDINGS[pack_id] = panel


def pack_of(run_dir: Path) -> str | None:
    """The run's task pack: the manifest's ``task_pack_id``, else the archive folder the pack names
    (``<series>/<experiment>/<pack>/<run_id>``)."""
    try:
        pack = json.loads((Path(run_dir) / "manifest.json").read_text()).get("task_pack_id")
    except (OSError, ValueError):
        pack = None
    return pack or Path(run_dir).parent.name or None


def standings(events: list[dict], pack_id: str | None) -> dict | None:
    """The run's standings as its pack's registered panel gives them (None when the pack has none)."""
    from oaos2.archive.renderers import ensure_pack_renderers
    ensure_pack_renderers(pack_id)
    panel = _STANDINGS.get(pack_id or "")
    return panel(events) if panel else None


def live_clock(state: dict, run_dir: Path, *, now: float | None = None) -> dict:
    """A copy of ``state`` with the seconds since the run's and each agent's last
    event, from the recorded timestamps, and since a stream file last changed."""
    run_dir = Path(run_dir)
    now = time.time() if now is None else now

    def since(ts):
        return int(now - ts) if isinstance(ts, (int, float)) else None

    out = dict(state)
    out["quiet_s"] = since(state.get("last_ts"))
    try:  # the record's own clock: when a stream file last changed on this computer
        out["written_s"] = int(now - max((run_dir / rel).stat().st_mtime for rel in _STREAMS
                                         if (run_dir / rel).exists()))
    except ValueError:
        out["written_s"] = None
    out["groups"] = [{**g, "agents": [{**a, "quiet_s": since(a["last_ts"])} for a in g["agents"]]}
                     for g in state["groups"]]
    return out


def feed_items(items: list[dict], *, after: int | None, member: dict[str, str],
               group: str | None = None) -> list[dict]:
    """Story items after position ``after`` (the last ``FEED_FIRST`` on a first poll),
    cut to one group when asked: items by its members or addressed to them. Each
    directed item carries where it crossed: within a group or from one to another."""
    if group:
        items = [it for it in items if member.get(it["who"]) == group
                 or any(member.get(t) == group for t in it["to"])]
    if after is None:
        items = items[-FEED_FIRST:]
    else:
        # a folded burst is shown again, with its new count, once any member is new
        items = [it for it in items if max(it["seq"], it.get("last_seq") or 0) > after]
    grouped = len(set(member.values())) > 1  # one group has no crossings to name
    out = []
    for it in items:
        it = dict(it)
        src = member.get(it["who"]) if grouped else None
        dst = sorted({member[t] for t in it["to"] if t in member})
        if it["kind"] in ("note", "handoff", "exchange", "relay") and src and dst:
            it["crossing"] = (f"within {src}" if dst == [src]
                              else f"{src} → {', '.join(dst)}")
        out.append(it)
    return out


def in_flight(rows: list[dict]) -> list[dict]:
    """Unfinished runs the archive has not read as idle, most recently written first."""
    out = [r for r in rows if r.get("status") == "incomplete"]
    return sorted(out, key=lambda r: r.get("idle_minutes") if r.get("idle_minutes") is not None
                  else 10 ** 9)


# --- lanes: the groups side by side ------------------------------------------ #

BOARD_LANE = "board"
GAP_S = 60  # a pause this long between two rows is marked, since rows are not to scale


def lanes_of(agents: list[str], member: dict[str, str], *, board: bool) -> tuple[list[str], dict[str, int]]:
    """Lane names and ``{agent: lane index}``: one lane per group when the agents are
    grouped, otherwise one per agent; the board is a lane of its own when anyone may
    post, since a post goes to everyone rather than to one lane."""
    grouped = len(set(member.values())) > 1
    lanes: list[str] = []
    for a in agents:
        name = member[a] if grouped else a
        if name not in lanes:
            lanes.append(name)
    if board:
        lanes.append(BOARD_LANE)
    index = {a: lanes.index(member[a] if grouped else a) for a in agents}
    return lanes, index


def _busy_at(events: list[dict], seqs: list[int]) -> dict[int, set[str]]:
    """``{seq: agents busy just after that position}``. Busy means a model call or a
    tool call was open: invoked and not yet answered. That is recorded work, not a
    claim about what an agent attends to."""
    wanted = sorted(set(seqs))
    out: dict[int, set[str]] = {}
    calls: dict[str, int] = {}
    tools: dict[str, int] = {}
    i = 0
    for e in events:
        seq = e.get("sequence_number")
        seq = seq if isinstance(seq, int) else -1
        while i < len(wanted) and wanted[i] < seq:
            out[wanted[i]] = {a for a in set(calls) | set(tools) if calls.get(a) or tools.get(a)}
            i += 1
        a, cls = e.get("agent_id"), e.get("event_class")
        if a:
            if cls == "model.invoked":
                calls[a] = calls.get(a, 0) + 1
            elif cls in ("model.responded", "model.invocation_failed"):
                calls[a] = max(calls.get(a, 0) - 1, 0)
            elif cls == "tool.called":
                tools[a] = tools.get(a, 0) + 1
            elif cls in ("tool.result", "tool.denied"):
                tools[a] = max(tools.get(a, 0) - 1, 0)
    busy = {a for a in set(calls) | set(tools) if calls.get(a) or tools.get(a)}
    for s in wanted[i:]:
        out[s] = busy
    return out


def lane_rows(items: list[dict], events: list[dict], *, lanes: list[str],
              index: dict[str, int]) -> list[dict]:
    """One row per item, placed in its author's lane (a post in the board lane), with
    the lanes it reached, how many of each lane's agents were busy at that position,
    and the time since the run's first event. A row that opens a logical day, or
    follows a pause of more than ``GAP_S`` seconds, carries a separator label."""
    prev_ts = prev_day = None
    ts_of: dict[int, float] = {}
    day_of: dict[int, int] = {}
    day, t0 = None, None
    for e in events:
        seq, ts = e.get("sequence_number"), e.get("timestamp")
        if e.get("event_class") == "clock.round":
            day = int((e.get("payload") or {}).get("round_no") or 0)
        if isinstance(seq, int):
            if isinstance(ts, (int, float)):
                ts_of[seq] = ts
                t0 = ts if t0 is None else t0
            if day is not None:
                day_of[seq] = day
    busy = _busy_at(events, [int(it["seq"]) for it in items])
    board = lanes.index(BOARD_LANE) if BOARD_LANE in lanes else None
    rows = []
    for it in items:
        if (it.get("e") or {}).get("event_class") == "clock.round":
            continue  # the day separator on the next row says it
        seq = int(it["seq"])
        ts = ts_of.get(seq)
        d = day_of.get(seq)
        sep = None
        if d is not None and d != prev_day:
            sep = f"day {d} opens"
        elif ts is not None and prev_ts is not None and ts - prev_ts > GAP_S:
            sep = f"{int(ts - prev_ts)} s without a shown item"
        prev_day = d if d is not None else prev_day
        prev_ts = ts if ts is not None else prev_ts
        src = index.get(it["who"])
        lane = board if it["kind"] == "post" and board is not None else src
        if it["kind"] == "notice" and it["to"] and it["to"][0] in index:
            lane = index[it["to"][0]]  # a notice arrives in its recipient's lane
        if lane is None:
            lane = board if board is not None else 0  # a run-level item (no agent)
        reached = sorted({index[t] for t in it["to"] if t in index} - {lane})
        if it["kind"] == "post":
            reached = []  # to everyone: the board lane is the destination
        counts = [0] * len(lanes)
        for a in busy.get(seq, ()):
            if a in index:
                counts[index[a]] += 1
        span = [lane, *reached] + ([src] if it["kind"] == "post" and src is not None else [])
        arrive = {i: [t for t in it["to"] if index.get(t) == i] for i in reached}
        rows.append({"sep": sep, "item": it, "lane": lane, "reached": reached, "arrive": arrive,
                     "busy": counts,
                     "from": src if it["kind"] == "post" else None,
                     "span": (min(span), max(span)) if len(set(span)) > 1 else None,
                     "t": int(ts - t0) if ts is not None and t0 is not None else None,
                     "ts": ts, "day": d})
    return rows


def rows_after(rows: list[dict], after: int | None) -> list[dict]:
    """The rows the reader does not have yet (the last ``FEED_FIRST`` on a first poll)."""
    if after is None:
        return rows[-FEED_FIRST:]
    return [r for r in rows if max(r["item"]["seq"], r["item"].get("last_seq") or 0) > after]
