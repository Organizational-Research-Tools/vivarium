"""Choose an event's file from its actual audience and channel fields.

Infrastructure audience or channel routes to trace/infra.jsonl; other events
route to trace/events.jsonl. The guardrail rejects an agent-audience event routed
to infrastructure. Both files share a writer and sequence space. Ordering and
causality checks read their union; full transcripts can include both streams.
The final run-status event belongs to the experiment stream."""

from __future__ import annotations

from enum import Enum

from oaos2.trace.schema import Audience, Channel, Event


class Stream(str, Enum):
    EVENTS = "events"  # trace/events.jsonl — authoritative experiment spine
    INFRA = "infra"  # trace/infra.jsonl — self-observability


def route(event: Event) -> Stream:
    """Return which stream ``event`` is appended to (keyed on the realized envelope)."""
    if (
        event.channel == Channel.INFRASTRUCTURE.value
        or event.audience == Audience.INFRASTRUCTURE.value
    ):
        return Stream.INFRA
    return Stream.EVENTS


def assert_routing_guardrail(event: Event, stream: Stream) -> None:
    """The committed §5.1 guardrail, asserted against the realized envelope.

    Both directions: no ``audience=agent`` event may land in ``infra.jsonl``, and
    no ``audience=infrastructure``/``channel=infrastructure`` event may land in
    ``events.jsonl``. A misroute (e.g. a per-emission override gone wrong) is a
    hard error, not a silent slip onto the wrong stream.
    """
    if stream is Stream.INFRA and event.audience == Audience.AGENT.value:
        raise AssertionError(
            f"routing guardrail: agent-audience event {event.event_class!r} "
            f"({event.event_id}) must not land on infra.jsonl"
        )
    if stream is Stream.EVENTS and (
        event.audience == Audience.INFRASTRUCTURE.value
        or event.channel == Channel.INFRASTRUCTURE.value
    ):
        raise AssertionError(
            f"routing guardrail: infrastructure event {event.event_class!r} "
            f"({event.event_id}) must not land on the experiment spine events.jsonl"
        )
