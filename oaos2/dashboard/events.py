"""Per-run event access for the trace explorer (DASHBOARD.md §4.3) — read-only.

Reuses the archive's own projections (``transcript._summary`` for row text,
``_load_raw``/``_extract_prose`` for verbatim prose) so the explorer shows exactly
what the derived transcripts show, never a reimplementation. Streams are parsed
once per (run, content) and memoized in-process — the memo is keyed on the stream
files' size+mtime, so an in-flight run's appends invalidate it naturally.
"""

from __future__ import annotations

import json
import threading
from collections import OrderedDict
from pathlib import Path

from oaos2.archive.transcript import _extract_prose, _load_raw, _summary, events_in_order

summary = _summary  # the one row-text function, shared with the transcripts

_STREAMS = ("trace/events.jsonl", "trace/infra.jsonl")
_CACHE_RUNS = 16  # a reader flips between a few runs (paired views need two); scans use cache.py

_cache: OrderedDict[str, tuple[str, list[dict], dict[str, dict]]] = OrderedDict()
_cache_lock = threading.Lock()  # FastAPI serves sync handlers from a thread pool


def _stream_fingerprint(run_dir: Path) -> str:
    parts = []
    for rel in _STREAMS:
        try:
            st = (run_dir / rel).stat()
            parts.append(f"{st.st_size}:{st.st_mtime_ns}")
        except OSError:
            parts.append("-")
    return "|".join(parts)


def load_events(run_dir: Path) -> list[dict]:
    """All events in writer order, memoized until the streams change."""
    return _load(run_dir)[0]


def event_index(run_dir: Path) -> dict[str, dict]:
    """``event_id → event`` for the same memoized snapshot."""
    return _load(run_dir)[1]


def _load(run_dir: Path) -> tuple[list[dict], dict[str, dict]]:
    run_dir = Path(run_dir)
    key = str(run_dir.resolve())
    fp = _stream_fingerprint(run_dir)
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] == fp:
            _cache.move_to_end(key)
            return hit[1], hit[2]
    events = events_in_order(run_dir)  # parse outside the lock; a duplicate parse is harmless
    by_id = {e.get("event_id"): e for e in events if e.get("event_id")}
    with _cache_lock:
        _cache[key] = (fp, events, by_id)
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_RUNS:
            _cache.popitem(last=False)
    return events, by_id


# --- filtering (the explorer's cut of the stream) --------------------------- #

def family_of(event_class: str) -> str:
    return (event_class or "?").split(".", 1)[0]


def facets(events: list[dict]) -> dict[str, list[str]]:
    """Distinct values for the explorer's filter selects, in stable sorted order."""
    def _distinct(key):
        return sorted({e.get(key) for e in events if e.get(key)})
    return {
        "agent": _distinct("agent_id"),
        "event_class": sorted({e.get("event_class") or "?" for e in events}),
        "family": sorted({family_of(e.get("event_class")) for e in events}),
        "channel": _distinct("channel"),
        "audience": _distinct("audience"),
        "phase": _distinct("phase_name"),
    }


def filter_events(events: list[dict], *, agent: str | None = None, event_class: str | None = None,
                  family: str | None = None, channel: str | None = None,
                  audience: str | None = None, phase: str | None = None,
                  turn: str | None = None, q: str | None = None) -> list[dict]:
    out = events
    if agent:
        out = [e for e in out if e.get("agent_id") == agent]
    if event_class:
        out = [e for e in out if e.get("event_class") == event_class]
    if family:
        out = [e for e in out if family_of(e.get("event_class")) == family]
    if channel:
        out = [e for e in out if e.get("channel") == channel]
    if audience:
        out = [e for e in out if e.get("audience") == audience]
    if phase:
        out = [e for e in out if e.get("phase_name") == phase]
    if turn:
        out = [e for e in out if e.get("turn_id") == turn]
    if q:
        needle = q.lower()
        # Free text searches what a reader can see: class/agent/turn, the summary,
        # AND the payload's own text fields (message bodies, volleys, thinking) —
        # summaries alone would miss what was actually *said*.
        out = [e for e in out
               if needle in (e.get("event_class") or "").lower()
               or needle in (e.get("agent_id") or "").lower()
               or needle in (e.get("turn_id") or "").lower()
               or needle in _summary(e).lower()
               or any(needle in v.lower() for v in (e.get("payload") or {}).values()
                      if isinstance(v, str))]
    return out


# --- verbatim ground truth --------------------------------------------------- #

def prose_for(run_dir: Path, event: dict) -> str:
    """The model's verbatim utterance behind a ``model.responded`` event (from raw/)."""
    ref = (event.get("payload") or {}).get("raw_provider_response_ref")
    return _extract_prose(_load_raw(run_dir, ref) or {})


def raw_ref_digest(event: dict) -> str | None:
    """The content digest of the event's raw payload ref (``sha256/<digest>``), if any."""
    ref = (event.get("payload") or {}).get("raw_provider_response_ref")
    if isinstance(ref, str) and "/" in ref:
        return ref.split("/", 1)[1]
    return None


# --- communication views (DASHBOARD.md §4.4) --------------------------------- #

def comm_view(events: list[dict], exchanges: list[dict] | None = None) -> dict:
    """The interaction order, grouped for reading: conversations (volleys in round
    order), chat request→resolution threads, relayed messages, handoffs; and the
    voluntary channels (M8 §7): the board, notes per pair, the pack's registered
    exchanges, and the derived request→reply threads over all three."""
    conversations: dict[str, dict] = {}
    for e in events:
        cls = e.get("event_class")
        if cls not in ("conversation.opened", "conversation.volley", "conversation.closed"):
            continue
        p = e.get("payload") or {}
        cid = p.get("conversation_id") or "?"
        conv = conversations.setdefault(cid, {"id": cid, "opened": None, "closed": None,
                                              "participants": [], "volleys": []})
        if cls == "conversation.opened":
            conv["opened"] = e
            conv["participants"] = list(p.get("participants") or [])
        elif cls == "conversation.volley":
            conv["volleys"].append(e)
        else:
            conv["closed"] = e

    requests = [e for e in events if e.get("event_class") == "chat.requested"]
    resolution_classes = ("chat.response", "chat.declined", "chat.ignored", "chat.timed_out")
    chats = []
    for req in requests:
        rid = req.get("event_id")
        resolutions = [e for e in events if e.get("event_class") in resolution_classes
                       and (rid in (e.get("caused_by_event_ids") or [])
                            or e.get("parent_event_id") == rid)]
        chats.append({"request": req, "resolutions": resolutions})

    # The voluntary board (M8 §7): posts in sequence, and who retrieved the board or
    # their notes, kept apart from delivery — a post delivered is not a post read.
    posts = [e for e in events if e.get("event_class") == "board.posted"]
    retrievals: dict[str, dict] = {}
    for e in events:
        cls = e.get("event_class")
        if cls not in ("board.retrieved", "notes.retrieved"):
            continue
        agent = e.get("agent_id") or "?"
        r = retrievals.setdefault(agent, {"agent": agent, "board_reads": 0, "note_reads": 0,
                                          "last_board_seq": None})
        if cls == "board.retrieved":
            r["board_reads"] += 1
            to_seq = (e.get("payload") or {}).get("to_seq")
            if to_seq is not None:
                r["last_board_seq"] = max(r["last_board_seq"] or 0, to_seq)
        else:
            r["note_reads"] += 1
    messages = [e for e in events if e.get("event_class") == "message.sent"]
    notes = [e for e in messages if (e.get("payload") or {}).get("kind") == "note"]
    relays = [e for e in messages if (e.get("payload") or {}).get("kind") != "note"]
    pairs: dict[tuple[str, str], list[dict]] = {}
    for e in notes:
        a, b = e.get("agent_id") or "?", (e.get("payload") or {}).get("to") or "?"
        pairs.setdefault(tuple(sorted((a, b))), []).append(e)
    exchanges = exchanges or []
    return {
        "conversations": [conversations[k] for k in sorted(conversations)],
        "chats": chats,
        "messages": relays,
        "handoffs": [e for e in events if e.get("event_class") == "handoff"],
        "board": posts,
        "retrievals": [retrievals[k] for k in sorted(retrievals)],
        "notes": notes,
        "note_pairs": [{"pair": k, "notes": v} for k, v in sorted(pairs.items())],
        "exchanges": exchanges,
        "threads": exchange_threads(posts, notes, exchanges),
    }


_THREAD_REPLY_CAP = 12  # per recipient; a long run of grants reads as "and more"


def _directed(posts: list[dict], notes: list[dict], exchanges: list[dict]) -> list[dict]:
    """Every directed act in writer order: posts (to their recipients), notes, and
    the pack's exchange rows, in one row shape."""
    rows = []
    for e in posts:
        p = e.get("payload") or {}
        rows.append({"seq": e.get("sequence_number") or 0, "event_id": e.get("event_id"),
                     "from": e.get("agent_id") or "?", "to": list(p.get("recipients") or []),
                     "kind": "post", "text": p.get("text") or ""})
    for e in notes:
        p = e.get("payload") or {}
        rows.append({"seq": e.get("sequence_number") or 0, "event_id": e.get("event_id"),
                     "from": e.get("agent_id") or "?", "to": [p.get("to") or "?"],
                     "kind": "note", "text": p.get("payload_text") or p.get("text") or ""})
    rows.extend(exchanges)
    return sorted(rows, key=lambda r: (r["seq"], r["event_id"] or ""))


def exchange_threads(posts: list[dict], notes: list[dict], exchanges: list[dict]) -> list[dict]:
    """A reading aid, labeled derived: each request (a post or a note) followed by
    what each addressee did toward the author afterwards — exchanges naming the
    author, notes back, posts — up to and including that addressee's next message
    to the author. Proximity in the record is the only rule; the grouping does not
    establish that any later act answered the request, and coding it is the
    reader's job (the annotate control on each thread)."""
    rows = _directed(posts, notes, exchanges)
    threads = []
    for req in rows:
        if req["kind"] not in ("post", "note"):
            continue
        author = req["from"]
        replies = []
        for who in req["to"]:
            items, more = [], 0
            for r in rows:
                if r["seq"] <= req["seq"] or r["from"] != who:
                    continue
                to_author = author in r["to"]
                is_message = r["kind"] in ("post", "note")
                if not to_author:
                    continue  # a note to a third party neither replies nor closes
                if len(items) < _THREAD_REPLY_CAP:
                    items.append(r)
                else:
                    more += 1
                if is_message:
                    break  # the addressee's next message to the author closes the window
            replies.append({"by": who, "items": items, "more": more})
        threads.append({"request": req, "author": author, "replies": replies,
                        "n_replies": sum(len(r["items"]) for r in replies),
                        "event_ids": [req["event_id"]] + [i["event_id"] for r in replies
                                                          for i in r["items"] if i["event_id"]]})
    return threads


# swimlane mark color slots: categorical, fixed order (dataviz rule — never cycled)
_LANE_FAMILY_SLOT = {"model": "s1", "tool": "s2", "file": "s3", "conversation": "s5"}
_SWIMLANE_MAX_MARKS = 5000


def swimlane(events: list[dict]) -> dict:
    """The per-agent timeline model: one lane per agent (first-seen order), x =
    sequence_number; comm events become cross-lane arrows, commits flags, trouble
    marks; turn.started→turn.completed pairs become activity spans (the soft band
    showing WHEN each agent was actually working). Rendered as SVG by the template."""
    from oaos2.dashboard.store import is_audit_class  # local: avoid module cycle

    agents: list[str] = []
    for e in events:
        a = e.get("agent_id")
        if a and a not in agents:
            agents.append(a)
    marks, arrows = [], []
    max_seq = max((e.get("sequence_number") or 0) for e in events) if events else 1
    truncated = False

    # activity spans: pair each turn's start/end per agent (unclosed → runs to end)
    spans: list[dict] = []
    open_turns: dict[tuple, int] = {}
    for e in events:
        cls, agent, turn = e.get("event_class"), e.get("agent_id"), e.get("turn_id")
        seq = e.get("sequence_number") or 0
        if cls == "turn.started" and agent:
            open_turns[(agent, turn)] = seq
        elif cls in ("turn.completed", "turn.paused") and agent:
            s0 = open_turns.pop((agent, turn), None)
            if s0 is not None:
                spans.append({"agent": agent, "s0": s0, "s1": seq, "turn": turn})
    for (agent, turn), s0 in open_turns.items():
        spans.append({"agent": agent, "s0": s0, "s1": max_seq, "turn": turn})
    for e in events:
        if len(marks) >= _SWIMLANE_MAX_MARKS:
            truncated = True
            break
        cls, seq, agent = e.get("event_class") or "?", e.get("sequence_number") or 0, e.get("agent_id")
        p = e.get("payload") or {}
        if cls in ("handoff", "message.sent"):
            src = p.get("from_agent") or agent
            dst = p.get("to_agent") or p.get("to")
            if src in agents and dst in agents and src != dst:
                arrows.append({"from": src, "to": dst, "seq": seq, "cls": cls,
                               "event_id": e.get("event_id")})
                continue
        if agent is None:
            continue
        if is_audit_class(cls) and e.get("audience") != "infrastructure":
            kind = "trouble"
        elif cls == "state.committed":
            kind = "commit"
        elif cls == "conversation.volley":
            kind = "volley"
        elif cls == "board.posted":
            kind = "post"  # a broadcast: one mark on the author's lane, no arrows
        else:
            slot = _LANE_FAMILY_SLOT.get(family_of(cls))
            if slot is None:
                continue  # lifecycle/turn chatter would just be noise at this zoom
            kind = slot
        marks.append({"agent": agent, "seq": seq, "kind": kind, "cls": cls,
                      "event_id": e.get("event_id")})
    return {"agents": agents, "marks": marks, "arrows": arrows, "spans": spans,
            "max_seq": max(max_seq, 1), "truncated": truncated}


# --- the decision flow (DASHBOARD.md §4.3b) ----------------------------------- #
#
# One chronological reading of the run with the CONTENT inline — thinking, tool
# calls with their real output, utterances, handoff bodies, committed artifacts —
# zoomable by level. Levels are cumulative; problem events (audit classes) are
# ALWAYS shown at every level so zooming out can never hide a failure moment.

FLOW_LEVELS = ("decisions", "dialogue", "reasoning", "everything")

# item kind → the coarsest level that shows it
_KIND_LEVEL = {
    "commit": 0, "outcome": 0, "lifecycle": 0, "evaluation": 0, "handoff": 0, "filing": 0,
    "problem": 0, "clock": 0, "capacity": 0,   # never hidden
    "arrival": 0, "constraint": 0, "intervention": 0,  # what the day was about, and what bit
    "milestone": 0,  # the task's registered turning points (archive/exchanges.py)
    "say": 1, "volley": 1, "message": 1, "chat": 1, "stage": 1, "exchange": 1,
    "thinking": 2, "tool": 2, "observed": 2,
    "other": 3,
}

_LIFECYCLE = {"run.started", "run.completed", "run.failed", "agent.launched",
              "agent.resumed", "conversation.opened", "conversation.closed"}
_CHAT = {"chat.requested", "chat.response", "chat.declined", "chat.ignored", "chat.timed_out"}

_TRUNCATE_AT = 1400  # chars shown before the rest folds behind "show all"


def _handoff_key(e: dict) -> tuple | None:
    """A broadcast filing's identity: (sender, formalized payload ref). The handoff
    payload carries no commitment id; the delta's ref (``submitted/<cid>.json``) is
    the platform's own pointer to the artifact every copy carries."""
    if e.get("event_class") != "handoff":
        return None
    p = e.get("payload") or {}
    ref = (p.get("handoff_delta") or {}).get("formalized_payload_ref")
    if not ref:
        return None
    return (p.get("from_agent") or e.get("agent_id"), ref)


def collapse_broadcasts(events: list[dict]) -> list[dict | list[dict]]:
    """The stream with each run of same-(sender, ref) handoffs folded into one
    list — a filing broadcast to every peer reads as ONE filing with recipients,
    not as seven events (a lateral cell carries 414 handoffs for 69 filings)."""
    out: list[dict | list[dict]] = []
    pending: list[dict] = []
    pending_key: tuple | None = None
    for e in events:
        key = _handoff_key(e)
        if key is not None and key == pending_key:
            pending.append(e)
            continue
        if pending:
            out.append(pending if len(pending) > 1 else pending[0])
            pending, pending_key = [], None
        if key is not None:
            pending, pending_key = [e], key
        else:
            out.append(e)
    if pending:
        out.append(pending if len(pending) > 1 else pending[0])
    return out


def flow_items(run_dir: Path, events: list[dict], level: str, *,
               milestones: list[dict] = (), exchanges: list[dict] = ()) -> list[dict]:
    """The flow's item list at one zoom level. Each item:
    {kind, e, title, text, folded, [recipients, event_ids, n]} — ``text`` is the
    step's real content (a one-line digest at the ``decisions`` zoom, where the
    reader wants the shape of the day, not the bodies), ``folded`` the remainder
    past the truncation point (the template offers it as a fetch link, never
    inline — a lateral cell's bodies are 525 KB). ``milestones`` and ``exchanges`` are
    the pack's registered rows (``archive/exchanges.py``): an event they name, which
    the platform would otherwise show only at ``everything``, is shown as the task's
    milestone (at ``decisions``) or exchange (at ``dialogue``) in the pack's words."""
    from oaos2.dashboard.store import is_audit_class  # local: avoid module cycle

    max_level = FLOW_LEVELS.index(level if level in FLOW_LEVELS else "reasoning")
    compact = max_level == 0
    registered: dict[str, tuple[str, str, str]] = {}
    for row in exchanges:
        to = ", ".join(row.get("to") or [])
        registered[row.get("event_id")] = ("exchange", f"{row.get('from')} → {to} · {row.get('kind')}",
                                           row.get("text") or "")
    for row in milestones:
        registered[row.get("event_id")] = ("milestone", f"{row.get('from')} · {row.get('kind')}",
                                           row.get("text") or "")
    out: list[dict] = []
    for entry in collapse_broadcasts(events):
        if isinstance(entry, list):
            item = _filing_item(entry, compact)
        else:
            item = _flow_item(run_dir, entry, is_audit_class, compact)
        if item is None:
            continue
        hit = registered.get(item["e"].get("event_id")) if item["kind"] == "other" else None
        if hit:
            item = _item(hit[0], item["e"], hit[1], hit[2])
        if _KIND_LEVEL[item["kind"]] <= max_level:
            out.append(item)
    return out


def _digest(text: str, n: int = 200) -> str:
    one = " ".join((text or "").split())
    return one if len(one) <= n else one[:n] + "…"


def _filing_item(copies: list[dict], compact: bool) -> dict:
    first = copies[0]
    p = first.get("payload") or {}
    ref = (p.get("handoff_delta") or {}).get("formalized_payload_ref") or ""
    stem = ref.rsplit("/", 1)[-1].rsplit(".", 1)[0] if ref else "?"
    recipients = [(c.get("payload") or {}).get("to_agent") or "?" for c in copies]
    title = (f"FILING {stem} → {len(recipients)} recipients "
             f"({', '.join(recipients)})")
    text = p.get("payload_text") or ""
    body, folded = (_digest(text), "") if compact else _fold(text)
    item = _item("filing", first, title, body, folded)
    item.update({"recipients": recipients, "n": len(copies),
                 "event_ids": [c.get("event_id") for c in copies], "ref": ref})
    return item


def _flow_item(run_dir: Path, e: dict, is_audit_class, compact: bool = False) -> dict | None:
    cls = e.get("event_class") or "?"
    p = e.get("payload") or {}

    if is_audit_class(cls) and e.get("audience") != "infrastructure" \
            and e.get("channel") != "infrastructure":
        # recorder bookkeeping (file.reconciliation_mismatch and kin) is not a
        # problem *in the organization* — it stays on the audit page
        return _item("problem", e, cls, _summary(e))
    if cls == "state.committed":
        sc = p.get("state_commitment") or {}
        full = _committed_payload(run_dir, sc.get("payload_ref"))
        body, folded = (_digest(full), "") if compact else _fold(full)
        return _item("commit", e, f"COMMIT {sc.get('commitment_id', '?')} "
                                  f"({sc.get('kind', '')})", body, folded)
    if cls == "outcome.closed":
        return _item("outcome", e, f"OUTCOME CLOSED {p.get('outcome_id', '')}", "")
    if cls == "evaluation.completed":
        return _item("evaluation", e, "evaluation.completed",
                     json.dumps(p.get("agent_feedback"), sort_keys=True)
                     if p.get("agent_feedback") is not None else "")
    if cls == "handoff":
        text = p.get("payload_text") or ""
        body, folded = (_digest(text), "") if compact else _fold(text)
        return _item("handoff", e, f"HANDOFF {p.get('from_agent', '?')} → "
                                   f"{p.get('to_agent', '?')} ({p.get('kind', '')})",
                     body, folded)
    if cls == "environment.event":
        ee = p.get("environment_event") or {}
        pl = ee.get("payload") if isinstance(ee.get("payload"), dict) else {}
        bits = [f"NOTICE {pl.get('notice_id') or ee.get('packet_id') or '?'} → "
                f"{ee.get('target_role_id') or e.get('agent_id') or '?'}"]
        if pl.get("case_id"):
            bits.append(str(pl["case_id"]))
        if pl.get("type"):
            bits.append(str(pl["type"]))
        if ee.get("wave_id"):
            bits.append(str(ee["wave_id"]))
        text = pl.get("text") or json.dumps(pl, sort_keys=True)
        body, folded = (_digest(text), "") if compact else _fold(text)
        return _item("arrival", e, " · ".join(bits), body, folded)
    if cls == "agent.observed":
        obs = p.get("observations") or []
        counts: dict[str, int] = {}
        for o in obs:
            k = o.get("kind") or "?"
            counts[k] = counts.get(k, 0) + 1
        title = "SAW " + (", ".join(f"{k}×{n}" if n > 1 else k for k, n in sorted(counts.items()))
                          or "nothing new")
        body_lines = [f"[{o.get('kind')}] {_digest(str(o.get('payload') or ''), 400)}" for o in obs]
        return _item("observed", e, title, *_fold("\n".join(body_lines)))
    if cls == "context.compaction":
        return _item("constraint", e,
                     f"CONTEXT COMPACTED · {p.get('tokens_before', '?')} → "
                     f"{p.get('tokens_after', '?')} tokens · "
                     f"{p.get('messages_summarized', '?')} messages summarized", "")
    if cls == "intervention.recorded":
        probs = p.get("problems") or []
        return _item("intervention", e,
                     f"INTERVENTION · {p.get('kind', '?')} [{p.get('class', '?')}]",
                     "\n".join(str(x) for x in probs))
    if cls == "coordination.stage_advanced":
        return _item("stage", e, f"DUTY {p.get('from', '?')} → {p.get('to', '?')}"
                                 f" ({p.get('phase', '')})", "")
    if cls == "clock.round":
        return _item("clock", e,
                     f"DAY {p.get('round_no', '?')} / {p.get('rounds_total', '?')}", "")
    if cls == "capacity.deadline_lapse":
        case = p.get("case_id") or p.get("commitment_id") or "?"
        return _item("capacity", e, f"DEADLINE LAPSED · {case}",
                     f"due day {p.get('deadline_round', '?')} · observed day "
                     f"{p.get('round_no', '?')}" + (" · forced" if p.get("forced") else ""))
    if cls == "capacity.slot_ceiling":
        slot = p.get("slot_id") or p.get("commitment_id") or p.get("case_id") or "?"
        return _item("capacity", e, f"CAPACITY CEILING · {slot}", _summary(e))
    if cls in _LIFECYCLE:
        return _item("lifecycle", e, cls, _summary(e))
    if cls == "conversation.volley":
        return _item("volley", e, f"{p.get('speaker', '?')} (round {p.get('round_index')})",
                     *_fold(p.get("text") or ""))
    if cls == "message.sent":
        return _item("message", e, f"message → {p.get('to', '?')} ({p.get('kind', '')})",
                     *_fold(p.get("payload_text") or p.get("text") or ""))
    if cls == "board.posted":
        return _item("message", e, f"board post #{p.get('seq', '?')} → "
                                   f"{len(p.get('recipients') or [])} agent(s)",
                     *_fold(p.get("text") or ""))
    if cls == "board.retrieved":
        if p.get("view") == "index":  # the forum board (October 10, 2026)
            return _item("message", e, f"read board index, page {p.get('page', 1)} of {p.get('pages', 1)}", "")
        return _item("message", e, (f"opened board {p['view']}" + (f" #{p['thread']}" if p.get("thread") else "") + ": "
                                    if p.get("view") else "read board: ") + f"{p.get('count', 0)} post(s)"
                     + (f" #{p.get('from_seq')}–#{p.get('to_seq')}" if p.get("count") else ""), "")
    if cls == "notes.retrieved":
        return _item("message", e, f"read notes: {p.get('count', 0)} note(s)", "")
    if cls in _CHAT:
        return _item("chat", e, cls, p.get("text") or p.get("reason") or "")
    if cls == "reasoning.step":
        narration = (p.get("narration") or "").strip()
        thinking = (p.get("thinking") or "").strip()
        body, folded = _fold(thinking)
        return _item("thinking", e, narration or "thinking", body, folded)
    if cls == "model.responded":
        prose = prose_for(run_dir, e)
        if not prose:
            return None  # telemetry only; usage stays on the inspector page
        return _item("say", e, f"{e.get('agent_id') or '·'} says", *_fold(prose))
    if cls == "tool.called":
        return _item("tool", e, f"⚙ {p.get('tool_name', '?')}", "")
    if cls == "tool.result":
        body, folded = _fold(str(p.get("output") or ""))
        return _item("tool", e, f"→ {p.get('tool_name', '?')} result", body, folded)
    # everything else only appears fully zoomed in
    return _item("other", e, cls, _summary(e))


def _item(kind, e, title, text, folded="") -> dict:
    return {"kind": kind, "e": e, "title": title, "text": text, "folded": folded}


def _fold(text: str) -> tuple[str, str]:
    text = text or ""
    if len(text) <= _TRUNCATE_AT:
        return text, ""
    return text[:_TRUNCATE_AT], text[_TRUNCATE_AT:]


def _committed_payload(run_dir: Path, payload_ref) -> str:
    """The actual submitted artifact behind a commitment, when it's still on disk
    (containment-checked — a hostile ref can't read outside the run dir)."""
    if not payload_ref or not isinstance(payload_ref, str):
        return ""
    root = Path(run_dir).resolve()
    for base in ("container_mount", "captured", "."):
        candidate = (root / base / payload_ref).resolve()
        if root not in candidate.parents or not candidate.is_file():
            continue
        try:
            return json.dumps(json.loads(candidate.read_text()), indent=2, sort_keys=True)
        except (OSError, ValueError):
            try:
                return candidate.read_text(errors="replace")
            except OSError:
                return ""
    return f"(submitted payload {payload_ref} not retained on disk)"


def flow_groups(items: list[dict], day_of: dict[str, int] | None = None) -> list[dict]:
    """Group consecutive items by (day, agent, turn) — the reading's paragraph
    breaks; ``day`` (from ``archive.clock.day_index``) is None for unclocked runs."""
    groups: list[dict] = []
    day_of = day_of or {}
    for item in items:
        e = item["e"]
        day = day_of.get(e.get("event_id")) if day_of else None
        key = (day, e.get("agent_id") or "·", e.get("turn_id") or "")
        if not groups or groups[-1]["key"] != key:
            groups.append({"key": key, "day": day, "agent": key[1], "turn": key[2], "items": []})
        groups[-1]["items"].append(item)
    return groups


def item_text(run_dir: Path, event: dict) -> str:
    """The full, unfolded content of one flow item (the per-item fetch route)."""
    from oaos2.dashboard.store import is_audit_class
    item = _flow_item(run_dir, event, is_audit_class, compact=False)
    if item is None:
        return _summary(event)
    return f"{item['title']}\n\n{item['text']}{item['folded']}"


# --- causal navigation (§6.2 over the memoized snapshot) --------------------- #

def parents_of(by_id: dict[str, dict], event: dict) -> list[dict]:
    """Immediate causes: ``caused_by_event_ids`` + the structural parent, resolved."""
    ids = list(event.get("caused_by_event_ids") or [])
    structural = event.get("parent_event_id")
    if structural and structural not in ids:
        ids.append(structural)
    return [by_id[i] for i in ids if i in by_id]


def children_of(events: list[dict], event_id: str) -> list[dict]:
    """Events citing this one as a cause (or structural parent), in stream order."""
    return [e for e in events
            if event_id in (e.get("caused_by_event_ids") or [])
            or e.get("parent_event_id") == event_id]


def ancestry_outline(by_id: dict[str, dict], event_id: str,
                     *, max_nodes: int = 200) -> list[tuple[int, dict]]:
    """The "what led to this?" outline: depth-first over ``caused_by`` parents,
    each ancestor once (at its first, shallowest encounter), bounded so a long
    causal chain can't render an unbounded page."""
    out: list[tuple[int, dict]] = []
    seen: set[str] = set()

    def _walk(eid: str, depth: int) -> None:
        if len(out) >= max_nodes:
            return
        e = by_id.get(eid)
        if e is None:
            return
        for pid in e.get("caused_by_event_ids") or []:
            if pid in seen:
                continue
            seen.add(pid)
            parent = by_id.get(pid)
            if parent is None:
                continue
            out.append((depth, parent))
            _walk(pid, depth + 1)

    _walk(event_id, 0)
    return out
