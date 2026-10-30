"""Logical-time projection over an archive (DASHBOARD.md §4.3; clock_design.md).

Day membership is not stamped on events: it is an event's position relative to
the ``clock.round`` markers the runtime emits.  This is the ONE place that rule
lives — the pack scorer (``_clocked_meta``), the dashboard's day headers and
ledger, and the citation format all take the day from here, so a commit can
never belong to one day in the report and another on the page.

Day 0 is everything before the first round opens (setup: launches, the first
observations); an archive without ``clock.round`` events has no days at all
(``day_index`` returns an empty map, ``rounds_total`` None).
"""

from __future__ import annotations


def day_index(events: list[dict]) -> dict[str, int]:
    """``event_id → day`` over the total-ordered stream (0 before the first round)."""
    out: dict[str, int] = {}
    day = 0
    seen = False
    for e in events:
        if e.get("event_class") == "clock.round":
            seen = True
            day = int((e.get("payload") or {}).get("round_no", day))
        eid = e.get("event_id")
        if eid:
            out[eid] = day
    return out if seen else {}


def day_spans(events: list[dict]) -> list[dict]:
    """One entry per day actually opened: ``{day, seq_start, seq_end, n_events,
    round_event_id}`` in day order, plus a day-0 span when setup events precede
    the first round.  Empty when the archive is not clocked."""
    spans: list[dict] = []
    current: dict | None = None
    for e in events:
        seq = e.get("sequence_number") or 0
        if e.get("event_class") == "clock.round":
            if current is not None:
                spans.append(current)
            current = {"day": int((e.get("payload") or {}).get("round_no", 0)),
                       "seq_start": seq, "seq_end": seq, "n_events": 0,
                       "round_event_id": e.get("event_id")}
        elif current is None:
            current = {"day": 0, "seq_start": seq, "seq_end": seq, "n_events": 0,
                       "round_event_id": None}
        current["seq_end"] = seq
        current["n_events"] += 1
    if current is not None and any(s["round_event_id"] for s in spans + [current]):
        spans.append(current)
        return spans
    return []


def rounds_total(events: list[dict]) -> int | None:
    for e in events:
        if e.get("event_class") == "clock.round":
            rt = (e.get("payload") or {}).get("rounds_total")
            return int(rt) if rt is not None else None
    return None


def final_day(events: list[dict]) -> int | None:
    days = [int((e.get("payload") or {}).get("round_no", 0)) for e in events
            if e.get("event_class") == "clock.round"]
    return max(days) if days else None
