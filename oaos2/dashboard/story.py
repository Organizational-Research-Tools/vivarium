"""The run's story (DASHBOARD.md §4.2a): the organization's life in order, in the
agents' own words, read straight from the record.

The board is the spine — every post is a card in sequence — with private notes and
handoffs as asides between the posts they sit among, each agent's own narration between them,
the task's turning points as milestones, and problems always visible. One depth
control decides how much surrounds the forum. Nothing here is inferred: every item is
one recorded event (or one registered pack row) in writer order; the agent filter is
a cut, not a reconstruction of what an agent knew.
"""

from __future__ import annotations

from oaos2.dashboard.events import _fold, family_of

STORY_DEPTHS = ("forum", "notes", "said", "everything")
_PAGE = 400

# item kind → the shallowest depth that shows it (problems at every depth)
_KIND_DEPTH = {"post": 0, "milestone": 0, "problem": 0, "lifecycle": 0,
               "note": 1, "handoff": 1, "notice": 1,
               "said": 2, "exchange": 2,
               "thinking": 3, "tool": 3, "result": 3, "relay": 3}

_LIFECYCLE = {"agent.launched": "joined the run", "agent.retired": "retired",
              "run.completed": "run completed", "run.failed": "run failed",
              "outcome.closed": "outcome closed"}


def story_items(events: list[dict], *, exchanges: list[dict], milestones: list[dict],
                depth: str, agent: str | None = None, is_audit_class=None,
                fold: bool = True) -> list[dict]:
    """Every story item at or above ``depth``, in writer order. ``agent`` keeps the
    shared forum and everything that touches that agent. ``fold=False`` keeps each
    exchange its own item (the live feed appends by position, so a run folded across
    two polls would hide its later members)."""
    if is_audit_class is None:
        from oaos2.dashboard.store import is_audit_class
    max_depth = STORY_DEPTHS.index(depth if depth in STORY_DEPTHS else "notes")
    items: list[dict] = []

    def add(kind, e, who, text, *, to=None, title=None, seq=None):
        if _KIND_DEPTH[kind] > max_depth:
            return
        if agent and kind not in ("post", "problem", "milestone") and who is not None \
                and who != agent and agent not in (to or []):
            return  # a run-level item (no agent) belongs to everyone's story
        if agent and kind == "milestone" and who not in (agent, "lab", None):
            return
        if agent and kind == "notice" and agent not in (to or []):
            return  # a notice belongs to the role it was sent to
        body, folded = _fold(text or "")
        items.append({"kind": kind, "e": e, "who": who, "to": to or [], "title": title,
                      "text": body, "folded": folded,
                      "seq": seq if seq is not None else (e or {}).get("sequence_number") or 0})

    for e in events:
        cls = e.get("event_class") or "?"
        p = e.get("payload") or {}
        who = e.get("agent_id")
        if cls == "board.posted":
            add("post", e, who, p.get("text"), to=list(p.get("recipients") or []),
                title=f"#{p.get('seq')}")
        elif cls == "message.sent":
            to = [p.get("to")] if p.get("to") else []
            text = p.get("payload_text") or p.get("text") or ""
            if p.get("kind") == "note":
                add("note", e, who, text, to=to)
            else:
                add("relay", e, who or "·", text, to=to, title=p.get("kind"))
        elif cls == "handoff":
            ref = (p.get("handoff_delta") or {}).get("formalized_payload_ref")
            to = [p.get("to_agent")] if p.get("to_agent") else []
            add("handoff", e, p.get("from_agent") or who, p.get("payload_text") or "", to=to,
                title=ref or p.get("kind"))
        elif cls == "environment.event":
            ee = p.get("environment_event") or {}
            pl = ee.get("payload") if isinstance(ee.get("payload"), dict) else {}
            role = ee.get("target_role_id") or who
            label = " · ".join(str(x) for x in (pl.get("case_id"), pl.get("notice_id") or ee.get("packet_id"))
                               if x)
            add("notice", e, None, pl.get("text") or "", to=[role] if role else [], title=label or None)
        elif cls == "clock.round":
            add("lifecycle", e, None, f"day {p.get('round_no')} opens"
                + (f" of {p.get('rounds_total')}" if p.get("rounds_total") else ""))
        elif cls == "capacity.deadline_lapse":
            add("milestone", e, who, f"case {p.get('case_id')} passed its deadline unresolved"
                + (" (closed by the platform)" if p.get("forced") else ""), title="deadline lapse")
        elif cls == "context.compaction":
            add("lifecycle", e, who, f"{who}'s context was compacted: earlier material was "
                "summarized or dropped from what its model sees")
        elif cls == "reasoning.step":
            if p.get("narration"):
                add("said", e, who, p.get("narration"))
            if p.get("thinking"):
                add("thinking", e, who, p.get("thinking"))
        elif cls == "tool.called":
            args = p.get("arguments") or p.get("args") or {}
            add("tool", e, who, str(args)[:600] if args else "", title=p.get("tool_name"))
        elif cls == "tool.result":
            add("result", e, who, (p.get("output") or p.get("text") or "")[:1400], title=p.get("tool_name"))
        elif cls == "state.committed":
            sc = p.get("state_commitment") or {}
            add("milestone", e, sc.get("agent_id") or who, f"submitted {sc.get('commitment_id')}")
        elif cls == "intervention.recorded":
            add("milestone", e, who or "platform", f"platform intervened: {p.get('kind')}",
                title="intervention")
        elif cls in _LIFECYCLE:
            reason = f" ({p.get('reason')})" if p.get("reason") else ""
            add("lifecycle", e, who, f"{who or 'run'} {_LIFECYCLE[cls]}{reason}")
        elif is_audit_class(cls) and e.get("audience") != "infrastructure":
            add("problem", e, who, p.get("reason") or p.get("error") or "", title=cls)
    for row in exchanges:
        add("exchange", {"event_id": row["event_id"], "sequence_number": row["seq"]},
            row["from"], row["text"], to=row["to"], title=row["kind"])
    for row in milestones:
        add("milestone", {"event_id": row["event_id"], "sequence_number": row["seq"]},
            row["from"], row["text"], to=row["to"], title=row["kind"].split(".", 1)[-1])
    items.sort(key=lambda it: (it["seq"], (it["e"] or {}).get("event_id") or ""))
    return _fold_exchange_runs(items) if fold else items


_OWN_STEPS = ("said", "thinking", "tool", "result")  # an agent's own steps between its acts


def _fold_exchange_runs(items: list[dict]) -> list[dict]:
    """Consecutive exchanges of one kind by one agent to the same recipients read as
    one line with a count (a lab granting twelve prototypes in a row is one act to a
    reader). "Consecutive" allows the same agent's own steps in between (what it said,
    its tool calls), which a burst of grants interleaves; anything by another role, or
    any other kind of item, ends the run. Each folded row keeps its members' texts."""
    out: list[dict] = []
    open_at: dict[tuple, int] = {}  # (who, to, title) -> index of the exchange row still open
    for it in items:
        if it["kind"] == "exchange":
            key = (it["who"], tuple(it["to"]), it["title"])
            i = open_at.get(key)
            if i is not None:
                row = out[i]
                row.setdefault("members", [row["text"]]).append(it["text"])
                row["n"] = len(row["members"])
                row["last_seq"] = it["seq"]
                continue
            open_at = {k: v for k, v in open_at.items() if k[0] == it["who"]}
            open_at[key] = len(out)
            out.append(dict(it))
            continue
        if not (it["kind"] in _OWN_STEPS and open_at and all(k[0] == it["who"] for k in open_at)):
            open_at = {}  # someone else acted, or something other than the agent's own steps
        out.append(dict(it))
    for it in out:
        if it["kind"] == "exchange" and it.get("n", 1) > 1:
            it["text"] = f"{it['n']}× — " + "; ".join(it["members"][:6]) + ("; …" if it["n"] > 6 else "")
    return out


def paginate(items: list[dict], page: int) -> tuple[list[dict], int]:
    pages = max(1, (len(items) + _PAGE - 1) // _PAGE)
    page = min(max(page, 1), pages)
    return items[(page - 1) * _PAGE: page * _PAGE], pages


def counts(items: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for it in items:
        out[it["kind"]] = out.get(it["kind"], 0) + 1
    return out


__all__ = ["STORY_DEPTHS", "story_items", "paginate", "counts", "family_of"]
