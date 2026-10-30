"""Register platform event names and their default fields.

Each entry supplies phase, audience, and channel defaults for make_event.
A caller can explicitly override permitted fields for an individual event;
routing uses those realized values. Task manifests add vocabulary through
trace_vocabulary instead of renaming platform events. Phase names have their
own validated registry. See trace/emit.py and tasks/loader.py."""

from __future__ import annotations

from dataclasses import dataclass

from oaos2.registry import Registry, RegistrySpec
from oaos2.trace.schema import Audience, Channel, PhaseClass


@dataclass(frozen=True)
class EventClassDef:
    """Default envelope classification for one event class (M0 §3)."""

    phase_class: str
    audience: str
    channel: str
    emitted_by: str


# Shorthands for the table below.
_SETUP = PhaseClass.SETUP.value
_EXEC = PhaseClass.EXECUTION.value
_CLOSE = PhaseClass.CLOSURE.value
_INFRA = PhaseClass.INFRASTRUCTURE.value
_AGENT = Audience.AGENT.value
_RESEARCHER = Audience.RESEARCHER.value
_AUD_INFRA = Audience.INFRASTRUCTURE.value
_FORMAL = Channel.FORMAL.value
_INFORMAL = Channel.INFORMAL.value
_CH_INFRA = Channel.INFRASTRUCTURE.value


def _d(phase: str, audience: str, channel: str, emitted_by: str) -> EventClassDef:
    return EventClassDef(phase, audience, channel, emitted_by)


# The §3 table, verbatim. Order mirrors the spec for reviewability.
_FOUNDATION_EVENT_CLASSES: dict[str, EventClassDef] = {
    # run lifecycle
    "run.started": _d(_SETUP, _RESEARCHER, _FORMAL, "runner"),
    "run.completed": _d(_CLOSE, _RESEARCHER, _FORMAL, "runner"),
    "run.failed": _d(_CLOSE, _RESEARCHER, _FORMAL, "runner"),
    # The supervisor's overall deadlock backstop fired (a role retired without committing
    # its blocker, so a downstream role would wait forever). A CLOSE-phase researcher
    # signal the run registry classifies as "stalled" (M5 §2.3, runner deadlock backstop).
    "run.deadlock_timeout": _d(_CLOSE, _RESEARCHER, _FORMAL, "runner"),
    # The PI stopped the run (a first SIGINT/SIGTERM to its launcher; experiments/stop.py,
    # October 21, 2026). The run then ends its work period and finalizes as at a normal end.
    "run.stop_requested": _d(_EXEC, _RESEARCHER, _FORMAL, "runner"),
    "run.recovered": _d(_INFRA, _AUD_INFRA, _CH_INFRA, "writer"),
    # agent lifecycle
    "agent.launched": _d(_SETUP, _RESEARCHER, _FORMAL, "supervisor"),
    "agent.observed": _d(_EXEC, _RESEARCHER, _FORMAL, "agent_loop"),
    "agent.resumed": _d(_EXEC, _RESEARCHER, _FORMAL, "supervisor"),
    "agent.failed": _d(_EXEC, _RESEARCHER, _FORMAL, "supervisor"),
    # turns / actions
    "turn.started": _d(_EXEC, _RESEARCHER, _FORMAL, "agent_loop"),
    "turn.completed": _d(_EXEC, _RESEARCHER, _FORMAL, "agent_loop"),
    "turn.paused": _d(_EXEC, _RESEARCHER, _FORMAL, "agent_loop"),
    "action.started": _d(_EXEC, _RESEARCHER, _FORMAL, "agent_loop"),
    "action.completed": _d(_EXEC, _RESEARCHER, _FORMAL, "agent_loop"),
    "reasoning.step": _d(_EXEC, _RESEARCHER, _FORMAL, "agent_loop"),
    # model gateway
    "model.invoked": _d(_EXEC, _RESEARCHER, _FORMAL, "model_gateway"),
    "model.responded": _d(_EXEC, _RESEARCHER, _FORMAL, "model_gateway"),
    "model.invocation_failed": _d(_EXEC, _RESEARCHER, _FORMAL, "model_gateway"),
    # a provider call that lost its connection and was sent again after a wait (2026-10-04)
    "model.transport_retry": _d(_EXEC, _RESEARCHER, _FORMAL, "model_gateway"),
    # tools
    "tool.called": _d(_EXEC, _RESEARCHER, _FORMAL, "tool_runner"),
    "tool.result": _d(_EXEC, _RESEARCHER, _FORMAL, "tool_runner"),
    "tool.denied": _d(_EXEC, _RESEARCHER, _FORMAL, "tool_runner"),
    # files
    "file.read": _d(_EXEC, _RESEARCHER, _FORMAL, "file_monitor"),
    "file.write": _d(_EXEC, _RESEARCHER, _FORMAL, "file_monitor"),
    "file.edit": _d(_EXEC, _RESEARCHER, _FORMAL, "file_monitor"),
    "file.delete": _d(_EXEC, _RESEARCHER, _FORMAL, "file_monitor"),
    "file.execute": _d(_EXEC, _RESEARCHER, _FORMAL, "file_monitor"),
    "file.searched": _d(_EXEC, _RESEARCHER, _FORMAL, "file_monitor"),
    "file.moved": _d(_EXEC, _RESEARCHER, _FORMAL, "file_monitor"),
    "file.write_contended": _d(_EXEC, _RESEARCHER, _FORMAL, "file_monitor"),
    "artifact.versioned": _d(_EXEC, _RESEARCHER, _FORMAL, "file_monitor"),
    "file.reconciliation_mismatch": _d(_INFRA, _AUD_INFRA, _CH_INFRA, "file_monitor"),
    # live conversation
    "conversation.opened": _d(_EXEC, _AGENT, _INFORMAL, "agent_loop"),
    "conversation.volley": _d(_EXEC, _AGENT, _INFORMAL, "agent_loop"),
    "conversation.closed": _d(_CLOSE, _AGENT, _INFORMAL, "conversation_loop"),
    "context.pressure_warning": _d(_EXEC, _RESEARCHER, _FORMAL, "runtime"),
    # per-agent context budget: eviction of oldest tool-result text when over the token
    # budget (a CONSTRAINT, researcher-facing — never an intervention; see model_agent).
    "context.compaction": _d(_EXEC, _RESEARCHER, _FORMAL, "agent_loop"),
    # hierarchical-arm report watchdog: a domain analyst failed to report within the bounded
    # wait, so the platform committed an EMPTY report to unblock the orchestrator (a
    # CONSTRAINT/scheduling action like context.compaction — never an intervention: it gives
    # the org nothing, it only prevents one dead agent from starving the whole cell).
    "coordination.report_timeout": _d(_EXEC, _RESEARCHER, _FORMAL, "supervisor"),
    # D9 stage advance: the platform opened the next composition stage (draft circulated
    # for comment / ratification closed -> revision) and moved an agent's submit binding.
    # Pure coordination bookkeeping — a constraint-side observable, never an intervention.
    "coordination.stage_advanced": _d(_EXEC, _RESEARCHER, _FORMAL, "supervisor"),
    # Per-slot model-call ceiling reached (§11.6 capacity binding): the platform closed
    # the slot via the contract-declared fallback (or recorded that none was declared).
    # A CONSTRAINT like context.compaction — declared, uniform, never an intervention.
    "capacity.slot_ceiling": _d(_EXEC, _RESEARCHER, _FORMAL, "runtime"),
    # Clocked rounds (decision (c), clock_design.md): a new logical round opened —
    # quiescence-driven, arm-identical, the archive's event→round mapping. A declared
    # apparatus constant like the final-call warning, never an intervention.
    "clock.round": _d(_EXEC, _RESEARCHER, _FORMAL, "runtime"),
    # Post-runtime platform wind-down of an open clocked outcome (audit round 4
    # P1-5): its presence marks a CENSORED cell — never ordinary success.
    "clock.wind_down": _d(_EXEC, _RESEARCHER, _FORMAL, "runtime"),
    # A round deadline passed with a commitment still open: the platform committed the
    # contract-declared fallback (the slot_ceiling pattern, time-triggered). The lapsed
    # case scores unresolved — capacity binding reaches the primary outcome (§11.6).
    "capacity.deadline_lapse": _d(_EXEC, _RESEARCHER, _FORMAL, "runtime"),
    # Task-generic, manifest-scheduled exogenous observation.  The event contains
    # only the role-scoped participant packet; the oracle stays host-side.
    "environment.event": _d(_EXEC, _AGENT, _FORMAL, "environment_driver"),
    # one-round clarification reduction + chat trichotomy
    "chat.requested": _d(_EXEC, _AGENT, _INFORMAL, "agent_loop"),
    "chat.response": _d(_EXEC, _AGENT, _INFORMAL, "agent_loop"),
    "chat.declined": _d(_EXEC, _AGENT, _INFORMAL, "agent_loop"),
    "chat.ignored": _d(_EXEC, _AGENT, _INFORMAL, "agent_loop"),
    "chat.timed_out": _d(_EXEC, _RESEARCHER, _CH_INFRA, "timeout_monitor"),
    "message.sent": _d(_EXEC, _AGENT, _FORMAL, "router"),
    # Voluntary board and notes (M8 §7; named research use: PC1). Delivery and
    # retrieval are separate events; neither is recognition.
    "board.posted": _d(_EXEC, _AGENT, _FORMAL, "board"),
    "board.retrieved": _d(_EXEC, _RESEARCHER, _FORMAL, "board"),
    "notes.retrieved": _d(_EXEC, _RESEARCHER, _FORMAL, "board"),
    # handoff / protocol
    "handoff": _d(_EXEC, _AGENT, _FORMAL, "agent_loop"),
    "handoff_extraction_failed": _d(_EXEC, _RESEARCHER, _FORMAL, "protocol_layer"),
    "handoff_stub_injected": _d(_EXEC, _RESEARCHER, _FORMAL, "protocol_layer"),
    "protocol.violation": _d(_EXEC, _RESEARCHER, _FORMAL, "router"),
    "relay.blocked": _d(_EXEC, _RESEARCHER, _FORMAL, "router"),
    # outcomes / evaluation
    "state.committed": _d(_CLOSE, _RESEARCHER, _FORMAL, "commit_path"),
    # The sole writer rejected a structurally invalid payload. This is distinct from
    # protocol.violation (ordering/duplicate attempts) and leaves no committed state.
    "outcome.commit_refused": _d(_CLOSE, _RESEARCHER, _FORMAL, "commit_path"),
    "outcome.closed": _d(_CLOSE, _RESEARCHER, _FORMAL, "commit_path"),
    "evaluation.completed": _d(_CLOSE, _RESEARCHER, _FORMAL, "evaluator"),
    "evaluation.failed": _d(_CLOSE, _RESEARCHER, _FORMAL, "evaluator"),
    # docker / capture / isolation
    "capture.succeeded": _d(_CLOSE, _RESEARCHER, _FORMAL, "docker_capture"),
    "capture.failed": _d(_CLOSE, _RESEARCHER, _FORMAL, "docker_capture"),
    "docker.launched": _d(_SETUP, _RESEARCHER, _FORMAL, "docker_backend"),
    "docker.launch_failed": _d(_SETUP, _RESEARCHER, _FORMAL, "docker_backend"),
    "docker.exec": _d(_EXEC, _RESEARCHER, _FORMAL, "tool_runner"),
    "docker.oom": _d(_EXEC, _RESEARCHER, _FORMAL, "docker_backend"),
    "docker.disk_exceeded": _d(_EXEC, _RESEARCHER, _FORMAL, "docker_backend"),
    "docker.capability_gap": _d(_SETUP, _RESEARCHER, _FORMAL, "docker_backend"),
    "isolation.violation": _d(_CLOSE, _RESEARCHER, _FORMAL, "docker_capture"),
    # interventions / cost
    "intervention.recorded": _d(_EXEC, _RESEARCHER, _FORMAL, "various"),  # phase varies; overridable
    "cost.recorded": _d(_INFRA, _RESEARCHER, _FORMAL, "cost_core"),
    "cost.cap_blocked_dispatch": _d(_INFRA, _RESEARCHER, _FORMAL, "agent_loop"),
    # self-observability (infra stream)
    "spine.backpressure": _d(_INFRA, _AUD_INFRA, _CH_INFRA, "queue"),
    "spine.queue_depth": _d(_INFRA, _AUD_INFRA, _CH_INFRA, "writer"),
    "spine.write_latency": _d(_INFRA, _AUD_INFRA, _CH_INFRA, "writer"),
    "spine.causality_cycle": _d(_INFRA, _AUD_INFRA, _CH_INFRA, "writer"),
    "spine.reorder_flush": _d(_INFRA, _AUD_INFRA, _CH_INFRA, "writer"),
    "writer.restarted": _d(_INFRA, _AUD_INFRA, _CH_INFRA, "writer"),
    "index.rebuilt": _d(_INFRA, _AUD_INFRA, _CH_INFRA, "writer"),
}


EVENT_CLASS_SPEC: RegistrySpec[EventClassDef] = RegistrySpec(
    registry_id="oaos2.foundation.event_classes",
    entries=_FOUNDATION_EVENT_CLASSES,
)

EVENT_CLASS_REGISTRY: Registry[EventClassDef] = EVENT_CLASS_SPEC.resolve()


# --------------------------------------------------------------------------- #
# Phase-name registry (M0 §2.1) — phase_class (closed) is in schema.py; the
# phase_name vocabulary is open, exactly like the zone/zone_class split.
# --------------------------------------------------------------------------- #

_FOUNDATION_PHASE_NAMES: dict[str, str] = {
    # phase_name -> phase_class it belongs to
    "container_launch": _SETUP,
    "prompt_assembly": _SETUP,
    "reasoning": _EXEC,
    "tool_use": _EXEC,
    "coordination": _EXEC,
    "environment": _EXEC,
    "commit": _CLOSE,
    "evaluation": _CLOSE,
    "capture": _CLOSE,
    "spine": _INFRA,
    "cost_rollup": _INFRA,
}

PHASE_NAME_SPEC: RegistrySpec[str] = RegistrySpec(
    registry_id="oaos2.foundation.phase_names",
    entries=_FOUNDATION_PHASE_NAMES,
)

PHASE_NAME_REGISTRY: Registry[str] = PHASE_NAME_SPEC.resolve()


def default_for(event_class: str) -> EventClassDef:
    """Return the default classification for a foundation event class."""
    return EVENT_CLASS_REGISTRY[event_class]
