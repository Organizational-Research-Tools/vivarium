"""Define the shared fields carried by every Event.

The event envelope contains identity, ordering, visibility, causal links, and
payload. Event classes and phase names come from registries of accepted names;
changing those names need not change the envelope. Changing shared fields
requires an explicit schema-version decision. make_event() applies registry
validation and default visibility settings before the writer assigns order."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum

# Archive-level schema version (M0 §5.3): YYYY-MM-DD.vN — the freeze date plus a
# within-day revision counter. Primary versioning is archive-level; per-record
# self-versioning is added only where a record evolves independently (DESIGN §6.6).
SCHEMA_VERSION = "2026-06-01.v1"


class PhaseClass(str, Enum):
    """Closed phase-class set (M0 §2.1). The open ``phase_name`` refines within."""

    SETUP = "setup"
    EXECUTION = "execution"
    CLOSURE = "closure"
    INFRASTRUCTURE = "infrastructure"


class Audience(str, Enum):
    """Closed audience set (M0 §2) — *who may see this*."""

    AGENT = "agent"
    RESEARCHER = "researcher"
    SCORING = "scoring"
    INFRASTRUCTURE = "infrastructure"


class Channel(str, Enum):
    """Closed channel set (M0 §2) — *what conduit carried this*."""

    FORMAL = "formal"
    INFORMAL = "informal"
    PRIVATE_SCORING = "private_scoring"
    INFRASTRUCTURE = "infrastructure"


PHASE_CLASSES: frozenset[str] = frozenset(p.value for p in PhaseClass)
AUDIENCES: frozenset[str] = frozenset(a.value for a in Audience)
CHANNELS: frozenset[str] = frozenset(c.value for c in Channel)


def _normalize_caused_by(value: object) -> list[str]:
    """Accept a single event_id, a list, or None; store the normalized list.

    The producer-facing emit convention (M0 §4) accepts ``caused_by`` as a single
    id *or* a list; the envelope always stores ``caused_by_event_ids`` as a list
    (a singleton for the common one-cause case, ``[]`` for a root).
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


@dataclass
class Event:
    """The atom of the trace: closed envelope + open ``event_class`` + free payload.

    Defaults lean toward writer-synthesized infrastructure events (M1 emits
    ``spine.backpressure``/``writer.restarted``/``run.recovered`` with only a
    handful of fields set), so those construct trivially while producer events go
    through ``emit.py`` which fills every field from the active registry.
    """

    # --- Classification (event_class is OPEN; the rest are CLOSED sets) ---
    event_class: str
    run_id: str = ""

    # --- Identity & ordering (the two-clock rule, DESIGN §6.2) ---
    event_id: str = ""
    sequence_number: int | None = None  # WRITER-assigned at append; the sole total order
    timestamp: float = field(default_factory=time.time)  # advisory ONLY

    # --- Causality (drives INV-2/INV-3) ---
    caused_by_event_ids: list[str] = field(default_factory=list)  # MULTI-PARENT DAG
    parent_event_id: str | None = None  # structural nesting (single)

    # --- Scope ---
    agent_id: str | None = None
    role_id: str | None = None
    session_id: str | None = None
    model_call_id: str | None = None
    turn_id: str | None = None  # logical turn; survives pause/resume (DESIGN §6.5)

    # --- Phase / audience / channel ---
    phase_class: str = PhaseClass.INFRASTRUCTURE.value
    phase_name: str = "spine"
    audience: str = Audience.INFRASTRUCTURE.value
    channel: str = Channel.INFRASTRUCTURE.value

    # --- Payload & versioning ---
    payload: dict = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        # Mint an id if the producer didn't (most producers do, so they can
        # reference it before enqueue — M0 §4).
        if not self.event_id:
            from oaos2.ulid import gen_event_id

            self.event_id = gen_event_id()
        self.caused_by_event_ids = _normalize_caused_by(self.caused_by_event_ids)

        # Validate the three genuinely-closed envelope fields. event_class and
        # phase_name are open registries, validated on the emit path.
        if self.phase_class not in PHASE_CLASSES:
            raise ValueError(
                f"phase_class {self.phase_class!r} not in closed set {sorted(PHASE_CLASSES)}"
            )
        if self.audience not in AUDIENCES:
            raise ValueError(
                f"audience {self.audience!r} not in closed set {sorted(AUDIENCES)}"
            )
        if self.channel not in CHANNELS:
            raise ValueError(
                f"channel {self.channel!r} not in closed set {sorted(CHANNELS)}"
            )

    @property
    def is_infrastructure(self) -> bool:
        """True iff this event routes to ``infra.jsonl`` (M0 §5.1).

        Keyed on the **realized** envelope, never on a class default — a
        per-emission override is authoritative for routing.
        """
        return (
            self.channel == Channel.INFRASTRUCTURE.value
            or self.audience == Audience.INFRASTRUCTURE.value
        )

    def to_dict(self) -> dict:
        """Serialize for the JSONL streams (the writer appends ``to_dict`` + newline)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        """Reconstruct from a parsed JSONL line (recovery / index rebuild)."""
        return cls(**data)
