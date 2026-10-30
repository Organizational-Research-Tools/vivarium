"""Manage concurrent agent work, waiting, messages, and handoffs.

Agents run as independent asynchronous tasks. Scheduling policies admit ready
agents; dependency overrides let a requested responder or conversation speaker
act even when the base policy would withhold it. Unclocked work has no global
turn barrier. Clocked runs additionally limit each role to one turn per round.
Timeouts detect stalled work; dependency overrides do not guarantee every
possible organization is free of deadlock.

An AgentBehavior returns an ActionPlan for a turn. Scripted behaviors support
offline checks; model-driven behaviors use agents/model_agent.py. The runtime
records actions and their predecessors through RunSpine. Submission handling,
coordination procedures, and the runner supply the task's work dependencies."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from oaos2.communication.mailbox import Mailbox, MailboxItem, MailboxPolicy
from oaos2.communication.messages import ChatRequest, ChatResponse, MessageIntent
from oaos2.communication.router import Router
from oaos2.organizations.scheduler import (
    SCHEDULER_POLICIES,
    SchedulerPolicy,
    resolve_scheduler_policy,
)
from oaos2.trace.spine import RunSpine
from oaos2.trace.records import AgentView, Observation
from oaos2.ulid import new_ulid


# --------------------------------------------------------------------------- #
# Agent runtime + action plan
# --------------------------------------------------------------------------- #


@dataclass
class ToolCallIntent:
    name: str
    argv: list[str] = field(default_factory=list)
    tool_call_id: str = ""


@dataclass
class WriteIntent:
    path: object  # Path
    data: bytes
    zone: object  # workspace.acl.Zone
    edit: bool = False


@dataclass
class ConversationOpenIntent:
    """Request a conversation with a partner and supply its opening text.

    Without an explicit contract, use the default two-participant contract.
    Group conversations can also be started through run_conversation."""

    partner: str
    opening_payload: str
    contract: object | None = None  # ConversationContract; None ⇒ default free chat


@dataclass
class ConversationVolleyIntent:
    """The floor-holder's volley over an open conversation (M5 §2.6). Set by an agent
    that observes a ``conversation_volley_request`` in its mailbox."""

    conversation_id: str
    text: str
    done: bool = False
    # True when the assent was forced by the cost cap (the speaker could not afford
    # another volley), not reached freely — recorded so closure can distinguish
    # genuine consensus from a budget-forced one (an observable, not a construct).
    budget_forced: bool = False
    last_event_id: str | None = None


@dataclass
class ActionPlan:
    """What an agent decides to do in one within-turn action (M5 §2.2)."""

    tool_calls: list[ToolCallIntent] = field(default_factory=list)
    writes: list[WriteIntent] = field(default_factory=list)
    messages: list[MessageIntent] = field(default_factory=list)
    chat_responses: list[ChatResponse] = field(default_factory=list)
    chat_request: ChatRequest | None = None
    conversation_open: ConversationOpenIntent | None = None
    conversation_volley: ConversationVolleyIntent | None = None
    # continue | finish_turn | retire | handoff | closed
    result: str = "finish_turn"
    narration: str = ""
    # Last event produced inside the behavior, so subsequent actions retain the
    # information and interventions that shaped this action.
    last_event_id: str | None = None


AgentBehavior = Callable[["AgentRuntime", "RuntimeState", "TurnContext"], Awaitable[ActionPlan]]


@dataclass
class TurnContext:
    turn_id: str
    action_index: int
    caused_by: str
    observations: list[dict]


@dataclass
class AgentRuntime:
    agent_id: str
    role_id: str
    behavior: AgentBehavior
    last_event_id: str | None = None
    turn_count: int = 0
    retired: bool = False
    status: str = "idle"  # idle | running | paused | retired
    cost_spent_usd: float = 0.0
    state: dict = field(default_factory=dict)  # scratch for behaviors


@dataclass
class PausedTurnRecord:
    paused_turn_id: str
    parent_turn_id: str
    pausing_agent_id: str
    target_agent_id: str
    request_payload: str
    resume_event: asyncio.Event
    nesting_depth: int
    deadline_seconds: float
    requested_event_id: str | None = None
    resolution_kind: str | None = None  # the single sentinel; None = unresolved
    resolved_at_event_id: str | None = None


# --------------------------------------------------------------------------- #
# Runtime state
# --------------------------------------------------------------------------- #


@dataclass
class RuntimeState:
    run_id: str
    spine: RunSpine
    agents: dict[str, AgentRuntime] = field(default_factory=dict)
    admission: dict[str, asyncio.Event] = field(default_factory=dict)
    scheduler_wakeup: asyncio.Event = field(default_factory=asyncio.Event)
    paused_turns: dict[str, PausedTurnRecord] = field(default_factory=dict)
    # Live multi-round conversations (M5 §2.6). While a conversation is open the
    # scheduler force-admits its floor-holder and withholds the other participant —
    # the floor token IS mutual exclusion (§2.3/§2.4).
    open_conversations: dict = field(default_factory=dict)  # conv_id -> ConversationState
    mailbox: dict[str, Mailbox] = field(default_factory=dict)
    router: Router = field(default_factory=Router)
    scheduler_policy: SchedulerPolicy = SCHEDULER_POLICIES["free"]
    last_actor: str | None = None
    manager_last_dispatch: list[str] | None = None
    # Bounded tail of recent admission-relevant declarations (admission_directive),
    # so manager_dispatch reads the manager-agent's directive FROM the trace
    # (M5 §2.3, §3.2) instead of an externally pre-set field.
    recent_events: list[dict] = field(default_factory=list)
    allow_whole_org_broadcast: bool = False  # whole_organization scope needs this grant (§11.3)
    max_nesting_depth: int = 4
    pause_counter: int = 0  # monotonic; mints unique paused_turn_id suffixes (never reused after a pop)
    max_actions_per_turn: int = 64
    # Agent-turn model responses and classifier refusals among them (October 10, 2026), so a
    # procedure can end a run whose refusals exceed its bound instead of switching models.
    provider_tally: dict = field(default_factory=lambda: {"responses": 0, "refusals": 0, "unrecovered": 0,
                                                          "unrecovered_by_agent": {}})
    outcome_closed: bool = False
    # The PI asked the run to stop (a first SIGINT/SIGTERM to the launcher; experiments/stop.py,
    # October 21, 2026). Every agent is retired at once and makes no new model call; the task's
    # procedure ends its work period and the run finalizes and tears down as at a normal end.
    stop_requested: bool = False
    workspace: object | None = None  # WorkspaceManager (M4), optional
    handoff_contract: object | None = None  # HandoffContract (M6 §1), optional
    # Organization-structure surface (M5 §18.1), optional — set by a structure-pack;
    # the four decomposition-only arms leave them None/{} (fully permissive). topology
    # gates which kinds flow between which roles; decision_rights[role_id] gates
    # handoff acceptance and milestone submission.
    topology: object | None = None  # organizations.topology.Topology
    decision_rights: dict = field(default_factory=dict)  # role_id -> DecisionRights
    comm_kinds: dict = field(default_factory=dict)  # role_id -> frozenset of send-permitted kinds
    # Dependency-driven admission for the OutcomeContract `blocks` DAG (M5 §2.3): a
    # readiness predicate per agent (agent_id -> () -> bool). A not-ready agent is NOT
    # admitted — it never runs and emits nothing — so a downstream role waiting on its
    # blocker does not busy-spin finish_turn (the cost is real: a live blocker takes
    # minutes, during which a hot re-admit loop emits hundreds of thousands of events).
    readiness: dict = field(default_factory=dict)
    # Agent id -> manifest attention scope (a str), or a tuple of scopes when the
    # role declares extra ``packet_scopes`` (CH1 evidence arm).  Environment packets
    # target scopes, so the same schedule serves a solo (``all``), a hierarchy, or a
    # network; a tuple receives a packet targeting ANY of its members.
    environment_scopes: dict[str, str | tuple] = field(default_factory=dict)
    # Optional per-delivery sink for environment packets (the clocked runner's
    # correspondence file): called as sink(agent_id=..., packet=...) for every
    # recipient the attention-scope routing selects — file-of-record semantics
    # ride the SAME targeting as mailbox delivery, never a second visibility rule.
    environment_delivery_sink: object | None = None
    # Optional builder of the case file appended to a duty notice (outcomes/case_file.py):
    # called as builder(commitment_id, agent_id) -> str; '' when the slot declares none.
    case_file_builder: object | None = None
    # Logical clock for clocked-rounds runs (kernel/clock.py); None = batched mode,
    # in which nothing below changes behavior.
    clock: object | None = None
    _clock: float = 0.0

    # gateway components for model-driven behaviors (M3), optional
    adapter: object | None = None
    ledger: object | None = None
    raw_store: object | None = None
    # Task spawner for detached drivers (e.g. run_conversation), set by run_supervisor to
    # the run's TaskGroup.create_task so a conversation runs concurrently with the agent
    # loops rather than blocking the opener's turn (M5 §2.6).
    _spawn: object | None = None

    def now(self) -> float:
        import time

        return time.time()

    def kick_scheduler(self) -> None:
        self.scheduler_wakeup.set()

    def is_done(self) -> bool:
        return self.outcome_closed or all(a.retired for a in self.agents.values())

    def close_outcome(self) -> None:
        self.outcome_closed = True
        self.kick_scheduler()

    def request_stop(self) -> None:
        """Retire every agent at its next action boundary (the PI's stop); no new turn is admitted."""
        self.stop_requested = True
        for agent in self.agents.values():
            agent.retired = True
        self.kick_scheduler()
        for gate in self.admission.values():  # wake waiting loops so they see the stop and exit
            gate.set()

    # -- snapshot for the scheduler (synchronous = atomic on one loop, §3.2) -- #
    def snapshot(self) -> "Snapshot":
        idle = [aid for aid, a in self.agents.items() if a.status == "idle" and not a.retired]
        return Snapshot(
            idle_agents=idle,
            running_agents=[aid for aid, a in self.agents.items() if a.status == "running"],
            last_actor=self.last_actor,
            all_agent_order=list(self.agents.keys()),
            manager_last_dispatch=self.manager_last_dispatch,
            recent_events=list(self.recent_events),
            open_pause_targets=[pt.target_agent_id for pt in self.paused_turns.values()
                                if pt.resolution_kind is None],
            paused_agents=[pt.pausing_agent_id for pt in self.paused_turns.values()
                           if pt.resolution_kind is None],
            open_conversations=[c for c in self.open_conversations.values() if not c.closed],
            clock_round=self.clock.round_no if self.clock is not None else 0,
            clock_acted=frozenset(self.clock.acted) if self.clock is not None
            else frozenset(),
        )


@dataclass
class Snapshot:
    idle_agents: list[str]
    last_actor: str | None
    all_agent_order: list[str]
    manager_last_dispatch: list[str] | None
    recent_events: list[dict]
    open_pause_targets: list[str]
    paused_agents: list[str]
    open_conversations: list = field(default_factory=list)  # ConversationState (M5 §2.6)
    # Clocked-rounds view (kernel/clock.py); inert defaults in batched mode.
    clock_round: int = 0
    clock_acted: frozenset = frozenset()
    running_agents: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Supervisor
# --------------------------------------------------------------------------- #


async def run_supervisor(rs: RuntimeState, *, timeout_tick: float = 0.05, on_start=None) -> None:
    """Launch N agent loops + scheduler + timeout monitor as long-lived coroutines.

    The TaskGroup scope is the *lifetime of the run*, not a per-round barrier
    (M5 §2.1). It completes when the scheduler returns on closure (releasing all
    gates), the agent loops observe closure and exit, and the monitor exits.

    ``on_start`` (optional, zero-arg coroutine fn) is spawned into the run's TaskGroup at
    start — used to drive a run-opening n-party deliberation concurrently with the agents.
    """
    # The run's causal root (M5 §2.2): every agent.launched is caused_by it, so the
    # whole causal forest descends from one explicit root rather than N orphans.
    run_started = await rs.spine.emit_event("run.started", payload={"run_id": rs.run_id})
    for agent in rs.agents.values():
        await rs.spine.emit_event(
            "agent.launched", agent_id=agent.agent_id, caused_by=run_started,
            payload={"role_id": agent.role_id}
        )
    rs.kick_scheduler()  # compute initial admissions
    async with asyncio.TaskGroup() as tg:
        rs._spawn = tg.create_task  # let conversation drivers run concurrently (M5 §2.6)
        for agent in rs.agents.values():
            tg.create_task(_agent_loop(agent, rs))
        tg.create_task(_scheduler_coro(rs))
        tg.create_task(_timeout_monitor(rs, timeout_tick))
        if on_start is not None:
            tg.create_task(on_start())  # run-opening deliberation (organic arm), concurrent


async def _agent_loop(agent: AgentRuntime, rs: RuntimeState) -> None:
    while not rs.is_done() and not agent.retired:
        await rs.admission[agent.agent_id].wait()
        # Each admission grants one turn. Consuming it before any await prevents
        # a completed turn from reusing a stale gate before the scheduler runs.
        rs.admission[agent.agent_id].clear()
        if rs.is_done() or agent.retired:
            break
        if agent.status != "idle":
            # Re-gated while not idle (e.g. just resumed); yield and re-check.
            await asyncio.sleep(0)
            continue
        if rs.clock is not None and agent.agent_id in rs.clock.acted:
            # Clocked rounds: this round's turn is already spent. The admission
            # gate can be stale for one beat (it is cleared by the scheduler
            # coroutine, which races the loop's re-entry), so ``acted`` is the
            # authoritative per-round budget — clear our own gate and wait for
            # the next round's admission.
            rs.admission[agent.agent_id].clear()
            rs.kick_scheduler()
            continue
        agent.status = "running"
        try:
            await _agent_turn(agent, rs)
        except Exception as exc:  # noqa: BLE001 — retire on uncaught, never crash the run
            from oaos2.docker.isolation import IsolationViolation
            from oaos2.environment import EnvironmentScheduleError
            from oaos2.outcomes.conformance import CommitmentConformanceError
            if isinstance(exc, (IsolationViolation, CommitmentConformanceError,
                                EnvironmentScheduleError)):
                # Run-fatal: isolation breaches and exhausted commitment conformance
                # retries both mean the declared apparatus was not instantiated. Retiring
                # just this agent would leave downstream blockers waiting for the much
                # longer deadlock watchdog and could launder failure into a scored cell.
                raise
            await rs.spine.emit_event(
                "agent.failed", agent_id=agent.agent_id, payload={"error": repr(exc)}
            )
            agent.retired = True
            agent.status = "retired"
        else:
            if not agent.retired:
                agent.status = "idle"
        if rs.clock is not None:
            # Clocked rounds: this agent's one turn for the round is spent
            # (success or failure alike — a crashed turn is still a spent turn).
            rs.clock.acted.add(agent.agent_id)
        rs.last_actor = agent.agent_id
        rs.kick_scheduler()


async def _agent_turn(agent: AgentRuntime, rs: RuntimeState) -> str:
    agent.turn_count += 1
    turn_id = f"{agent.agent_id}.t{agent.turn_count}"
    turn_started = await rs.spine.emit_event(
        "turn.started", agent_id=agent.agent_id, turn_id=turn_id, caused_by=agent.last_event_id
    )
    prev = turn_started
    for action_index in range(1, rs.max_actions_per_turn + 1):
        result, prev = await _agent_action(agent, rs, turn_id, action_index, prev)
        if rs.outcome_closed and result == "continue":
            result = "closed"
        if rs.stop_requested and result == "continue":
            result = "stopped"  # the PI's stop: no further action in this turn
        if result in ("handoff", "closed", "cost_capped", "stopped"):
            # A cost-capped agent cannot make progress under the cap and — with no
            # soft-pressure ladder (Tier B) and no outcome to wrap up to — retires,
            # so the run terminates rather than spinning on refused dispatches.
            if result == "cost_capped":
                agent.retired = True
                agent.status = "retired"
            await rs.spine.emit_event(
                "turn.completed", agent_id=agent.agent_id, turn_id=turn_id,
                caused_by=prev, payload={"result": result, "action_count": action_index},
            )
            agent.last_event_id = prev
            return result
        if result == "retire":
            agent.retired = True
            agent.status = "retired"
            await rs.spine.emit_event(
                "turn.completed", agent_id=agent.agent_id, turn_id=turn_id,
                caused_by=prev, payload={"result": "retire", "action_count": action_index},
            )
            agent.last_event_id = prev
            return "retire"
        if result == "finish_turn":
            await rs.spine.emit_event(
                "turn.completed", agent_id=agent.agent_id, turn_id=turn_id,
                caused_by=prev, payload={"result": "finish_turn", "action_count": action_index},
            )
            agent.last_event_id = prev
            return "finish_turn"
        # result == "continue" → next action
    # Hit the per-turn action ceiling — end the turn.
    await rs.spine.emit_event(
        "turn.completed", agent_id=agent.agent_id, turn_id=turn_id,
        caused_by=prev, payload={"result": "action_ceiling"},
    )
    agent.last_event_id = prev
    return "finish_turn"


async def _agent_action(agent, rs, turn_id, action_index, caused_by):
    from oaos2.pricing.ledger import CostCapWouldBreach

    started = await rs.spine.emit_event(
        "action.started", agent_id=agent.agent_id, turn_id=turn_id,
        caused_by=caused_by, payload={"action_index": action_index},
    )
    observations = _observe(agent, rs)
    source_event_ids = list(dict.fromkeys(
        o["source_event_id"] for o in observations if o.get("source_event_id")
    ))
    observation_records = [Observation(
        observation_id=o["item_id"], agent_id=agent.agent_id,
        source_event_ids=([o["source_event_id"]] if o.get("source_event_id") else []),
        summary=o["kind"],
    ) for o in observations]
    agent_view = AgentView(
        agent_view_id=new_ulid(), agent_id=agent.agent_id, turn_id=turn_id,
        observation_ids=[o.observation_id for o in observation_records],
    )
    observed = await rs.spine.emit_event(
        "agent.observed", agent_id=agent.agent_id, turn_id=turn_id,
        caused_by=[started, *source_event_ids],
        payload={"observations": observations,
                 "observation_records": [o.model_dump() for o in observation_records],
                 "agent_view": agent_view.model_dump()},
    )

    ctx = TurnContext(turn_id=turn_id, action_index=action_index, caused_by=observed,
                      observations=observations)
    try:
        plan = await agent.behavior(agent, rs, ctx)
    except CostCapWouldBreach:
        # The pre-dispatch cap refused the next call — wrap up, never mid-thought.
        return "cost_capped", observed

    last = plan.last_event_id or observed
    for w in plan.writes:
        if rs.workspace is not None:
            tc = await rs.spine.emit_event(
                "tool.called", agent_id=agent.agent_id, turn_id=turn_id, caused_by=last,
                payload={"tool_name": "edit" if w.edit else "write"},
            )
            fc = await rs.workspace.capture_write(
                agent_id=agent.agent_id, path=w.path, new_bytes=w.data, zone=w.zone,
                tool_call_event_id=tc, turn_id=turn_id, edit=w.edit,
            )
            last = fc.file_change_id  # not an event id, but a stable ref; chain via tc below
            last = tc

    for tc in plan.tool_calls:
        called = await rs.spine.emit_event(
            "tool.called", agent_id=agent.agent_id, turn_id=turn_id, caused_by=last,
            payload={"tool_call_id": tc.tool_call_id or new_ulid(), "tool_name": tc.name},
        )
        last = await rs.spine.emit_event(
            "tool.result", agent_id=agent.agent_id, turn_id=turn_id, caused_by=called,
            payload={"tool_name": tc.name},
        )

    for resp in plan.chat_responses:
        await _handle_response_to_pause(resp, agent, rs, caused_by=last)

    for msg in plan.messages:
        await _send_message(msg, agent, rs, caused_by=msg.caused_by_event_id or last)

    if plan.conversation_volley is not None:
        # The floor-holder speaks: emit conversation.volley and hand the text to the
        # driver awaiting on the conversation's inbox (M5 §2.6).
        last = await _handle_conversation_volley(plan.conversation_volley, agent, rs, caused_by=last)
        done = await rs.spine.emit_event(
            "action.completed", agent_id=agent.agent_id, turn_id=turn_id, caused_by=last,
            payload={"result": "volleyed"},
        )
        return "finish_turn", done

    if plan.conversation_open is not None:
        # Launch the conversation as a detached driver so neither participant blocks the
        # other; the opener ends its turn and re-enters as a forced floor-holder (§2.6).
        opened = await _open_conversation(plan.conversation_open, agent, rs, caused_by=last)
        done = await rs.spine.emit_event(
            "action.completed", agent_id=agent.agent_id, turn_id=turn_id, caused_by=opened,
            payload={"result": "conversation_opened"},
        )
        return "finish_turn", done

    if plan.chat_request is not None:
        resumed = await _handle_pause(plan.chat_request, agent, rs, turn_id, caused_by=last)
        done = await rs.spine.emit_event(
            "action.completed", agent_id=agent.agent_id, turn_id=turn_id, caused_by=resumed,
            payload={"result": "resumed"},
        )
        return "continue", done

    done = await rs.spine.emit_event(
        "action.completed", agent_id=agent.agent_id, turn_id=turn_id, caused_by=last,
        payload={"result": plan.result},
    )
    if plan.result == "closed":
        rs.close_outcome()
        return "closed", done
    return plan.result, done


def _observe(agent: AgentRuntime, rs: RuntimeState) -> list[dict]:
    mb = rs.mailbox.get(agent.agent_id)
    if mb is None:
        return []
    items = mb.drain()
    observations = []
    for item in items:
        observation = {"item_id": item.item_id, "kind": item.kind, "payload": item.payload}
        if item.source_event_id is not None:
            observation["source_event_id"] = item.source_event_id
        observations.append(observation)
    return observations


# --------------------------------------------------------------------------- #
# Messaging / broadcast
# --------------------------------------------------------------------------- #


async def _deliver(item: MailboxItem, target_agent_id: str, rs: RuntimeState) -> str:
    mb = rs.mailbox.setdefault(target_agent_id, Mailbox(MailboxPolicy()))
    return mb.enqueue(item)


def _resolve_broadcast_targets(msg: MessageIntent, sender: AgentRuntime, rs: RuntimeState) -> list[str]:
    """Resolve a broadcast's recipients from its declared scope (M5 §2.7).

    - ``topology_subgraph`` (default): every other agent (the foundation has a
      complete topology; a pack with explicit channels would narrow this).
    - ``role_class``: agents sharing the sender's role_id.
    - ``whole_organization``: every other agent, but ONLY with an explicit org
      grant (``rs.allow_whole_org_broadcast``); otherwise the broadcast is empty
      and a protocol.violation is the caller's to record.
    """
    from oaos2.communication.messages import BroadcastScope

    others = [a for a in rs.agents if a != sender.agent_id]
    if msg.scope == BroadcastScope.ROLE_CLASS.value:
        return [a for a in others if rs.agents[a].role_id == sender.role_id]
    if msg.scope == BroadcastScope.WHOLE_ORGANIZATION.value:
        return others if rs.allow_whole_org_broadcast else []
    return others  # topology_subgraph


_MSG_TEXT_CAP = 8000  # verbatim payload text persisted on handoff / message.sent events


def _payload_text(payload) -> str:
    """Deterministic, capped serialization of what crossed the channel."""
    import json as _json

    if isinstance(payload, str):
        return payload[:_MSG_TEXT_CAP]
    try:
        return _json.dumps(payload, sort_keys=True)[:_MSG_TEXT_CAP]
    except (TypeError, ValueError):
        return str(payload)[:_MSG_TEXT_CAP]


async def _route_handoff(msg: MessageIntent, sender: AgentRuntime, rs: RuntimeState,
                         caused_by: str, *, event_ids: list[str] | None = None) -> bool:
    """Enforce the HandoffContract before delivery (M6 §1): topology admissibility
    + required fields, and capture the HandoffDelta boundary-loss slot.

    Returns True if the handoff may be delivered; False (with a protocol.violation
    emitted) if the contract refuses it. When supplied, event_ids receives the
    recorded handoff event so delivery can cite it. With no contract set, handoffs
    pass but the HandoffDelta is still captured.
    """
    import json as _json

    from oaos2.trace.records import HandoffDelta

    contract = rs.handoff_contract
    target = msg.to_agent or ""
    to_role = rs.agents[target].role_id if target in rs.agents else target
    if contract is not None:
        if not contract.permits(sender.role_id, to_role, msg.kind):
            await rs.spine.emit_event(
                "protocol.violation", agent_id=sender.agent_id, caused_by=caused_by,
                payload={"reason": "handoff_not_in_topology", "from_role": sender.role_id,
                         "to_role": to_role, "kind": msg.kind},
            )
            return False
        payload_obj = msg.payload
        if isinstance(payload_obj, str):
            try:
                payload_obj = _json.loads(payload_obj)
            except (ValueError, TypeError):
                payload_obj = {}
        keys = set(payload_obj.keys()) if isinstance(payload_obj, dict) else set()
        missing = set(contract.required_fields) - keys
        if missing:
            await rs.spine.emit_event(
                "protocol.violation", agent_id=sender.agent_id, caused_by=caused_by,
                payload={"reason": "handoff_missing_fields", "missing": sorted(missing), "kind": msg.kind},
            )
            return False
    # Organization-structure admissibility (M5 §18.1), orthogonal to the task's
    # HandoffContract: the org topology gates which kinds flow between which roles, and
    # the RECIPIENT's decision rights gate whose handoffs it accepts. Both default to
    # permissive when unset (the four decomposition-only arms set neither).
    if rs.topology is not None and not rs.topology.allows(sender.role_id, to_role, msg.kind):
        await rs.spine.emit_event(
            "protocol.violation", agent_id=sender.agent_id, caused_by=caused_by,
            payload={"reason": "handoff_not_in_org_topology", "from_role": sender.role_id,
                     "to_role": to_role, "kind": msg.kind},
        )
        return False
    recipient_rights = rs.decision_rights.get(to_role)
    if recipient_rights is not None and not recipient_rights.can_accept_handoff_from(sender.role_id):
        await rs.spine.emit_event(
            "protocol.violation", agent_id=sender.agent_id, caused_by=caused_by,
            payload={"reason": "handoff_acceptance_denied", "from_role": sender.role_id,
                     "to_role": to_role},
        )
        return False
    # Capture the narration↔formalized boundary-loss slot (M6 §1, §19), even when
    # no refs are supplied — the record's existence is what later measurement hangs on.
    handoff_id = new_ulid()
    delta = HandoffDelta(
        handoff_delta_id=new_ulid(), handoff_id=handoff_id,
        narration_ref=msg.extensions.get("narration_ref"),
        formalized_payload_ref=msg.extensions.get("formalized_ref"),
        # CH1: the arm's declared channel form and the participant-vocabulary refs of
        # the source packets the formalized payload was written FROM — what the
        # archive-side carriage projection joins (DESIGN §17.1 boundary-loss).
        handoff_format=msg.extensions.get("handoff_format"),
        source_refs=[str(r) for r in (msg.extensions.get("source_refs") or [])],
    )
    event_id = await rs.spine.emit_event(
        "handoff", agent_id=sender.agent_id, caused_by=caused_by, channel="formal", audience="agent",
        payload={"handoff_id": handoff_id, "from_agent": sender.agent_id, "to_agent": target,
                 "kind": msg.kind, "handoff_delta": delta.model_dump(),
                 # WHAT crossed the channel, verbatim — downstream analysis (e.g. the D2/D8
                 # absorption scan) reads the trace, so an unrecorded payload is unmeasurable.
                 "payload_text": _payload_text(msg.payload)},
    )
    if event_ids is not None:
        event_ids.append(event_id)
    return True


async def _send_message(msg: MessageIntent, sender: AgentRuntime, rs: RuntimeState,
                        caused_by: str) -> list[tuple[str, str]]:
    """Route one message or broadcast. Returns [(target, message.sent event id)] for
    every delivery made; refusals (comm kind, grant, topology, relay) are recorded as
    events and absent from the list."""
    delivered: list[tuple[str, str]] = []
    rs.router.validate_kind(msg.kind)
    # Org-structure comm-kind policy (M5 §18.1): a role may only SEND the kinds its
    # comm_kinds grant lists. Permissive when unset (the four arms). Refused → dropped.
    sender_kinds = rs.comm_kinds.get(sender.role_id)
    if sender_kinds is not None and msg.kind not in sender_kinds:
        await rs.spine.emit_event(
            "protocol.violation", agent_id=sender.agent_id, caused_by=caused_by,
            payload={"reason": "comm_kind_not_permitted", "kind": msg.kind},
        )
        return delivered
    # An admission_directive declaration is the manager-agent's dispatch decision:
    # record it from the trace so the manager_dispatch scheduler reads an
    # agent-emitted directive, not an externally pre-set field (M5 §2.3).
    if msg.kind == "admission_directive":
        admit = msg.extensions.get("admit")
        if admit is None and msg.payload:
            admit = [a.strip() for a in str(msg.payload).split(",") if a.strip()]
        rs.manager_last_dispatch = list(admit or [])
        rs.recent_events.append({"event_class": "admission_directive",
                                 "agent_id": sender.agent_id, "admit": rs.manager_last_dispatch})
        rs.recent_events[:] = rs.recent_events[-64:]  # bounded tail
    if msg.scope == "whole_organization" and not rs.allow_whole_org_broadcast and msg.to_agent is None:
        await rs.spine.emit_event(
            "protocol.violation", agent_id=sender.agent_id, caused_by=caused_by,
            payload={"reason": "whole_organization_broadcast_without_grant", "kind": msg.kind},
        )
    targets = [msg.to_agent] if msg.to_agent else _resolve_broadcast_targets(msg, sender, rs)
    for target in targets:
        # Org topology (M5 §18.1): a message may only flow on a declared channel. With no
        # topology it's the complete graph (permissive). A disallowed edge is relay.blocked
        # (handoff edges were already gated in _route_handoff; this covers messages/broadcasts).
        to_role = rs.agents[target].role_id if target in rs.agents else target
        if (msg.kind != "handoff" and rs.topology is not None
                and not rs.topology.allows(sender.role_id, to_role, msg.kind)):
            await rs.spine.emit_event(
                "relay.blocked", agent_id=sender.agent_id, caused_by=caused_by,
                payload={"to": target, "kind": msg.kind, "reason": "not_in_org_topology"},
            )
            continue
        if rs.router.relay_blocked(msg.payload, target):
            await rs.spine.emit_event(
                "relay.blocked", agent_id=sender.agent_id, caused_by=caused_by,
                payload={"to": target, "kind": msg.kind},
            )
            continue
        item_id = msg.item_id or new_ulid()
        if msg.kind == "handoff":
            from dataclasses import replace

            handoff_events = []
            if not await _route_handoff(replace(msg, to_agent=target), sender, rs, caused_by,
                                        event_ids=handoff_events):
                continue
            sent = handoff_events[0]
        else:
            sent = await rs.spine.emit_event(
                "message.sent", agent_id=sender.agent_id, caused_by=caused_by,
                payload={"to": target, "item_id": item_id, "kind": msg.kind,
                         "payload_text": _payload_text(msg.payload)},
            )
        await _deliver(MailboxItem(item_id=item_id, kind=msg.kind, payload=msg.payload,
                                   source_event_id=sent), target, rs)
        delivered.append((target, sent))
        rs.kick_scheduler()
    return delivered


# --------------------------------------------------------------------------- #
# Pause / resume (the max_rounds=1 clarification, M5 §2.4)
# --------------------------------------------------------------------------- #


async def _handle_pause(req: ChatRequest, agent: AgentRuntime, rs: RuntimeState, parent_turn_id: str, caused_by: str) -> str:
    if rs.outcome_closed:
        return await rs.spine.emit_event(
            "chat.declined", agent_id=agent.agent_id, turn_id=parent_turn_id,
            caused_by=caused_by, payload={"reason": "run_closed", "target_agent_id": req.to_agent})
    # Pause-inside-conversation invariant (M5 §2.4): an agent holding/awaiting a
    # conversation floor MAY NOT open a cross-agent pause — mid-conversation
    # clarification is the conversation's own volley, not a nested pause (otherwise the
    # forced-admission of a pause target would collide with the floor's mutual exclusion).
    if any(agent.agent_id in c.participants for c in rs.open_conversations.values() if not c.closed):
        return await rs.spine.emit_event(
            "chat.declined", agent_id=agent.agent_id, turn_id=parent_turn_id, caused_by=caused_by,
            channel="informal", audience="agent",
            payload={"reason": "floor_held", "target_agent_id": req.to_agent},
        )

    # Nesting depth chains through the OPEN pauses: if this pausing agent is itself
    # the target of an unresolved pause, it is servicing a request, so its new pause
    # is one level deeper. (The agent's turn_id carries no nesting marker, so counting
    # "~" on it would always yield depth 1 and never enforce the bound.)
    servicing = [pt.nesting_depth for pt in rs.paused_turns.values()
                 if pt.target_agent_id == agent.agent_id and pt.resolution_kind is None]
    depth = (max(servicing) + 1) if servicing else 1
    if depth > rs.max_nesting_depth:
        return await rs.spine.emit_event(
            "chat.declined", agent_id=agent.agent_id, turn_id=parent_turn_id, caused_by=caused_by,
            payload={"reason": "nesting_depth_exceeded", "depth": depth},
        )

    # Monotonic suffix so a paused_turn_id is never reissued after a prior pause is
    # popped on resolution (len(paused_turns)+1 could collide and overwrite the
    # earlier pause's index row).
    rs.pause_counter += 1
    paused_turn_id = f"{parent_turn_id}~{req.to_agent}.{rs.pause_counter}"
    pt = PausedTurnRecord(
        paused_turn_id=paused_turn_id, parent_turn_id=parent_turn_id,
        pausing_agent_id=agent.agent_id, target_agent_id=req.to_agent,
        request_payload=req.payload, resume_event=asyncio.Event(), nesting_depth=depth,
        deadline_seconds=rs.now() + req.timeout_seconds,
    )
    rs.paused_turns[paused_turn_id] = pt
    requested = await rs.spine.emit_event(
        "chat.requested", agent_id=agent.agent_id, turn_id=parent_turn_id, caused_by=caused_by,
        channel="informal", audience="agent",
        payload={"paused_turn_id": paused_turn_id, "target_agent_id": req.to_agent, "text": req.payload},
    )
    pt.requested_event_id = requested
    await rs.spine.emit_event(
        "turn.paused", agent_id=agent.agent_id, turn_id=parent_turn_id, caused_by=requested,
        payload={"paused_turn_id": paused_turn_id},
    )
    # Deliver the request into the target's mailbox so observe() surfaces it.
    await _deliver(
        MailboxItem(item_id=new_ulid(), kind="clarification_request",
                    payload={"paused_turn_id": paused_turn_id, "from": agent.agent_id, "text": req.payload},
                    source_event_id=requested),
        req.to_agent, rs,
    )
    agent.status = "paused"
    rs.kick_scheduler()  # mutate state THEN kick (so the snapshot sees the open pause)

    try:
        if pt.resolution_kind is None:
            await pt.resume_event.wait()

        agent.status = "running"
        return await rs.spine.emit_event(
            "agent.resumed", agent_id=agent.agent_id, turn_id=parent_turn_id,
            caused_by=pt.resolved_at_event_id,
            payload={"paused_turn_id": paused_turn_id, "resolution": pt.resolution_kind},
        )
    finally:
        rs.paused_turns.pop(paused_turn_id, None)
        rs.kick_scheduler()


async def _handle_response_to_pause(resp: ChatResponse, responder: AgentRuntime, rs: RuntimeState, caused_by: str) -> None:
    pt = rs.paused_turns.get(resp.paused_turn_id)
    if pt is None or pt.resolution_kind is not None:
        await rs.spine.emit_event(
            "chat.response", agent_id=responder.agent_id, caused_by=caused_by,
            channel="informal", audience="researcher",
            payload={"paused_turn_id": resp.paused_turn_id, "late": True},
        )
        return
    if resp.ignore:
        # Consumed-but-no-reply (M5 §2.7): record chat.ignored and leave the pause
        # UNRESOLVED — it resolves by timeout unless the responder later binds a reply.
        await rs.spine.emit_event(
            "chat.ignored", agent_id=responder.agent_id,
            caused_by=[pt.requested_event_id, caused_by], channel="informal", audience="agent",
            payload={"paused_turn_id": resp.paused_turn_id, "responder_agent_id": responder.agent_id},
        )
        return
    if resp.decline:
        # Refusal-as-authority: resolve the pause with chat.declined, a distinct
        # disposition from a substantive response (M5 §2.7).
        pt.resolution_kind = "declined"  # claim atomically (no await before this)
        pt.resolved_at_event_id = await rs.spine.emit_event(
            "chat.declined", agent_id=responder.agent_id,
            caused_by=[pt.requested_event_id, caused_by], channel="informal", audience="agent",
            payload={"paused_turn_id": resp.paused_turn_id, "responder_agent_id": responder.agent_id,
                     "reason": resp.reason},
        )
        pt.resume_event.set()
        return
    pt.resolution_kind = "response"  # claim atomically (no await before this)
    pt.resolved_at_event_id = await rs.spine.emit_event(
        "chat.response", agent_id=responder.agent_id,
        caused_by=[pt.requested_event_id, caused_by], channel="informal", audience="agent",
        payload={"paused_turn_id": resp.paused_turn_id, "responder_agent_id": responder.agent_id,
                 "text": resp.payload},
    )
    pt.resume_event.set()


# --------------------------------------------------------------------------- #
# Live conversations: rotate the speaker among the contract's participants.
# The runtime admits the requested speaker while the others wait. Explicit round
# limits and the safety ceiling bound contributions; mailbox waits have timeouts.
# Per-conversation spending and context-pressure checks are still placeholders.
# --------------------------------------------------------------------------- #

# Bound contributions even when the contract relies on an inactive stop setting.
_CONVERSATION_SAFETY_CEILING = 1000
# The driver polls the volley inbox at this cadence so it can detect a dead/retired
# floor-holder or run-end instead of blocking forever; and abandons a single volley that
# never arrives after this wall-clock cap (generous — a live model turn can be minutes).
_VOLLEY_POLL_TICK = 0.2
_VOLLEY_WALL_CLOCK_CAP = 600.0


def _gen_conversation_id(opener_id: str) -> str:
    return f"conv-{opener_id}-{new_ulid()}"


def _contract_summary(contract) -> dict:
    return {
        "participants": list(contract.participants),
        "floor_order": contract.floor_order,
        "agent_closure": contract.agent_closure,
        "max_rounds": contract.max_rounds,
        "max_cost_usd": contract.max_cost_usd,
        "stop_at_first_compaction": contract.stop_at_first_compaction,
    }


def _has_done_marker(text: str, contract) -> bool:
    return bool(text) and contract.done_marker in text


def _agent_closure_met(contract, done: dict) -> bool:
    vals = list(done.values())
    if contract.agent_closure == "first_done":
        return any(vals)
    return bool(vals) and all(vals)  # mutual_done (default)


def _conversation_cost(rs: RuntimeState, conv_id: str) -> float:
    """Return 0.0: spending is not yet attributed to individual conversations."""
    return 0.0


def _would_compact(rs: RuntimeState, agent_id: str) -> bool:
    """Return False: the conversation driver has no connected context-pressure check.

    Model agents separately manage their request context. This placeholder does
    not make stop_at_first_compaction close a conversation."""
    return False


def _most_loaded(participants, rs: RuntimeState) -> str:
    """Return the first participant; context-load comparison is not implemented here."""
    return participants[0]


async def _begin_conversation(rs: RuntimeState, contract, opener_id: str, caused_by):
    """Validate, emit conversation.opened, register the live state, and re-gate."""
    from oaos2.communication.conversation import ConversationState

    contract.validate()  # distinct participants and at least one declared stopping setting
    conv_id = _gen_conversation_id(opener_id)
    participants = tuple(contract.participants)
    opened = await rs.spine.emit_event(
        "conversation.opened", agent_id=opener_id, caused_by=caused_by,
        channel="informal", audience="agent",
        payload={"conversation_id": conv_id, "participants": list(participants),
                 "label": getattr(contract, "label", ""),
                 "contract": _contract_summary(contract)},
    )
    conv = ConversationState(
        conversation_id=conv_id, contract=contract, floor_holder_id=opener_id,
        opened_at_event_id=opened, volley_inbox=asyncio.Queue(),
        done={p: False for p in participants},
    )
    rs.open_conversations[conv_id] = conv
    # No kick yet: the opener's volley-0 is driver-supplied (it spoke at open), so the
    # opener is NOT scheduled for it. The driver kicks once it awaits the partner.
    return conv, opened


async def run_conversation(contract, rs: RuntimeState, opener_id: str, opening_payload: str,
                           caused_by, *, volley_provider=None):
    """Drive a live conversation to a layered close (M5 §2.6). Returns the
    ``conversation.closed`` event id. ``volley_provider`` is injectable for tests; the
    default sources each volley from the floor-holder via the mailbox + scheduler."""
    conv, opened = await _begin_conversation(rs, contract, opener_id, caused_by)
    return await _drive_conversation(rs, conv, opener_id, opening_payload, opened, volley_provider)


async def _open_conversation(intent, opener: AgentRuntime, rs: RuntimeState, caused_by) -> str:
    """Agent-loop entry: set up the conversation and spawn its driver concurrently so
    neither participant blocks the other (M5 §2.6). Returns conversation.opened."""
    from oaos2.communication.conversation import ConversationContract

    contract = intent.contract or ConversationContract(participants=(opener.agent_id, intent.partner))
    conv, opened = await _begin_conversation(rs, contract, opener.agent_id, caused_by)
    coro = _guarded_conversation(rs, conv, opener.agent_id, intent.opening_payload, opened)
    if rs._spawn is not None:
        rs._spawn(coro)
    else:  # no nursery (e.g. a unit harness) — drive inline as a fallback
        await coro
    return opened


async def _guarded_conversation(rs: RuntimeState, conv, opener_id: str, opening_payload, opened) -> None:
    """Catch a conversation-driver failure, record it, and close that conversation.

    Keep the exception from automatically canceling the sibling agent loops."""
    try:
        await _drive_conversation(rs, conv, opener_id, opening_payload, opened, None)
    except Exception as exc:  # noqa: BLE001 — isolate the detached driver
        try:
            await rs.spine.emit_event(
                "protocol.violation", caused_by=conv.opened_at_event_id,
                payload={"reason": "conversation_driver_error",
                         "conversation_id": conv.conversation_id, "error": repr(exc)},
            )
        except Exception:  # noqa: BLE001 — even the error-emit must not propagate
            pass
        if not conv.closed:
            conv.closed = True
            rs.open_conversations.pop(conv.conversation_id, None)
            rs.kick_scheduler()


class _ConversationAbandoned(Exception):
    """The awaited floor-holder will never volley (run ended / retired / timed out), so the
    driver must close the conversation rather than park on the inbox forever (M5 §2.6)."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


async def _mailbox_volley_provider(rs: RuntimeState, conv, floor: str, prev):
    """Default volley source: request a volley from the floor-holder via its mailbox,
    then await the volley the floor-holder's action puts on the conversation inbox.

    The wait is INTERRUPTIBLE: it wakes periodically to check liveness so it can never
    park forever — if the run is ending, the floor-holder has retired/vanished, or the
    per-volley wall-clock cap is exceeded, it abandons and the driver closes the chat.
    """
    transcript = [{"speaker": s, "text": t} for s, t in conv.transcript]
    conv.awaiting_volley_from = floor  # mutate THEN deliver THEN kick (snapshot sees it)
    await _deliver(
        MailboxItem(item_id=new_ulid(), kind="conversation_volley_request",
                    payload={"conversation_id": conv.conversation_id, "from": conv.prev_floor(floor),
                             "transcript": transcript,
                             # per-conversation instruction override (contract-declared);
                             # lets one agent serve differently-purposed conversations
                             "volley_instruction": getattr(conv.contract, "volley_instruction", None)},
                    source_event_id=prev),
        floor, rs,
    )
    rs.kick_scheduler()  # force-admit the awaited floor-holder
    deadline = rs.now() + _VOLLEY_WALL_CLOCK_CAP
    while True:
        try:
            return await asyncio.wait_for(conv.volley_inbox.get(), timeout=_VOLLEY_POLL_TICK)
        except asyncio.TimeoutError:
            agent = rs.agents.get(floor)
            # Specific cause first: a retired/vanished floor-holder is reported as such even
            # if the run is also ending (more informative than the generic run_ended).
            if agent is None or agent.retired:
                raise _ConversationAbandoned("floor_holder_unavailable")
            if conv.closed or rs.is_done():
                raise _ConversationAbandoned("run_ended")
            if rs.now() >= deadline:
                raise _ConversationAbandoned("volley_timeout")


def _closure_layer(contract, conv, rs, floor, opener_id, rounds_completed):
    """The closure ladder, evaluated after every volley (M5 §2.6). Returns
    ``(reason, layer)`` for the first layer that fires, else None (continue)."""
    if _agent_closure_met(contract, conv.done):  # Layer 2 — the healthy exit
        return ("agent_done", "agent_done")
    # Layer 0 — hard backstops (≥1 finite). max_rounds counts round-trips, so
    # max_rounds=1 closes only after the partner (non-opener) has answered.
    if contract.max_rounds and rounds_completed >= contract.max_rounds and floor != opener_id:
        return ("max_rounds", "hard_backstop")
    if contract.max_cost_usd and _conversation_cost(rs, conv.conversation_id) >= contract.max_cost_usd:
        return ("max_cost", "hard_backstop")
    if contract.stop_at_first_compaction and _would_compact(rs, _most_loaded(contract.participants, rs)):
        return ("context_ceiling", "hard_backstop")
    if conv.volleys >= _CONVERSATION_SAFETY_CEILING:
        return ("safety_ceiling", "hard_backstop")
    return None


async def _drive_conversation(rs: RuntimeState, conv, opener_id: str, opening_payload: str,
                              opened, volley_provider):
    contract = conv.contract
    provider = volley_provider or _mailbox_volley_provider
    floor, prev = opener_id, opened
    n = len(contract.participants)
    try:
        while not conv.closed:
            if conv.volleys == 0 and opening_payload is not None:
                # The opener's opening volley was supplied at open — no round-trip (the
                # clarification/pause path). When opening_payload is None (e.g. a deliberation),
                # even volley-0 is sourced from the opener via the provider, so EVERY turn is
                # agent-produced and uniform.
                text, is_done = opening_payload, _has_done_marker(opening_payload, contract)
                prev = await rs.spine.emit_event(
                    "conversation.volley", agent_id=floor, caused_by=prev,
                    channel="informal", audience="agent",
                    payload={"conversation_id": conv.conversation_id, "speaker": floor,
                             "round_index": conv.volleys, "text": text},
                )
            else:
                try:
                    text, is_done, prev = await provider(rs, conv, floor, prev)
                except _ConversationAbandoned as ab:
                    # The floor-holder will never volley — close the chat as a hard backstop
                    # rather than leave this driver (and the run's TaskGroup) parked forever.
                    return await _close_conversation(rs, conv, ab.reason, "hard_backstop", prev)
            conv.transcript.append((floor, text))
            conv.done[floor] = conv.done.get(floor, False) or is_done
            conv.volleys += 1
            rounds_completed = conv.volleys // n

            layer = _closure_layer(contract, conv, rs, floor, opener_id, rounds_completed)
            if layer is not None:
                return await _close_conversation(rs, conv, layer[0], layer[1], prev)

            prev = await _maybe_warn(rs, conv, rounds_completed, prev) or prev  # Layer 1 (soft)
            floor = conv.next_floor(floor)  # pass the floor (rotation; n=2 → alternating)
            conv.floor_holder_id = floor
            rs.kick_scheduler()  # re-gate: new floor-holder forced, prior speaker withheld
    finally:
        if not conv.closed:  # error/cancel path — never leave a conversation dangling open
            conv.closed = True
            rs.open_conversations.pop(conv.conversation_id, None)
            rs.kick_scheduler()


async def _maybe_warn(rs: RuntimeState, conv, rounds_completed: int, prev):
    """Warn once when remaining rounds equal rounds_warn_remaining, then continue.

    Cost and context warning settings are not used by this function."""
    c = conv.contract
    if getattr(conv, "_warned", False) or not (c.max_rounds and c.rounds_warn_remaining):
        return None
    if (c.max_rounds - rounds_completed) != c.rounds_warn_remaining:
        return None
    conv._warned = True  # set on the (dataclass) state so it fires at most once
    return await rs.spine.emit_event(
        "context.pressure_warning", caused_by=prev, channel="informal", audience="agent",
        payload={"conversation_id": conv.conversation_id, "regulator": "rounds",
                 "rounds_remaining": c.rounds_warn_remaining, "max_rounds": c.max_rounds},
    )


async def _handle_conversation_volley(intent, agent: AgentRuntime, rs: RuntimeState, caused_by) -> str:
    """The floor-holder's volley action: emit conversation.volley and hand the text to
    the driver awaiting on the conversation inbox (M5 §2.6)."""
    conv = rs.open_conversations.get(intent.conversation_id)
    if conv is None or conv.closed:
        return await rs.spine.emit_event(
            "protocol.violation", agent_id=agent.agent_id, caused_by=caused_by,
            payload={"reason": "volley_after_close", "conversation_id": intent.conversation_id},
        )
    vev = await rs.spine.emit_event(
        "conversation.volley", agent_id=agent.agent_id, caused_by=caused_by,
        channel="informal", audience="agent",
        payload={"conversation_id": conv.conversation_id, "speaker": agent.agent_id,
                 "round_index": conv.volleys, "text": intent.text,
                 "budget_forced": bool(getattr(intent, "budget_forced", False))},
    )
    if getattr(intent, "budget_forced", False):
        conv.budget_forced[agent.agent_id] = True  # closure records forced vs free assent
    is_done = intent.done or _has_done_marker(intent.text, conv.contract)
    conv.awaiting_volley_from = None  # volley received; withhold both until the driver advances
    if conv.volley_inbox is not None:
        conv.volley_inbox.put_nowait((intent.text, is_done, vev))
    return vev


async def _close_conversation(rs: RuntimeState, conv, reason: str, layer: str, caused_by) -> str:
    conv.closed = True
    transcript = [{"speaker": s, "text": t} for s, t in conv.transcript]
    ev = await rs.spine.emit_event(
        "conversation.closed", caused_by=caused_by, channel="informal", audience="agent",
        payload={"conversation_id": conv.conversation_id, "reason": reason, "closure_layer": layer,
                 "volleys": conv.volleys, "transcript": transcript,
                 # Who assented only because the cost cap fired — an agent_done close where
                 # this is non-empty is NOT the same observable as a free mutual_done.
                 "budget_forced": sorted(getattr(conv, "budget_forced", {}) or {})},
    )
    rs.open_conversations.pop(conv.conversation_id, None)
    # Fold the transcript back to both participants so their resumed turns see the outcome.
    for p in conv.contract.participants:
        await _deliver(
            MailboxItem(item_id=new_ulid(), kind="conversation_closed",
                        payload={"conversation_id": conv.conversation_id, "reason": reason,
                                 "transcript": transcript}, source_event_id=ev),
            p, rs,
        )
    rs.kick_scheduler()  # participants leave the conversation; re-gate to their main turns
    return ev


# --------------------------------------------------------------------------- #
# Scheduler + timeout monitor
# --------------------------------------------------------------------------- #


def _always_ready() -> bool:
    return True


async def _scheduler_coro(rs: RuntimeState) -> None:
    while not rs.is_done():
        await rs.scheduler_wakeup.wait()
        rs.scheduler_wakeup.clear()  # clear BEFORE snapshot (lost-wakeup fix, §5)
        snap = rs.snapshot()
        # Selective policies must choose FROM ready agents.  Filtering only after a
        # round-robin/sequential policy chose one can wedge the scheduler forever when
        # that one agent is blocked: every kick selects and then removes the same role,
        # while a later ready role is never considered.  Forced pause/conversation
        # targets are added below and intentionally bypass this base readiness filter.
        if rs.readiness:
            snap.idle_agents = [
                agent_id for agent_id in snap.idle_agents
                if rs.readiness.get(agent_id, _always_ready)()
            ]
        base_admit = set(rs.scheduler_policy(snap))
        # Dependency-driven admission (deadlock fix): force pause targets AND the
        # participant a conversation is awaiting a volley from (§2.3). A floor-holder is
        # force-admitted only once its volley-request is pending (awaiting_volley_from);
        # the other participant is withheld — the floor token is mutual exclusion, so
        # exactly one participant acts per volley (§2.4). Between volleys neither is
        # admitted under the conversation (awaiting is None), so no idle spin.
        conv_awaited = {c.awaiting_volley_from for c in snap.open_conversations
                        if c.awaiting_volley_from}
        conv_blocked = {p for c in snap.open_conversations
                        for p in c.participants if p != c.awaiting_volley_from}
        forced = set(snap.open_pause_targets) | conv_awaited
        # Pause-servicing wins over conversation-blocking: a pending pause target that is
        # also a non-floor conversation participant must still be admitted to answer the
        # pause, or it and the pausing agent wedge (§2.4 floor_held prevents the inverse).
        conv_blocked -= forced
        admit = (base_admit | forced) - set(snap.paused_agents) - conv_blocked
        # Withhold admission from an agent whose `blocks` precondition is unmet (M5 §2.3):
        # it waits without running, re-evaluated on the next kick (commits/messages kick),
        # so there is no finish_turn busy-spin. Pause targets (forced) are never withheld.
        if rs.readiness:
            admit = {a for a in admit
                     if a in forced or rs.readiness.get(a, _always_ready)()}
        # Clocked rounds (kernel/clock.py): when nothing is admittable and nothing
        # is in flight, the round is over — advance the clock (which may dispatch
        # arrivals and force deadline fallbacks via the runner's callback) and
        # recompute admissions. Quiescence, not wall-clock, is what ends a round,
        # so replay determinism is untouched. With no ready work at all, rounds
        # fast-forward to the next arrival — time passes when nobody has work.
        if (rs.clock is not None and not admit and not rs.is_done()
                and not any(a.status == "running" for a in rs.agents.values())
                and not snap.open_pause_targets
                and not any(c.awaiting_volley_from for c in snap.open_conversations)):
            if await rs.clock.advance():
                rs.kick_scheduler()
                continue
        for agent_id, gate in rs.admission.items():
            if agent_id in admit:
                gate.set()
            else:
                gate.clear()
    # A paused turn waits on its own event, not its admission gate. Resolve
    # those waits before the timeout monitor exits on run closure.
    for pt in list(rs.paused_turns.values()):
        if pt.resolution_kind is None:
            pt.resolution_kind = "run_closed"
            try:
                pt.resolved_at_event_id = await rs.spine.emit_event(
                    "chat.declined", agent_id=pt.pausing_agent_id,
                    caused_by=pt.requested_event_id,
                    payload={"paused_turn_id": pt.paused_turn_id, "reason": "run_closed"})
            finally:
                pt.resume_event.set()
    # Closure: release every gate so the loops unblock, observe closure, and return.
    for gate in rs.admission.values():
        gate.set()


async def _timeout_monitor(rs: RuntimeState, tick: float) -> None:
    while not rs.is_done():
        await asyncio.sleep(tick)
        now = rs.now()
        for pt in list(rs.paused_turns.values()):
            if pt.resolution_kind is None and now >= pt.deadline_seconds:
                pt.resolution_kind = "timed_out"  # claim atomically
                pt.resolved_at_event_id = await rs.spine.emit_event(
                    "chat.timed_out", agent_id=pt.pausing_agent_id, caused_by=pt.requested_event_id,
                    audience="researcher", channel="infrastructure",
                    payload={"paused_turn_id": pt.paused_turn_id},
                )
                await rs.spine.emit_event(
                    "intervention.recorded", agent_id=pt.pausing_agent_id,
                    caused_by=pt.resolved_at_event_id,
                    payload={"kind": "pause_timeout_stub", "class": "recorded",
                             "paused_turn_id": pt.paused_turn_id},
                )
                pt.resume_event.set()


# --------------------------------------------------------------------------- #
# Helpers to build a runtime
# --------------------------------------------------------------------------- #


def make_agent(agent_id: str, behavior: AgentBehavior, role_id: str = "worker") -> AgentRuntime:
    return AgentRuntime(agent_id=agent_id, role_id=role_id, behavior=behavior)


def build_runtime(
    spine: RunSpine,
    agents: list[AgentRuntime],
    *,
    scheduler: str = "free",
    router: Router | None = None,
    workspace=None,
) -> RuntimeState:
    rs = RuntimeState(
        run_id=spine.run_id, spine=spine,
        agents={a.agent_id: a for a in agents},
        admission={a.agent_id: asyncio.Event() for a in agents},
        mailbox={a.agent_id: Mailbox(MailboxPolicy()) for a in agents},
        router=router or Router(),
        scheduler_policy=resolve_scheduler_policy(scheduler),
        workspace=workspace,
    )
    return rs
