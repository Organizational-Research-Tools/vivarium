"""The replay (DASHBOARD.md §4.2g): watch how a run's work unfolded, as a moving window
over the saved record.

Everything the page animates is read from recorded events, keyed to the time since the
run's first event: when each agent had a model call or a tool call open (busy
intervals), every directed act between roles with its time (notes, handoffs, posts to
the board, and the task's registered exchanges), day openings on a clocked run, and the
Story's items laid out in lanes. Nothing is inferred or smoothed; a window only chooses
which recorded acts are drawn. Busy means a call was open, not what a model attended to.
"""

from __future__ import annotations

from oaos2.dashboard.organization import BOARD, graph


def _t(e: dict, t0: float) -> float | None:
    ts = e.get("timestamp")
    return round(ts - t0, 2) if isinstance(ts, (int, float)) else None


def busy_intervals(events: list[dict], agents: list[str], t0: float) -> dict[str, list[list[float]]]:
    """``{agent: [[start, end], ...]}`` — the stretches in which the agent had at least
    one model call or tool call open. An interval still open at the end runs to the
    last event."""
    open_n: dict[str, int] = {a: 0 for a in agents}
    since: dict[str, float] = {}
    out: dict[str, list[list[float]]] = {a: [] for a in agents}
    last = 0.0
    for e in events:
        a, cls, t = e.get("agent_id"), e.get("event_class"), _t(e, t0)
        if t is None:
            continue
        last = max(last, t)
        if a not in open_n:
            continue
        if cls in ("model.invoked", "tool.called"):
            if open_n[a] == 0:
                since[a] = t
            open_n[a] += 1
        elif cls in ("model.responded", "model.invocation_failed", "tool.result", "tool.denied"):
            if open_n[a] > 0:
                open_n[a] -= 1
                if open_n[a] == 0:
                    out[a].append([since.pop(a), t])
    for a, n in open_n.items():
        if n > 0 and a in since:
            out[a].append([since[a], last])
    return out


def acts(events: list[dict], exchanges: list[dict], agents: list[str], t0: float) -> list[dict]:
    """Every directed act in time order: ``{t, seq, from, to, kind}``. A post goes to the
    board; an act to several roles is one entry per recipient."""
    ts_of = {e.get("sequence_number"): _t(e, t0) for e in events}
    out = []
    known = set(agents)
    for e in events:
        cls, p, who = e.get("event_class"), e.get("payload") or {}, e.get("agent_id")
        t = _t(e, t0)
        if t is None:
            continue
        seq = e.get("sequence_number")
        if cls == "message.sent" and p.get("kind") == "note" and who in known and p.get("to") in known:
            out.append({"t": t, "seq": seq, "from": who, "to": p["to"], "kind": "note"})
        elif cls == "handoff":
            a, b = p.get("from_agent") or who, p.get("to_agent")
            if a in known and b in known and a != b:
                out.append({"t": t, "seq": seq, "from": a, "to": b, "kind": "handoff"})
        elif cls == "board.posted" and who in known:
            out.append({"t": t, "seq": seq, "from": who, "to": BOARD, "kind": "post"})
    for row in exchanges:
        t = ts_of.get(row.get("seq"))
        if t is None or row.get("from") not in known:
            continue
        for to in row.get("to") or []:
            if to in known and to != row["from"]:
                out.append({"t": t, "seq": row.get("seq"), "from": row["from"], "to": to,
                            "kind": row.get("kind") or "exchange"})
    out.sort(key=lambda a: (a["t"], a["seq"] or 0))
    return out


_TEXT_CAP = 4000  # characters of one message carried into the page; the Story has the rest


def messages(events: list[dict], exchanges: list[dict], agents: list[str], t0: float) -> list[dict]:
    """Every message in time order, one entry per message with all its recipients and its
    text: ``{t, seq, event_id, from, to: [...], kind, text}``. Notes, posts to the board,
    handoffs (a handoff broadcast to several roles, the same work product in a row, is
    one message), and the task's registered exchanges. The text is what was recorded."""
    known = set(agents)
    ts_of = {e.get("sequence_number"): (_t(e, t0), e.get("event_id")) for e in events}
    out: list[dict] = []
    for e in events:
        cls, p, who = e.get("event_class"), e.get("payload") or {}, e.get("agent_id")
        t = _t(e, t0)
        if t is None:
            continue
        base = {"t": t, "seq": e.get("sequence_number"), "event_id": e.get("event_id")}
        if cls == "message.sent" and p.get("kind") == "note" and who in known and p.get("to") in known:
            out.append({**base, "from": who, "to": [p["to"]], "kind": "note",
                        "text": str(p.get("payload_text") or p.get("text") or "")[:_TEXT_CAP]})
        elif cls == "board.posted" and who in known:
            out.append({**base, "from": who, "to": [BOARD], "kind": "post",
                        "text": str(p.get("text") or "")[:_TEXT_CAP]})
        elif cls == "handoff":
            a, b = p.get("from_agent") or who, p.get("to_agent")
            if a not in known or b not in known or a == b:
                continue
            ref = (p.get("handoff_delta") or {}).get("formalized_payload_ref") or ""
            last = out[-1] if out else None
            if last and last["kind"] == "handoff" and last["from"] == a and last.get("ref") == ref and ref:
                if b not in last["to"]:
                    last["to"].append(b)  # the same work product broadcast: one message
                continue
            out.append({**base, "from": a, "to": [b], "kind": "handoff", "ref": ref,
                        "text": ((ref + "\n") if ref else "") + str(p.get("payload_text") or "")[:_TEXT_CAP]})
    for row in exchanges:
        t, eid = ts_of.get(row.get("seq"), (None, None))
        to = [x for x in (row.get("to") or []) if x in known and x != row.get("from")]
        if t is None or row.get("from") not in known or not to:
            continue
        out.append({"t": t, "seq": row.get("seq"), "event_id": row.get("event_id") or eid,
                    "from": row["from"], "to": to, "kind": row.get("kind") or "exchange",
                    "text": str(row.get("text") or "")[:_TEXT_CAP]})
    out.sort(key=lambda m: (m["t"], m["seq"] or 0))
    for m in out:
        m.pop("ref", None)
    return out


def replay_data(events: list[dict], exchanges: list[dict], agents: list[str]) -> dict:
    """What the replay page animates, as JSON-able data."""
    stamped = [e for e in events if isinstance(e.get("timestamp"), (int, float))]
    if not stamped:
        return {"timed": False, "n_events": len(events), "duration": 0, "agents": agents, "busy": {},
                "acts": [], "messages": [], "days": [], "nodes": [], "w": 0, "h": 0}
    t0 = stamped[0]["timestamp"]
    span = stamped[-1]["timestamp"] - t0
    duration = max(round(span, 2), 1.0)  # a timeline needs some length
    g = graph(events, exchanges, agents)
    days = [{"t": _t(e, t0), "day": (e.get("payload") or {}).get("round_no")}
            for e in stamped if e.get("event_class") == "clock.round"]
    return {"timed": True, "n_events": len(events), "span_s": round(span, 3), "duration": duration, "agents": agents, "busy": busy_intervals(events, agents, t0),
            "acts": acts(events, exchanges, agents, t0), "messages": messages(events, exchanges, agents, t0),
            "days": days,
            "nodes": g["nodes"], "w": g["w"], "h": g["h"]}
