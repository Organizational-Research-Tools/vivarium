"""Render readable transcripts from saved events, without rerunning agents.

clean selects events marked for agent audiences; it is not proof that every
agent saw each selected event. full includes both experiment and infrastructure
streams in sequence-number order. agent_centric groups events by agent.
File history is rendered separately by lineage.py.

The same saved inputs and rendering code produce identical text. Transcripts
omit advisory timestamps and use the writer's sequence numbers for order."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from oaos2.trace.invariants import load_all_events


def _load_raw(run_dir: Path, ref: str | None) -> dict | None:
    """Read a content-addressed raw provider payload (``raw/<hash>``), or None."""
    if not ref or "/" not in ref:
        return None
    path = Path(run_dir) / "raw" / f"{ref.split('/', 1)[1]}.json.gz"
    if not path.exists():
        return None
    try:
        with gzip.open(path, "rb") as f:
            return json.loads(f.read())
    except (OSError, ValueError):
        return None


def _extract_prose(raw: dict) -> str:
    """The model's verbatim text from a raw payload — provider-shape aware, single-line.

    Anthropic puts text in ``content[].text``; OpenAI in ``choices[0].message.content``.
    Collapsed to one line so the transcript stays a deterministic line-per-utterance."""
    texts = [b.get("text", "") for b in (raw.get("content") or [])
             if isinstance(b, dict) and b.get("type") == "text"]
    if not texts:
        choices = raw.get("choices") or []
        content = (choices[0].get("message") or {}).get("content") if choices else None
        if isinstance(content, str):
            texts = [content]
        elif isinstance(content, list):  # OpenAI multimodal/parts shape: list of part dicts
            texts = [p.get("text", "") for p in content
                     if isinstance(p, dict) and p.get("type") in ("text", "output_text")]
    return " ".join(" ".join(t for t in texts if t).split())


def events_in_order(run_dir: Path) -> list[dict]:
    """All events (spine + infra) in the single writer-assigned total order."""
    evs = load_all_events(run_dir)
    return sorted(evs, key=lambda e: (e.get("sequence_number") if e.get("sequence_number") is not None else -1))


# --- per-event one-line summary (shared by the transcripts) ---------------- #

def _summary(e: dict) -> str:
    """A compact, deterministic one-liner for an event's salient payload."""
    p = e.get("payload") or {}
    cls = e.get("event_class", "?")
    if cls == "agent.observed":
        obs = p.get("observations") or []
        kinds = ",".join(o.get("kind", "?") for o in obs) if obs else "—"
        return f"observed [{kinds}]"
    if cls in ("tool.called", "tool.result"):
        return f"{p.get('tool_name', '?')}"
    if cls == "tool.denied":
        return f"{p.get('tool_name', '?')} DENIED ({p.get('reason', '?')})"
    if cls in ("conversation.volley",):
        return f"{p.get('speaker', '?')}: {p.get('text', '')!r}"
    if cls in ("conversation.opened", "conversation.closed"):
        extra = p.get("reason") or ",".join(p.get("participants", []))
        return f"{p.get('conversation_id', '')} {extra}".strip()
    if cls in ("chat.requested", "chat.response", "chat.declined", "chat.ignored"):
        return f"{p.get('text') or p.get('reason') or p.get('paused_turn_id', '')}"
    if cls == "handoff":
        return f"{p.get('from_agent', '?')}→{p.get('to_agent', '?')} ({p.get('kind', '?')})"
    if cls == "message.sent":
        return f"→{p.get('to', '?')} ({p.get('kind', '?')})"
    if cls == "board.posted":
        return f"board #{p.get('seq', '?')} → {len(p.get('recipients') or [])}: {(p.get('text') or '')[:60]!r}"
    if cls == "board.retrieved":
        if p.get("view") == "index":  # the forum board (October 10, 2026)
            return f"read board index (page {p.get('page', 1)})"
        return f"{'opened board ' + p['view'] if p.get('view') else 'read board'} ({p.get('count', 0)})"
    if cls == "notes.retrieved":
        return f"read notes ({p.get('count', 0)})"
    if cls == "state.committed":
        sc = p.get("state_commitment") or {}
        return f"commit {sc.get('commitment_id', '?')}"
    if cls == "outcome.closed":
        return f"outcome {p.get('outcome_id', '?')} CLOSED"
    if cls == "intervention.recorded":
        return f"{p.get('kind', '?')} [{p.get('class', '?')}]"
    if cls == "protocol.violation":
        return f"VIOLATION {p.get('reason', '?')}"
    if cls in ("turn.started", "turn.completed", "action.started", "action.completed"):
        return p.get("result", "")
    if cls == "model.responded":
        u = p.get("usage") or {}
        return f"stop={p.get('stop_reason', '?')} in={u.get('input', 0)} out={u.get('output', 0)}"
    if cls == "cost.recorded":
        return f"${p.get('cost_usd', 0):.4f}"
    return ""


def _line(e: dict) -> str:
    seq = e.get("sequence_number")
    who = e.get("agent_id") or "·"
    turn = e.get("turn_id") or ""
    s = _summary(e)
    tail = f" — {s}" if s else ""
    return f"[{seq:>5}] {who:<10} {e.get('event_class', '?'):<22} {turn}{tail}".rstrip()


# --- the three event-based transcripts ------------------------------------- #

def render_clean(run_dir: Path, events: list[dict] | None = None) -> str:
    """The agent-facing conversation: ``audience: agent`` events interleaved with each
    agent's verbatim model utterance (folded from ``raw/`` when retained) — §17.3.
    ``events`` may be preloaded (avoids re-reading the stream per transcript)."""
    head = ["# Clean transcript (agent-facing conversation)",
            "# audience=agent events + the agent's verbatim model prose (from raw/).", ""]
    lines: list[str] = []
    for e in (events if events is not None else events_in_order(run_dir)):
        if e.get("event_class") == "model.responded":
            prose = _extract_prose(_load_raw(run_dir, (e.get("payload") or {}).get(
                "raw_provider_response_ref")) or {})
            if prose:
                seq, who = e.get("sequence_number"), e.get("agent_id") or "·"
                lines.append(f'[{seq:>5}] {who:<10} says: "{prose}"')
            continue  # the telemetry line itself (researcher audience) stays out of clean
        if e.get("audience") == "agent":
            lines.append(_line(e))
    return "\n".join(head + lines) + "\n"


def render_full(run_dir: Path, events: list[dict] | None = None) -> str:
    """Every event in total order, infra included — the complete trace (§17.3)."""
    evs = events if events is not None else events_in_order(run_dir)
    head = ["# Full transcript (every event, sequence order)", ""]
    return "\n".join(head + [_line(e) for e in evs]) + "\n"


def render_agent_centric(run_dir: Path, events: list[dict] | None = None) -> str:
    """One section per agent, that agent's events in order (§17.3)."""
    evs = events if events is not None else events_in_order(run_dir)
    agents: list[str] = []
    for e in evs:  # preserve first-seen order, deterministic
        a = e.get("agent_id")
        if a and a not in agents:
            agents.append(a)
    out = ["# Agent-centric transcript", ""]
    for a in agents:
        out.append(f"## agent: {a}")
        out += [_line(e) for e in evs if e.get("agent_id") == a]
        out.append("")
    return "\n".join(out) + "\n"
