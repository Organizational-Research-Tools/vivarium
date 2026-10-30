"""The Agents view (DASHBOARD.md §4.2d): one profile per role, from the record.

What a role was (its packet, tier, first duty, and instructions), what reached it
(notes, posts by others, exchanges naming it), what it did (posts, notes, exchanges,
submissions, tool calls by name), what it cost, and what went wrong around it.
Every number is a count over recorded events; "received" means delivered, not read.
"""

from __future__ import annotations

from collections import Counter

from oaos2.dashboard.store import is_audit_class


def profiles(events: list[dict], exchanges: list[dict], design: dict, agents: list[str],
             milestones: list[dict] = ()) -> list[dict]:
    """``submissions`` counts commitments the commit path accepted (in some tasks those
    are credits, not every report filed); ``milestones`` counts the task's registered
    turning points by the role, by kind, so a filed report or a concern shows as itself."""
    envelopes = design.get("envelopes") or {}
    roles = design["organization"]["roles"]
    out: dict[str, dict] = {}

    def prof(a: str) -> dict:
        if a not in out:
            env = envelopes.get(a) or {}
            role = roles.get(a) or {}
            out[a] = {"agent": a, "packet": env.get("role_packet") or role.get("role_packet"),
                      "tier": env.get("tier"), "first_duty": env.get("commitment"),
                      "comm_grants": role.get("comm_grants") or [], "tools": role.get("tools") or [],
                      "model": role.get("model_ref"),
                      "calls": 0, "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0,
                      "posts": 0, "notes_out": 0, "notes_in": 0, "posts_received": 0,
                      "exchanges_out": Counter(), "exchanges_in": Counter(),
                      "submissions": 0, "milestones": Counter(), "tool_calls": Counter(), "problems": [],
                      "retired": None, "compactions": 0}
        return out[a]

    for a in agents:
        prof(a)
    for e in events:
        cls, p, who = e.get("event_class"), e.get("payload") or {}, e.get("agent_id")
        if cls == "model.responded" and who:
            u = p.get("usage") or {}
            pr = prof(who)
            pr["calls"] += 1
            pr["input_tokens"] += u.get("input", 0) or 0
            pr["output_tokens"] += u.get("output", 0) or 0
        elif cls == "cost.recorded" and who:
            prof(who)["cost_usd"] += p.get("cost_usd", 0.0) or 0.0
        elif cls == "board.posted" and who:
            prof(who)["posts"] += 1
            for r in p.get("recipients") or []:
                prof(r)["posts_received"] += 1
        elif cls == "message.sent" and p.get("kind") == "note" and who and p.get("to"):
            prof(who)["notes_out"] += 1
            prof(p["to"])["notes_in"] += 1
        elif cls == "tool.called" and who:
            prof(who)["tool_calls"][p.get("tool_name") or "?"] += 1
        elif cls == "state.committed":
            sc = p.get("state_commitment") or {}
            if sc.get("agent_id") or who:
                prof(sc.get("agent_id") or who)["submissions"] += 1
        elif cls == "agent.retired" and who:
            prof(who)["retired"] = p.get("reason") or "retired"
        elif cls == "context.compaction" and who:
            prof(who)["compactions"] += 1
        elif who and cls and is_audit_class(cls) and e.get("audience") != "infrastructure":
            prof(who)["problems"].append({"cls": cls, "event_id": e.get("event_id"),
                                          "seq": e.get("sequence_number"),
                                          "text": p.get("reason") or p.get("error") or ""})
    for row in milestones:
        if row.get("from") in out or row.get("from") in roles:
            prof(row["from"])["milestones"][row.get("kind") or "milestone"] += 1
    for row in exchanges:
        if row.get("from"):
            prof(row["from"])["exchanges_out"][row.get("kind") or "exchange"] += 1
        for to in row.get("to") or []:
            prof(to)["exchanges_in"][row.get("kind") or "exchange"] += 1
    ordered = [out[a] for a in agents if a in out] + [v for k, v in sorted(out.items()) if k not in agents]
    # A platform pseudo-role (the coordinator that closes the run) is not an agent of the
    # organization: it is kept only when the preset declares it or it ever spoke or called.
    ordered = [pr for pr in ordered if pr["agent"] in roles or pr["calls"] or pr["posts"] or pr["posts_received"]
               or pr["notes_out"] or pr["notes_in"] or pr["exchanges_out"] or pr["exchanges_in"]]
    for pr in ordered:
        pr["exchanges_out"] = dict(sorted(pr["exchanges_out"].items()))
        pr["exchanges_in"] = dict(sorted(pr["exchanges_in"].items()))
        pr["tool_calls"] = dict(pr["tool_calls"].most_common())
        pr["milestones"] = dict(sorted(pr["milestones"].items()))
        pr["cost_usd"] = round(pr["cost_usd"], 4)
    return ordered
