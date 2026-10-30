"""Declare conversation participants, speaker rotation, and closure settings.

The same contract supports two-agent clarification and larger discussions.
Validation requires distinct participants and at least one declared stopping
setting. The runtime implements closure and adds time/round safeguards. The
per-conversation cost, context-pressure check, and free speaker selection remain incomplete;
a valid declaration alone does not make those controls effective.
See kernel/runtime.py and docs/mechanism/DEFERRED.md §1."""

from __future__ import annotations

from dataclasses import dataclass, field


class InvalidContract(Exception):
    """A conversation has invalid participants or lacks a declared stopping setting."""


@dataclass
class ConversationContract:
    participants: tuple  # ≥2 agents; the floor rotates through them in order
    floor_order: str = "alternating"  # rotating speaker; free selection is not implemented
    done_marker: str = "<satisfied/>"
    # Analysis label ("deliberation" | "ratification" | ...): stamped on conversation.opened
    # so derived views can split multi-conversation runs by phase. Free-form, not enumerated.
    label: str = ""
    # Per-conversation volley instruction override (a pack-declared apparatus constant, like
    # the deliberation instruction). None → the agent behavior's default applies. Carried in
    # each volley request so the SAME agents can hold differently-purposed conversations.
    volley_instruction: str | None = None

    # Agent-requested closure: mutual_done requires assent from every participant.
    agent_closure: str = "mutual_done"  # mutual_done (all assent) | first_done

    # Warning settings; cost tracking remains incomplete
    context_warn_window_frac: float = 0.85
    cost_warn_frac: float = 0.85
    rounds_warn_remaining: int | None = 2

    # Stopping settings; validation requires at least one, but cost is not enforced here
    max_rounds: int | None = None
    max_cost_usd: float | None = None
    stop_at_first_compaction: bool = True

    def validate(self) -> None:
        """Require at least two distinct participants and a truthy stopping setting.

        This checks the declaration, not whether every setting is implemented or
        whether a numeric limit is positive and finite."""
        if len(self.participants) < 2:
            raise InvalidContract(
                f"ConversationContract needs ≥2 participants; got {len(self.participants)}"
            )
        if len(set(self.participants)) != len(self.participants):
            raise InvalidContract(f"ConversationContract participants must be distinct: {self.participants}")
        if not (self.max_rounds or self.max_cost_usd or self.stop_at_first_compaction):
            raise InvalidContract(
                "ConversationContract has no finite backstop — set at least one of "
                "max_rounds / max_cost_usd / stop_at_first_compaction"
            )

    @classmethod
    def clarification(cls, participants: tuple) -> "ConversationContract":
        """The tightest setting: opener asks, partner answers, close (M5 §2.4)."""
        return cls(
            participants=participants,
            floor_order="alternating",
            agent_closure="first_done",
            max_rounds=1,
        )


@dataclass
class ConversationState:
    """Track participants, speaker, contributions, and closure for an open conversation.

    The runtime keeps this object in RuntimeState.open_conversations. It admits
    the requested speaker while other participants wait. volley_inbox is the
    runtime's asynchronous queue for returned contributions."""

    conversation_id: str
    contract: ConversationContract
    floor_holder_id: str
    volleys: int = 0
    opened_at_event_id: str | None = None
    transcript: list = field(default_factory=list)  # [(agent_id, text)] in volley order
    done: dict = field(default_factory=dict)  # agent_id -> saw done marker this conversation
    budget_forced: dict = field(default_factory=dict)  # agent_id -> assent was cost-cap forced
    closed: bool = False
    volley_inbox: object | None = None  # asyncio.Queue, set by the runtime driver
    _warned: bool = False  # whether a wrap-up warning has already been sent
    # The participant the driver is currently awaiting a volley from (a request has been
    # delivered to its mailbox). The scheduler force-admits exactly this agent and
    # withholds the other participants — so a floor-holder is woken only when it has work, never
    # spun while idle (mirrors the pause target). None between volleys.
    awaiting_volley_from: str | None = None

    @property
    def participants(self) -> tuple:
        return self.contract.participants

    def next_floor(self, agent_id: str) -> str:
        """The next participant in rotation (the floor passes in `participants` order)."""
        p = self.contract.participants
        return p[(p.index(agent_id) + 1) % len(p)]

    def prev_floor(self, agent_id: str) -> str:
        """The previous participant in rotation (who last held the floor)."""
        p = self.contract.participants
        return p[(p.index(agent_id) - 1) % len(p)]

    def other(self, agent_id: str) -> str:
        """Back-compat alias; for a 2-party chat this is the other participant."""
        return self.next_floor(agent_id)
