"""Message kinds, per-agent mailboxes, routing checks, and group conversations.

The registry maps message kinds to common primitives. The router checks known
kinds and specified restricted substrings; callers perform delivery and record
violations. Conversations support two or more participants. See
communication/conversation.py and docs/mechanism/DEFERRED.md for limits."""

from oaos2.communication.conversation import ConversationContract, InvalidContract
from oaos2.communication.mailbox import Mailbox, MailboxItem, MailboxPolicy
from oaos2.communication.messages import (
    COMM_KIND_REGISTRY,
    COMM_PRIMITIVES,
    BroadcastScope,
    ChatRequest,
    ChatResponse,
    CommPrimitive,
    MessageIntent,
)
from oaos2.communication.router import ProtocolViolationError, Router

__all__ = [
    "COMM_KIND_REGISTRY",
    "COMM_PRIMITIVES",
    "BroadcastScope",
    "ChatRequest",
    "ChatResponse",
    "CommPrimitive",
    "ConversationContract",
    "InvalidContract",
    "Mailbox",
    "MailboxItem",
    "MailboxPolicy",
    "MessageIntent",
    "ProtocolViolationError",
    "Router",
]
