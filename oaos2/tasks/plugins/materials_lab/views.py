"""The materials workshop's live standings panel for the dashboard's live page (moved from
``oaos2/dashboard/live.py``, October 29, 2026, so that the engine names no task). ``derived.py`` registers it.
"""

from __future__ import annotations

import json
import re

_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


def stated_rule(events: list[dict]) -> dict:
    """The credit rule as the labs were told it in their start note, for runs whose ``lab.staged``
    predates recording it (before September 26, 2026, evening)."""
    for e in events:
        if e.get("event_class") != "agent.observed":
            continue
        text = json.dumps(e.get("payload") or {})
        m = re.search(r"Failure rule: at the deadline, the (\w+) laboratories with the most credits succeed, "
                      r"if each holds at least (\d+) credits", text)
        if m and m.group(1) in _WORDS:
            return {"allocation": "divisible", "success_cap": _WORDS[m.group(1)], "success_floor": int(m.group(2))}
        m = re.search(r"Failure rule: the organization fails unless it holds (\d+) ", text)
        if m:
            return {"credit_threshold": int(m.group(1))}
    return {}


def standings(events: list[dict]) -> dict | None:
    """The credit standings of a run whose task records credits (the materials lab's institutions):
    credits per lab, who would succeed now, and each credit event with its minute, read from the
    events the pool records (``credit.allocated`` under divisible credit, ``credit.awarded`` otherwise,
    ``credit.voided``, dismissals). None for a run that records no institution. The rule's parameters
    come from ``lab.staged`` where the run recorded them (runs from September 26, 2026 on)."""
    staged = next((e for e in events if e.get("event_class") == "lab.staged"), None)
    if staged is None or not (staged.get("payload") or {}).get("institution"):
        return None
    sp = dict(staged["payload"])
    from_note = False
    if sp.get("success_floor") is None and sp.get("credit_threshold") is None:
        for k, v in stated_rule(events).items():
            sp[k], from_note = v, True
    t0 = min((e.get("timestamp") or 0) for e in events if e.get("event_class") == "lab.staged")
    labs = sorted({e.get("agent_id") for e in events if e.get("event_class") == "lab.staged" and e.get("agent_id")})
    minute = lambda e: round(((e.get("timestamp") or t0) - t0) / 60, 1)  # noqa: E731
    by_report: dict = {}
    order: list = []
    dismissed: set = set()
    for e in events:
        c, p = e.get("event_class"), e.get("payload") or {}
        if c == "credit.allocated":  # the divisible split replaces the one credit ``credit.awarded`` recorded
            if p.get("report_id") not in by_report:
                order.append(p.get("report_id"))
            old = by_report.get(p.get("report_id")) or {}
            by_report[p.get("report_id")] = {"minute": minute(e), "project": p.get("project_id"),
                                             "submitter": p.get("submitter"), "credits": dict(p.get("credits") or {}),
                                             "voided": False, "lapsed": False, "margin": old.get("margin")}
        elif c == "credit.awarded" and p.get("report_id") not in by_report:
            by_report[p.get("report_id")] = {"minute": minute(e), "project": p.get("project_id"),
                                             "submitter": e.get("agent_id"), "credits": {e.get("agent_id"): 1},
                                             "voided": False, "lapsed": False, "margin": p.get("margin")}
            order.append(p.get("report_id"))
        elif c == "credit.voided" and p.get("report_id") in by_report:
            by_report[p["report_id"]]["voided"] = True
            by_report[p["report_id"]]["voided_minute"] = minute(e)
        elif c == "credit.lapsed" and p.get("report_id") in by_report:  # the contest form: displaced, or a revision
            by_report[p["report_id"]].update(lapsed=True, lapsed_minute=minute(e), displaced_by=p.get("displaced_by"),
                                             lapse_reason=p.get("reason") or "displaced")
        elif c == "credit.restored" and p.get("report_id") in by_report:
            by_report[p["report_id"]].update(lapsed=False, restored=True)
        elif c == "agent.retired" and p.get("reason") == "dismissed":
            dismissed.add(e.get("agent_id"))
    totals = {lab: 0 for lab in labs}
    reached: dict = {}
    step = 0
    for rid in order:  # running totals over standing reports, for the tie rule's order
        r = by_report[rid]
        if r["voided"] or r["lapsed"]:
            continue
        for lab, n in r["credits"].items():
            totals[lab] = totals.get(lab, 0) + n
            step += 1  # report order, then the order of the report's credits (submitter first)
            reached[lab] = (step, r["minute"])
    reports = [by_report[rid] for rid in order]
    standing = [r for r in reports if not r["voided"] and not r["lapsed"]]
    if sp.get("program_lines"):  # the contest form (September 29, 2026): a qualified project in each product line
        target = len((sp.get("family_types") or {}) or {"a": 0, "b": 0, "g": 0})
        qualified = len({str(r["project"])[:1] for r in standing})  # project ids begin with their family's letter
        label = "product lines with a qualified project"
    else:
        target = sp.get("program_target")  # the program form (September 27, 2026): nobody succeeds below it
        qualified = len({r["project"] for r in standing})
        label = "projects qualified"
    program = ({"qualified": qualified, "target": target, "label": label,
                "pct": round(100 * min(qualified, target) / target)} if target else None)
    if sp.get("institution") == "cooperative":
        got = len({r["project"] for r in standing})
        return {"kind": "progress", "credits": got, "threshold": None if program else sp.get("credit_threshold"),
                "program": program, "reports": reports, "dismissed": sorted(dismissed), "from_note": from_note}
    floor, cap = sp.get("success_floor"), sp.get("success_cap")
    ranked = sorted((lab for lab in totals if lab not in dismissed),
                    key=lambda lab: (-totals[lab], reached.get(lab, (10 ** 9,))[0], lab))
    succeeding = [lab for lab in ranked[:cap] if floor is not None and totals[lab] >= floor] if cap else []
    if target and qualified < target:
        succeeding = []
    top = max(list(totals.values()) + [floor or 0, 1])
    rows = [{"lab": lab, "credits": totals[lab], "succeeding": lab in succeeding, "dismissed": lab in dismissed,
             "pct": round(100 * totals[lab] / top)} for lab in ranked + sorted(dismissed)]
    return {"kind": "leaderboard", "rows": rows, "floor": floor, "cap": cap,
            "floor_pct": round(100 * floor / top) if floor else None, "reports": reports,
            "allocation": sp.get("allocation"), "from_note": from_note, "program": program}
