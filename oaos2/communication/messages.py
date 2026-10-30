"""Define message primitives and register task-specific message kinds.

The common primitives are message, request, response, and declaration. A kind
such as clarification_request is a validated registry entry. These data types
do not themselves pause an agent, deliver a message, or aggregate decisions;
callers in the runtime implement those actions. Group conversations use
conversation.py; work sequencing uses registered coordination procedures."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from oaos2.registry import Registry, RegistrySpec


class CommPrimitive(str, Enum):
    MESSAGE = "message"
    REQUEST = "request"
    RESPONSE = "response"
    DECLARATION = "declaration"


COMM_PRIMITIVES: frozenset[str] = frozenset(p.value for p in CommPrimitive)


# Open kind registry → primitive (DESIGN §11.1). Packs extend via inherits_from.
_FOUNDATION_KINDS: dict[str, str] = {
    "message": CommPrimitive.MESSAGE.value,
    "clarification_request": CommPrimitive.REQUEST.value,
    "clarification_response": CommPrimitive.RESPONSE.value,
    "review": CommPrimitive.MESSAGE.value,
    "announce": CommPrimitive.DECLARATION.value,
    "admission_directive": CommPrimitive.DECLARATION.value,  # manager_dispatch (M5 §2.3)
    "handoff": CommPrimitive.DECLARATION.value,
    "note": CommPrimitive.MESSAGE.value,  # agent-initiated private note (M8 §7, PC1)
}

COMM_KIND_SPEC: RegistrySpec[str] = RegistrySpec(
    registry_id="oaos2.foundation.comm_kinds", entries=_FOUNDATION_KINDS
)
COMM_KIND_REGISTRY: Registry[str] = COMM_KIND_SPEC.resolve()


class BroadcastScope(str, Enum):
    TOPOLOGY_SUBGRAPH = "topology_subgraph"  # default
    ROLE_CLASS = "role_class"
    WHOLE_ORGANIZATION = "whole_organization"  # requires explicit org grant


@dataclass
class ChatRequest:
    """A single-target request that pauses the requester (M5 §2.4)."""

    to_agent: str
    payload: str
    timeout_seconds: float = 30.0
    kind: str = "clarification_request"


@dataclass
class ChatResponse:
    """A reply binding back to a paused turn (M5 §2.4).

    ``decline=True`` is *refusal-as-authority*: the responder resolves the pause
    by declining rather than answering (e.g. a role with the authority to say
    "no"). It resolves to ``chat.declined`` with ``reason`` (default ``refusal``),
    a distinct measurement from a substantive ``chat.response`` (M5 §2.7) — the
    three dispositions must never be conflated.
    """

    paused_turn_id: str
    payload: str = ""
    kind: str = "clarification_response"
    decline: bool = False
    reason: str = "refusal"
    # ``ignore=True``: the responder read the request and chose NOT to reply — a third
    # disposition, distinct from decline (refusal-as-authority) and timeout (deadline).
    # It emits chat.ignored and does NOT resolve the pause (which still times out unless
    # a later reply binds back). Conflating the three would erase a measurement (§2.7).
    ignore: bool = False


@dataclass
class MessageIntent:
    """A one-way message or broadcast (M5 §2.7)."""

    to_agent: str | None  # None ⇒ broadcast
    payload: str
    kind: str = "message"
    scope: str = BroadcastScope.TOPOLOGY_SUBGRAPH.value
    item_id: str = ""
    extensions: dict = field(default_factory=dict)
    # A behavior can bind each transfer to the particular commitment/tool result
    # that produced it, even when several transfers leave in one ActionPlan.
    caused_by_event_id: str | None = None
