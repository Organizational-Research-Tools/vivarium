"""Event-class vocabulary + emit/routing tests (M0 §3, §5.1)."""

from __future__ import annotations

import pytest

from oaos2.trace.emit import ProtocolViolation, make_event
from oaos2.trace.event_classes import EVENT_CLASS_REGISTRY
from oaos2.trace.routing import Stream, assert_routing_guardrail, route


def test_retired_name_absent_canonical_present() -> None:
    # M0 §3: chat.request (M5's old name) is retired in favor of chat.requested.
    assert "chat.requested" in EVENT_CLASS_REGISTRY
    assert "chat.request" not in EVENT_CLASS_REGISTRY


def test_no_imperative_or_bare_noun_drift_for_key_events() -> None:
    # Completed facts are past-tense (M0 §3 naming convention).
    for name in ("model.responded", "state.committed", "run.completed", "docker.launched"):
        assert name in EVENT_CLASS_REGISTRY


def test_make_event_stamps_defaults() -> None:
    e = make_event("model.responded", "run1", caused_by="A", payload={"x": 1})
    assert e.phase_class == "execution"
    assert e.audience == "researcher"
    assert e.channel == "formal"
    assert e.caused_by_event_ids == ["A"]


def test_make_event_rejects_unknown_class() -> None:
    with pytest.raises(ProtocolViolation):
        make_event("totally.madeup", "run1")


def test_make_event_allows_per_emission_override() -> None:
    # chat.timed_out's informal default is overridden to researcher/infra (M0 §2).
    e = make_event(
        "chat.timed_out",
        "run1",
        audience="researcher",
        channel="infrastructure",
        phase_class="execution",
        phase_name="coordination",
    )
    assert e.is_infrastructure
    assert route(e) is Stream.INFRA


def test_routing_matches_design_examples() -> None:
    # Self-observability → infra; experiment events → spine.
    infra_classes = [
        "spine.backpressure",
        "run.recovered",
        "index.rebuilt",
        "file.reconciliation_mismatch",
        "spine.causality_cycle",
        "spine.reorder_flush",
        "writer.restarted",
    ]
    for cls in infra_classes:
        e = make_event(cls, "run1")
        assert route(e) is Stream.INFRA, cls

    spine_classes = ["run.started", "model.invoked", "state.committed", "cost.recorded"]
    for cls in spine_classes:
        e = make_event(cls, "run1")
        assert route(e) is Stream.EVENTS, cls


def test_routing_guardrail_both_directions() -> None:
    # An agent-audience event misrouted to infra must raise.
    agent_event = make_event("conversation.volley", "run1")
    assert agent_event.audience == "agent"
    with pytest.raises(AssertionError):
        assert_routing_guardrail(agent_event, Stream.INFRA)
    # An infra event misrouted to the spine must raise.
    infra_event = make_event("spine.backpressure", "run1")
    with pytest.raises(AssertionError):
        assert_routing_guardrail(infra_event, Stream.EVENTS)
    # Correct routing passes.
    assert_routing_guardrail(agent_event, route(agent_event))
    assert_routing_guardrail(infra_event, route(infra_event))


def test_every_foundation_class_routes_without_guardrail_violation() -> None:
    # Sanity: routing each foundation class by its defaults never trips the guardrail.
    for cls in EVENT_CLASS_REGISTRY.ids():
        e = make_event(cls, "run1")
        assert_routing_guardrail(e, route(e))
