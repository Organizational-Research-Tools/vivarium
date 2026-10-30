"""Event envelope tests (M0 §2): closed value sets, two-clock fields, defaults."""

from __future__ import annotations

import pytest

from oaos2.trace.schema import (
    AUDIENCES,
    CHANNELS,
    PHASE_CLASSES,
    SCHEMA_VERSION,
    Event,
)
from oaos2.ulid import is_ulid


def test_closed_value_sets() -> None:
    assert PHASE_CLASSES == {"setup", "execution", "closure", "infrastructure"}
    assert AUDIENCES == {"agent", "researcher", "scoring", "infrastructure"}
    assert CHANNELS == {"formal", "informal", "private_scoring", "infrastructure"}


def test_event_mints_ulid_when_absent() -> None:
    e = Event(event_class="spine.backpressure")
    assert is_ulid(e.event_id)
    assert e.sequence_number is None  # writer-assigned later
    assert e.schema_version == SCHEMA_VERSION


def test_caused_by_normalization() -> None:
    single = Event(event_class="model.invoked", caused_by_event_ids="A")  # type: ignore[arg-type]
    assert single.caused_by_event_ids == ["A"]
    listed = Event(event_class="model.invoked", caused_by_event_ids=["A", "B"])
    assert listed.caused_by_event_ids == ["A", "B"]
    root = Event(event_class="run.started")
    assert root.caused_by_event_ids == []


def test_rejects_out_of_set_envelope_fields() -> None:
    with pytest.raises(ValueError):
        Event(event_class="x", phase_class="not_a_phase")
    with pytest.raises(ValueError):
        Event(event_class="x", audience="nobody")
    with pytest.raises(ValueError):
        Event(event_class="x", channel="carrier_pigeon")


def test_is_infrastructure_keys_on_realized_envelope() -> None:
    infra = Event(event_class="spine.backpressure")  # defaults to infra/infra
    assert infra.is_infrastructure
    spine = Event(
        event_class="run.started",
        audience="researcher",
        channel="formal",
        phase_class="setup",
    )
    assert not spine.is_infrastructure
    # A per-emission override to channel=infrastructure flips routing.
    overridden = Event(
        event_class="chat.timed_out",
        audience="researcher",
        channel="infrastructure",
        phase_class="execution",
    )
    assert overridden.is_infrastructure


def test_roundtrip_to_dict_from_dict() -> None:
    e = Event(
        event_class="model.responded",
        run_id="run1",
        audience="researcher",
        channel="formal",
        phase_class="execution",
        phase_name="reasoning",
        caused_by_event_ids=["A"],
        payload={"k": 1},
    )
    e.sequence_number = 7
    again = Event.from_dict(e.to_dict())
    assert again.event_id == e.event_id
    assert again.sequence_number == 7
    assert again.caused_by_event_ids == ["A"]
    assert again.payload == {"k": 1}
