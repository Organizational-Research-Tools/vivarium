"""Event-detail renderer registry (DASHBOARD.md §5) — open, never enumerated in views.

Mirrors the platform's open registries: a pack (or a researcher) may register a
renderer for its own event classes; anything unregistered falls back to the raw
payload JSON the inspector always shows. A renderer extracts the event's *notable
text* — the human-readable segments an ethnographic reader wants without digging
into the payload tree (the verbatim utterance, the thinking, the handoff body).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from oaos2.dashboard import events as ev

# renderer: (run_dir, event) -> [(label, text), ...]; empty list = nothing notable
Renderer = Callable[[Path, dict], list[tuple[str, str]]]

_RENDERERS: dict[str, Renderer] = {}


def register(event_class: str, renderer: Renderer, *, override: bool = False) -> None:
    if event_class in _RENDERERS and not override:
        raise ValueError(f"renderer for {event_class!r} already registered (pass override=True)")
    _RENDERERS[event_class] = renderer


def notable_text(run_dir: Path, event: dict) -> list[tuple[str, str]]:
    """The registered renderer's segments for this event ([] when none/unregistered)."""
    renderer = _RENDERERS.get(event.get("event_class") or "")
    if renderer is None:
        return []
    segments = renderer(Path(run_dir), event)
    return [(label, text) for label, text in segments if text]


# --- foundation renderers (the closed record set the core always understands) - #

def _payload_texts(*keys: str) -> Renderer:
    def _render(run_dir: Path, event: dict) -> list[tuple[str, str]]:
        p = event.get("payload") or {}
        return [(k, p.get(k)) for k in keys if isinstance(p.get(k), str)]
    return _render


def _model_prose(run_dir: Path, event: dict) -> list[tuple[str, str]]:
    return [("verbatim prose (raw/)", ev.prose_for(run_dir, event))]


register("model.responded", _model_prose)
register("reasoning.step", _payload_texts("thinking"))
register("conversation.volley", _payload_texts("text"))
register("message.sent", _payload_texts("payload_text", "text", "body"))
register("handoff", _payload_texts("payload_text", "narration"))
register("chat.requested", _payload_texts("text"))
register("chat.response", _payload_texts("text"))
register("chat.declined", _payload_texts("reason"))
register("agent.failed", _payload_texts("error"))
register("protocol.violation", _payload_texts("reason"))
register("run.failed", _payload_texts("reason"))
