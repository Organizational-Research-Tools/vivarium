"""The episode ledger (DASHBOARD.md §4.3d): roles × logical days for one run.

Each cell says what a role did that day — calls against the daily ceiling,
notices received, filings and dispositions committed, plans, compactions,
bounced submissions — with wave windows, plan checkpoints, and case fuses drawn
on the day axis from the pinned clock and schedule.  Idle days are visible as
idle.  Every glyph links into the flow filtered to that role and day.
Observables only, taken from the same day projection the scorer uses.
"""

from __future__ import annotations

from oaos2.archive.clock import day_index, day_spans, rounds_total


def build_ledger(events: list[dict], design: dict, items: list[dict]) -> dict | None:
    days_of = day_index(events)
    if not days_of:
        return None
    spans = day_spans(events)
    horizon = rounds_total(events) or max((s["day"] for s in spans), default=0)
    days = list(range(0, horizon + 1)) if any(s["day"] == 0 for s in spans) else list(range(1, horizon + 1))

    roles: list[str] = []
    for e in events:
        if e.get("event_class") in ("turn.started", "model.invoked") and e.get("agent_id"):
            if e["agent_id"] not in roles:
                roles.append(e["agent_id"])

    cells: dict[tuple[str, int], dict] = {}

    def cell(role: str, day: int) -> dict:
        if role not in roles:
            roles.append(role)
        return cells.setdefault((role, day), {"calls": 0, "arrivals": [], "filings": [], "dispositions": [],
                                              "plans": [], "compactions": 0, "races": 0, "ceilings": 0,
                                              "woke": False})

    for e in events:
        cls = e.get("event_class")
        role = e.get("agent_id")
        day = days_of.get(e.get("event_id"))
        if day is None:
            continue
        p = e.get("payload") or {}
        if cls == "turn.started" and role:
            cell(role, day)["woke"] = True
        elif cls == "model.invoked" and role:
            cell(role, day)["calls"] += 1
        elif cls == "environment.event":
            ee = p.get("environment_event") or {}
            target = ee.get("target_role_id") or role
            pl = ee.get("payload") if isinstance(ee.get("payload"), dict) else {}
            if target:
                cell(target, day)["arrivals"].append(pl.get("case_id") or ee.get("packet_id") or "?")
        elif cls == "context.compaction" and role:
            cell(role, day)["compactions"] += 1
        elif cls == "intervention.recorded" and role and p.get("kind") == "submission_nonconformant_retry":
            cell(role, day)["races"] += 1
        elif cls == "capacity.slot_ceiling" and role:
            cell(role, day)["ceilings"] += 1

    for it in items:
        for f in it.get("filings") or []:
            if f.get("agent") and f.get("day") is not None:
                filed = cell(f["agent"], f["day"])["filings"]
                if f["commitment_id"] not in filed:  # a quarter report files once for its cases
                    filed.append(f["commitment_id"])
        d = it.get("disposition")
        if d and d.get("agent") and d.get("day") is not None:
            cell(d["agent"], d["day"])["dispositions"].append(it["item_id"])
        for c in it.get("commitments") or []:
            if c.get("kind") == "plan" and c.get("agent") and c.get("day") is not None:
                cell(c["agent"], c["day"])["plans"].append(c["commitment_id"])
    # plans that belong to no item (initial/final plans, office plans): from the events
    for e in events:
        if e.get("event_class") != "state.committed":
            continue
        sc = (e.get("payload") or {}).get("state_commitment") or {}
        cid = sc.get("commitment_id") or ""
        role = sc.get("agent_id") or e.get("agent_id")
        day = days_of.get(e.get("event_id"))
        if not role or day is None:
            continue
        known = any(cid in (c.get("commitment_id") for c in it.get("commitments") or []) for it in items)
        if not known and cid:
            cell(role, day)["plans"].append(cid)

    # bands from the design: wave windows, checkpoints, fuses
    waves: dict[str, list[int]] = {}
    for p in (design.get("packets") or {}).values():
        ar = (p.get("classification") or {}).get("arrival_round")
        if ar is not None and p.get("wave"):
            waves.setdefault(p["wave"], []).append(int(ar))
    wave_bands = {w: (min(v), max(v)) for w, v in waves.items()}
    clock = design.get("clock") or {}
    checkpoints = {int(v): k for k, v in (clock.get("plan_deadline_rounds") or {}).items()}
    fuses: dict[int, list[str]] = {}
    for cid, cr in (clock.get("case_rounds") or {}).items():
        if isinstance(cr, dict) and cr.get("deadline") is not None:
            fuses.setdefault(int(cr["deadline"]), []).append(cid)
    # what the clock itself recorded: deadlines that passed unmet (by the day they were
    # recorded), and a platform wind-down, which censors the run
    lapses: dict[int, list[str]] = {}
    wind_down = None
    for e in events:
        cls, p = e.get("event_class"), e.get("payload") or {}
        if cls == "capacity.deadline_lapse":
            d = days_of.get(e.get("event_id"))
            what = p.get("case_id") or p.get("commitment_id") or "?"
            if d is not None:
                lapses.setdefault(d, []).append(what + (" (forced)" if p.get("forced") else ""))
        elif cls == "clock.wind_down" and wind_down is None:
            wind_down = {"from": p.get("from_round"), "to": p.get("to_round"), "reason": p.get("reason"),
                         "event_id": e.get("event_id")}
    day_meta = []
    for d in days:
        wave = next((w for w, (lo, hi) in wave_bands.items() if lo <= d <= hi), None)
        wound = bool(wind_down and wind_down["from"] is not None and d > int(wind_down["from"]))
        day_meta.append({"day": d, "wave": wave, "checkpoint": checkpoints.get(d),
                         "fuses": sorted(fuses.get(d, [])), "lapses": lapses.get(d, []),
                         "wound": wound,
                         "n_events": next((s["n_events"] for s in spans if s["day"] == d), 0)})
    rows = []
    for role in roles:
        rows.append({"role": role, "cells": [cells.get((role, d)) for d in days]})
    return {"days": day_meta, "rows": rows, "calls_per_day": design.get("cell", {}).get("calls_per_day"),
            "horizon": horizon, "wind_down": wind_down,
            "n_lapses": sum(len(v) for v in lapses.values())}
