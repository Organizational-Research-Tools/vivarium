"""Queue messages for one agent and apply the declared overflow behavior.

FIFO preserves insertion order; priority delivery sorts higher priorities first.
TOPIC_KEYED currently falls back to FIFO, and read_receipt is not implemented.
On overflow, policies can discard the oldest/newest message or retain it in a
dead-letter list. BACKPRESSURE does not block here: the item is still enqueued,
so callers must enforce their own bound. Queue depth alone is not a measure of
an agent's information overload."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Ordering(str, Enum):
    FIFO = "fifo"
    PRIORITY = "priority"
    TOPIC_KEYED = "topic_keyed"


class Overflow(str, Enum):
    DROP_OLDEST = "drop_oldest"
    DROP_NEWEST = "drop_newest"
    BACKPRESSURE = "backpressure"
    DEAD_LETTER = "dead_letter"


@dataclass
class MailboxPolicy:
    ordering: str = Ordering.FIFO.value
    capacity: int = 1024
    overflow: str = Overflow.DROP_OLDEST.value
    read_receipt: bool = False


@dataclass
class MailboxItem:
    item_id: str
    kind: str
    payload: Any
    priority: int = 0
    # Event that caused this delivery, when the producer has one.  Environment
    # packets use it to make the eventual AgentView causally descend from the
    # exogenous event rather than merely appearing beside it in the archive.
    source_event_id: str | None = None


@dataclass
class Mailbox:
    policy: MailboxPolicy = field(default_factory=MailboxPolicy)
    _items: deque = field(default_factory=deque)
    dead_letter: list = field(default_factory=list)

    def enqueue(self, item: MailboxItem) -> str:
        """Enqueue under the policy; return an overflow tag ("" if none)."""
        if len(self._items) >= self.policy.capacity:
            if self.policy.overflow == Overflow.DROP_OLDEST.value:
                self._items.popleft()
                self._items.append(item)
                return "drop_oldest"
            if self.policy.overflow == Overflow.DROP_NEWEST.value:
                return "drop_newest"  # the new item is dropped
            if self.policy.overflow == Overflow.DEAD_LETTER.value:
                self.dead_letter.append(item)
                return "dead_letter"
            # backpressure: caller must handle; we still enqueue here (bounded by caller)
        self._items.append(item)
        return ""

    def drain(self) -> list[MailboxItem]:
        """Remove and return all items in delivery order (FIFO; priority sorts desc)."""
        items = list(self._items)
        self._items.clear()
        if self.policy.ordering == Ordering.PRIORITY.value:
            items.sort(key=lambda i: -i.priority)
        return items

    def depth(self) -> int:
        return len(self._items)
