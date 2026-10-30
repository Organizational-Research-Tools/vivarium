"""Build events using registered names and default visibility settings.

make_event() checks the active event-class registry, applies its default phase,
audience, and channel, and accepts explicit per-event overrides. It normalizes
causal references into caused_by_event_ids. The writer later assigns sequence
numbers; RunSpine handles durable submission."""

from __future__ import annotations

from oaos2.registry import Registry, RegistryError
from oaos2.trace.event_classes import (
    EVENT_CLASS_REGISTRY,
    PHASE_NAME_REGISTRY,
    EventClassDef,
)
from oaos2.trace.schema import Event


class ProtocolViolation(Exception):
    """An emission that violates the envelope/registry contract (M0 §3, §5.2)."""


def make_event(
    event_class: str,
    run_id: str,
    *,
    caused_by: str | list[str] | None = None,
    parent_event_id: str | None = None,
    payload: dict | None = None,
    agent_id: str | None = None,
    role_id: str | None = None,
    session_id: str | None = None,
    model_call_id: str | None = None,
    turn_id: str | None = None,
    audience: str | None = None,
    channel: str | None = None,
    phase_class: str | None = None,
    phase_name: str | None = None,
    event_id: str | None = None,
    event_class_registry: Registry[EventClassDef] = EVENT_CLASS_REGISTRY,
    phase_name_registry: Registry[str] = PHASE_NAME_REGISTRY,
) -> Event:
    """Build a validated ``Event`` with registry-stamped defaults.

    ``event_class`` and ``phase_name`` are validated against the **active**
    registries (open vocabulary, M0 §5.2). Unknown values raise
    ``ProtocolViolation`` — the same condition the router records as a
    ``protocol.violation`` event at runtime.
    """
    try:
        default = event_class_registry[event_class]
    except RegistryError as exc:
        raise ProtocolViolation(
            f"unknown event_class {event_class!r}; register it via inherits_from "
            f"on {event_class_registry.registry_id!r} (M0 §5.2)"
        ) from exc

    resolved_phase_name = phase_name if phase_name is not None else default_phase_name(default)
    if resolved_phase_name not in phase_name_registry:
        raise ProtocolViolation(
            f"unknown phase_name {resolved_phase_name!r} for event_class "
            f"{event_class!r}; register it on {phase_name_registry.registry_id!r}"
        )

    return Event(
        event_class=event_class,
        run_id=run_id,
        event_id=event_id or "",
        caused_by_event_ids=caused_by,
        parent_event_id=parent_event_id,
        agent_id=agent_id,
        role_id=role_id,
        session_id=session_id,
        model_call_id=model_call_id,
        turn_id=turn_id,
        phase_class=phase_class if phase_class is not None else default.phase_class,
        phase_name=resolved_phase_name,
        audience=audience if audience is not None else default.audience,
        channel=channel if channel is not None else default.channel,
        payload=payload if payload is not None else {},
    )


def default_phase_name(default: EventClassDef) -> str:
    """Pick a sensible default ``phase_name`` for a class from its ``phase_class``.

    The §3 table fixes ``phase_class`` per event but not ``phase_name`` (that is
    the open refinement). We default to the conventional name for the class's
    phase so callers need not pass it; producers that care override it.
    """
    return _PHASE_NAME_DEFAULTS.get(default.phase_class, "spine")


# Conventional default phase_name per phase_class (all are in the foundation
# phase-name registry, event_classes.py §2.1).
_PHASE_NAME_DEFAULTS: dict[str, str] = {
    "setup": "prompt_assembly",
    "execution": "reasoning",
    "closure": "commit",
    "infrastructure": "spine",
}
