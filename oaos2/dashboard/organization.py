"""The Organization view (DASHBOARD.md §4.2b): who is here, what each role may do,
and who dealt with whom — drawn from the recorded interactions, not from prose.

The graph counts directed acts between roles: notes, handoffs, and the pack's
registered exchanges; posts go to the board, drawn as a hub. Counts are what was
recorded; an edge says nothing about whether anything was read or understood.
Geometry is computed here so the template draws and never decides.
"""

from __future__ import annotations

import math

BOARD = "board"
_W, _H, _R = 640, 360, 130


def interaction_counts(events: list[dict], exchanges: list[dict], agents: list[str]) -> dict:
    """``{(from, to): {kind: n}}`` over notes, handoffs, exchanges, and posts to the board."""
    counts: dict[tuple[str, str], dict[str, int]] = {}

    def bump(a, b, kind):
        if not a or not b or a == b:
            return
        counts.setdefault((a, b), {})
        counts[(a, b)][kind] = counts[(a, b)].get(kind, 0) + 1

    for e in events:
        cls, p = e.get("event_class"), e.get("payload") or {}
        if cls == "message.sent" and p.get("kind") == "note":
            bump(e.get("agent_id"), p.get("to"), "notes")
        elif cls == "handoff":
            bump(p.get("from_agent") or e.get("agent_id"), p.get("to_agent"), "handoffs")
        elif cls == "board.posted":
            bump(e.get("agent_id"), BOARD, "posts")
    for row in exchanges:
        for to in row.get("to") or []:
            bump(row.get("from"), to, row.get("kind") or "exchange")
    return counts


def graph(events: list[dict], exchanges: list[dict], agents: list[str]) -> dict:
    """Nodes on a circle (the board at the center when anyone posted), one edge per
    ordered pair with its per-kind counts, widths scaled to the busiest edge."""
    roles = [a for a in agents if a != "coordination"] or list(agents)
    counts = interaction_counts(events, exchanges, roles)
    has_board = any(b == BOARD for _, b in counts)
    n = max(len(roles), 1)
    pos: dict[str, tuple[float, float]] = {}
    for i, a in enumerate(roles):
        ang = -math.pi / 2 + 2 * math.pi * i / n
        pos[a] = (_W / 2 + _R * math.cos(ang), _H / 2 + _R * math.sin(ang))
    if has_board:
        pos[BOARD] = (_W / 2, _H / 2)
    busiest = max((sum(v.values()) for v in counts.values()), default=1)
    edges = []
    for (a, b), kinds in sorted(counts.items()):
        if a not in pos or b not in pos:
            continue
        (x1, y1), (x2, y2) = pos[a], pos[b]
        total = sum(kinds.values())
        # bend each direction to its own side so A→B and B→A do not overlap
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy) or 1
        nx, ny = -dy / length, dx / length
        cx, cy = (x1 + x2) / 2 + nx * 24, (y1 + y2) / 2 + ny * 24
        # shorten toward the target so the arrowhead is not under the node
        tx, ty = x2 - dx / length * 22, y2 - dy / length * 22
        edges.append({"from": a, "to": b, "total": total,
                      "kinds": dict(sorted(kinds.items())),
                      "label": ", ".join(f"{n} {k}" for k, n in sorted(kinds.items())),
                      "path": f"M{x1:.1f},{y1:.1f} Q{cx:.1f},{cy:.1f} {tx:.1f},{ty:.1f}",
                      "lx": round((x1 + 2 * cx + x2) / 4, 1), "ly": round((y1 + 2 * cy + y2) / 4, 1),
                      "width": round(1 + 5 * total / busiest, 1)})
    nodes = [{"id": a, "x": round(x, 1), "y": round(y, 1), "board": a == BOARD} for a, (x, y) in pos.items()]
    return {"w": _W, "h": _H, "nodes": nodes, "edges": edges, "has_board": has_board,
            "n_edges": len(edges), "busiest": busiest}


def grant_matrix(design: dict) -> dict:
    """Roles × communication grants, plus each role's remaining tools."""
    roles = design["organization"]["roles"]
    grants = sorted({g for r in roles.values() for g in (r.get("comm_grants") or [])})
    rows = []
    for rid, r in roles.items():
        held = set(r.get("comm_grants") or [])
        rows.append({"role": rid, "cells": [g in held for g in grants],
                     "tools": [t for t in (r.get("tools") or []) if t not in held],
                     "packet": r.get("role_packet"), "channels_out": r.get("channels_out") or [],
                     "context": r.get("context_budget_tokens"), "calls": r.get("max_calls_per_slot"),
                     "model": r.get("model_ref")})
    return {"grants": grants, "rows": rows}
