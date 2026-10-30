"""Named archive record schemas, distinct from the common Event envelope.

Pydantic models define records such as AgentInstance, Handoff, and StateCommitment.
References link records by identifier instead of embedding complete objects.
An Event in schema.py supplies the shared ordering and routing fields around a
payload; its registered event name determines what happened.

Unexpected record fields are rejected. Declared extensions dictionaries support
additional metadata, and some runtime paths read specific extension keys. A
reserved record type does not establish that any producer currently emits it;
consult docs/SYSTEM.md and docs/mechanism/DEFERRED.md for implemented paths."""

from __future__ import annotations

from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field


class Tier(str, Enum):
    A = "A"  # foundation_v0
    B = "B"  # first extension (reserved seam)
    C = "C"  # future theory package (reserved seam)


class CanonicalRecord(BaseModel):
    """Base for every named record. Subclasses set ``record_tier``."""

    model_config = ConfigDict(extra="forbid")
    record_tier: ClassVar[Tier] = Tier.A


# --------------------------------------------------------------------------- #
# Run / agent identity & session
# --------------------------------------------------------------------------- #


class Run(CanonicalRecord):
    """One run of one task pack under one organization (DESIGN §17.1, §17.3)."""

    run_id: str
    experiment_id: str
    task_pack_id: str
    mode: str  # pilot | calibration | confirmatory | exploratory (validity, §19)
    schema_version: str
    manifest_hash: str | None = None
    organization_id: str | None = None


class AgentInstance(CanonicalRecord):
    """A runtime actor: binds a role + model + prompt + policies (DESIGN §10.1)."""

    agent_id: str
    role_id: str
    model_ref: str
    session_id: str | None = None
    runtime: str = "raw_api"  # raw_api (default/only confirmatory) | tool_runner | local | custom


class RuntimeSession(CanonicalRecord):
    """A model-backed conversation session owned by one agent (DESIGN §10.1)."""

    session_id: str
    agent_id: str
    runtime: str = "raw_api"


class PromptEnvelope(CanonicalRecord):
    """The assembled prompt for an agent (DESIGN §10.1)."""

    prompt_envelope_id: str
    agent_id: str
    system_prompt: str
    role_packet_refs: list[str] = Field(default_factory=list)
    marker_immediacy_instruction: str | None = None


# --------------------------------------------------------------------------- #
# Per-turn epistemic snapshot
# --------------------------------------------------------------------------- #


class Observation(CanonicalRecord):
    """Something an agent observed (a mailbox delivery, a file, feedback)."""

    observation_id: str
    agent_id: str
    source_event_ids: list[str] = Field(default_factory=list)
    summary: str | None = None


class AgentView(CanonicalRecord):
    """Per-turn epistemic snapshot: what the agent could see this turn (DESIGN §17.1)."""

    agent_view_id: str
    agent_id: str
    turn_id: str
    observation_ids: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Messages / narration
# --------------------------------------------------------------------------- #


class FormalMessage(CanonicalRecord):
    """A formal, router-mediated message (the persisted form behind message.sent)."""

    message_id: str
    from_agent: str
    to_agent: str  # an agent id, "broadcast", or a serialized recipient list
    kind: str  # registry-declared communication kind
    kind_primitive: str  # message | request | response | declaration (closed, §11.1)
    payload_text: str = ""
    payload_refs: list[str] = Field(default_factory=list)


class Narration(CanonicalRecord):
    """An agent's free-text narration.

    Never seen by downstream agents except via the formalized payload or the
    failure stub — router-enforced (DESIGN §17.1).
    """

    narration_id: str
    agent_id: str
    turn_id: str | None = None
    text: str = ""


# --------------------------------------------------------------------------- #
# Reasoning / tools / files
# --------------------------------------------------------------------------- #


class ReasoningTelemetry(CanonicalRecord):
    """Thinking/reasoning token telemetry, exposure-gated (DESIGN §10.2)."""

    reasoning_id: str
    model_call_id: str
    reasoning_kind: str | None = None  # provider reasoning kind capability
    reasoning_tokens: int | None = None
    exposed_to_agent: bool = False


class ToolCall(CanonicalRecord):
    """One tool invocation, carrying the policy decision (DESIGN §10.3)."""

    tool_call_id: str
    agent_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    tool_policy_decision: str = "allowed"  # allowed | denied (tool.denied is first-class)


class FileEvent(CanonicalRecord):
    """A read/search/permission-denial over a zone (non-mutating; DESIGN §9)."""

    file_event_id: str
    agent_id: str
    path: str
    zone: str
    zone_class: str  # agent_writable | task_visible | hidden | temp | infrastructure
    operation: str  # read | searched | denied


class FileChange(CanonicalRecord):
    """A mutating file change with before/after hashes (DESIGN §9, M4 §5)."""

    file_change_id: str
    agent_id: str
    path: str
    zone: str
    zone_class: str
    operation: str  # create | modify | delete | move
    hash_before: str | None = None
    hash_after: str | None = None
    patch_ref: str | None = None  # null for large/binary files or hashes_only retention
    cause_event_ids: list[str] = Field(default_factory=list)
    narration_refs: list[str] = Field(default_factory=list)
    turn_id: str | None = None
    enforcement: str = "os"  # os | software — the integrity claim (§8)
    capture_source: str = "tool"  # tool | hash_scan | fanotify (Tier-B §3.1)
    artifact_version_id: str | None = None


class ArtifactVersion(CanonicalRecord):
    """A versioned artifact minted by a FileChange (DESIGN §17.1; M4 §5)."""

    artifact_version_id: str
    artifact_id: str
    version: int
    file_change_id: str
    content_hash: str


# --------------------------------------------------------------------------- #
# Handoffs / coordination
# --------------------------------------------------------------------------- #


class Handoff(CanonicalRecord):
    """A formal payload transfer between roles (DESIGN §12)."""

    handoff_id: str
    from_agent: str
    to_agent: str
    handoff_format: str  # raw | structured | summary | structured_rationale
    payload_refs: list[str] = Field(default_factory=list)


class HandoffDelta(CanonicalRecord):
    """Narration ↔ formalized-payload delta, for boundary-loss measurement (§17.1).

    Study CH1 makes the slot live: ``handoff_format`` is the arm's declared channel
    form (``Handoff.handoff_format`` vocabulary — raw | structured | summary |
    structured_rationale) and ``source_refs`` are the participant-vocabulary ids of
    the packets the formalized payload was written from, so an archive projection
    can ask which registered facts of the source survived into the payload.
    """

    handoff_delta_id: str
    handoff_id: str
    narration_ref: str | None = None
    formalized_payload_ref: str | None = None
    handoff_format: str | None = None
    source_refs: list[str] = Field(default_factory=list)


class CommunicationEvent(CanonicalRecord):
    """The persisted form behind the chat.* / message.sent events (M0 §6)."""

    communication_event_id: str
    from_agent: str
    to_agent: str
    kind: str
    kind_primitive: str
    payload_text: str = ""
    relay_check: str = "passed"  # passed | blocked (cross-ACL verbatim leak, §8.2)


# --------------------------------------------------------------------------- #
# Validation / evaluation / intervention / context / commitment
# --------------------------------------------------------------------------- #


class ValidationEvent(CanonicalRecord):
    """A public validator result over a submitted commitment (DESIGN §14)."""

    validation_event_id: str
    commitment_ref: str
    validator_ref: str
    passed: bool
    detail: dict[str, Any] = Field(default_factory=dict)


class EvaluationRecord(CanonicalRecord):
    """An evaluator result with the diagnostic split enforced at write time (§14).

    ``agent_feedback`` must conform to the task's ``PublicFeedbackSchema``
    whitelist; ``researcher_diagnostics`` carries full detail and is **never**
    delivered to agents (the answer-key side channel is closed by construction).
    """

    evaluation_id: str
    commitment_ref: str
    evaluator_ref: str
    evaluator_kind: str  # schema | plugin
    # The outcome this evaluation scores (M6 §5) — lets the archive group evaluations
    # by outcome without reconstructing the link from event payloads.
    outcome_id: str | None = None
    determinism: str = "deterministic"  # deterministic | stochastic(seeded) | stochastic (§5)
    agent_feedback: dict[str, Any] = Field(default_factory=dict)
    researcher_diagnostics: dict[str, Any] = Field(default_factory=dict)


class InterventionClass(str, Enum):
    """Closed set (DESIGN §17.1, §19): how an intervention bears on validity."""

    SILENT_RECORDED = "silent_recorded"
    RECORDED = "recorded"
    TREATMENT_DEFINING = "treatment_defining"


class Intervention(CanonicalRecord):
    """Platform assistance, classed for validity accounting (DESIGN §17.1, §19)."""

    # ``class`` is a Python keyword, so the field is ``intervention_class`` but
    # serializes to/from the spec's ``class`` key (M0 §6) via the alias. Use
    # ``model_dump(by_alias=True)`` to emit the spec-faithful JSON key.
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    intervention_id: str
    intervention_class: InterventionClass = Field(alias="class")
    kind: str  # cost_pressure_wrapup | retry | forced_handoff | marker_repair | ...
    target_event_ids: list[str] = Field(default_factory=list)
    detail: dict[str, Any] = Field(default_factory=dict)


class ContextEvent(CanonicalRecord):
    """A compaction event with pre/post observation refs (DESIGN §17.1)."""

    context_event_id: str
    agent_id: str
    session_id: str
    pre_observation_refs: list[str] = Field(default_factory=list)
    post_observation_refs: list[str] = Field(default_factory=list)


class StateCommitment(CanonicalRecord):
    """Record an accepted submission with its agent, session, payload hash, and causes.

    outcomes/commit.py writes it through the controlled submission path. Agent
    and session IDs identify the submitter; they are not cryptographic signatures.
    An accepted commitment can contribute to outcome closure without being scored
    as correct."""

    commitment_id: str
    kind: str  # registry-declared (artifact_submission, vote_resolved, ...)
    agent_id: str
    session_id: str
    payload_ref: str | None = None
    # Hash of the accepted payload, also saved in its event. Containers cannot
    # overwrite submitted/; this is a content check, not a cryptographic signature.
    content_hash: str | None = None
    caused_by_event_ids: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Extended records: annotations and environment delivery work; other types remain reserved
# --------------------------------------------------------------------------- #


class AnnotationLink(CanonicalRecord):
    """Link a registered research label to one event, a relationship, or a group."""

    record_tier: ClassVar[Tier] = Tier.B

    link_id: str
    label_schema_ref: str
    namespace: str
    arity: str  # unary | relational | group
    event_ids: list[str] = Field(default_factory=list)
    relation_kind: str | None = None  # required when arity == relational
    label: dict[str, Any] = Field(default_factory=dict)
    classifier_mode: str = "deferred"  # pattern | plugin | llm_judge | deferred
    classifier_ref: str | None = None
    confidence: float | None = None


class EnvironmentEvent(CanonicalRecord):
    """Record an environment notice delivered to one role.

    The participant payload is saved as delivered. Private scoring state remains
    in the task's separate, hash-identified reference files."""

    record_tier: ClassVar[Tier] = Tier.C

    environment_event_id: str
    driver_ref: str
    schedule_ref: str
    schedule_hash: str
    wave_id: str
    packet_id: str
    trigger_commitment_id: str
    target_role_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentLifecycleEvent(CanonicalRecord):
    """Mid-run membership change (DESIGN §21 lifecycle). Tier C."""

    record_tier: ClassVar[Tier] = Tier.C

    lifecycle_event_id: str
    agent_id: str
    transition: str  # joined | left | replaced


# --------------------------------------------------------------------------- #
# The canonical record registry (the no-anonymous-types gate reads this)
# --------------------------------------------------------------------------- #

CANONICAL_RECORDS: dict[str, type[CanonicalRecord]] = {
    cls.__name__: cls
    for cls in (
        Run,
        AgentInstance,
        RuntimeSession,
        PromptEnvelope,
        Observation,
        AgentView,
        FormalMessage,
        Narration,
        ReasoningTelemetry,
        ToolCall,
        FileEvent,
        FileChange,
        ArtifactVersion,
        Handoff,
        HandoffDelta,
        CommunicationEvent,
        ValidationEvent,
        EvaluationRecord,
        Intervention,
        ContextEvent,
        StateCommitment,
        AnnotationLink,
        EnvironmentEvent,
        AgentLifecycleEvent,
    )
}


def is_canonical_record(tp: type) -> bool:
    """True iff ``tp`` is a schematized canonical record."""
    return isinstance(tp, type) and tp.__name__ in CANONICAL_RECORDS
