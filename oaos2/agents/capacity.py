"""Enforce the call-count limits for one agent.

CapacityPolicy owns one agent's total call limit, the daily limit in clocked runs,
and the limit for the current submission slot. It also tracks whether a slot's
final-call warning and fallback have already been issued. A slot is the work
needed for one declared commitment; its counter resets when that binding changes.

Check an exhausted slot's pending fallback even when the daily or global limit
ends the turn. Counters remain in the agent's persistent state dictionary.
CostLedger and the model gateway separately enforce spending and output-token
budgets. Calls used for context summarization also count toward call limits."""

from __future__ import annotations


class CapacityPolicy:
    def __init__(self, state: dict, *, max_model_calls: int,
                 max_calls_per_turn: int | None = None,
                 max_calls_per_slot: int | None = None) -> None:
        self.st = state
        self.max_model_calls = max_model_calls
        self.max_calls_per_turn = max_calls_per_turn
        self.max_calls_per_slot = max_calls_per_slot

    # ------------------------------------------------------------- charges --
    def charge_provider_call(self, n: int = 1) -> None:
        """Every PROVIDER call spends the day's budget AND the run-global
        ceiling — work, deliberation volleys, and compaction alike (audit
        rounds 4 P1-1 and 5 P1-4: compaction/deliberation previously escaped
        one or both counters). All three dispatch sites funnel through
        ``call_model_gateway`` and charge here."""
        if self.max_calls_per_turn is not None:
            self.st["_calls_this_turn"] = self.st.get("_calls_this_turn", 0) + n
        self.st["calls"] = self.st.get("calls", 0) + n

    def charge_slot_call(self) -> None:
        """A completed main-loop call additionally spends the bound slot's
        budget (the day/global legs were charged pre-dispatch)."""
        self.st["_slot_calls"] = self.st.get("_slot_calls", 0) + 1

    def exhausted(self) -> str | None:
        """One admission verdict shared by every provider-call path (audit
        round 6 P1-1): which ceiling forbids the next call — "day" (the
        working day ends, duties resume tomorrow), "global" (the agent
        retires), or None (admissible). Checked at turn open AND re-checked
        immediately before the main dispatch, because deliberation/compaction
        charges may have landed in between. Global DOMINATES (audit round 7
        P2-4): when one call exhausts both ceilings, the terminal verdict
        wins — the agent retires rather than surviving into another day."""
        if self.global_exhausted():
            return "global"
        if self.day_exhausted():
            return "day"
        return None

    # ---------------------------------------------------------- day budget --
    def begin_turn(self, turn_id) -> None:
        """Reset the daily counter when a new turn (working day) opens."""
        if self.max_calls_per_turn is None:
            return
        if self.st.get("_turn_for_calls") != turn_id:
            self.st["_turn_for_calls"] = turn_id
            self.st["_calls_this_turn"] = 0

    def day_exhausted(self) -> bool:
        return (self.max_calls_per_turn is not None
                and self.st.get("_calls_this_turn", 0) >= self.max_calls_per_turn)

    # ------------------------------------------------------- global ceiling --
    def global_exhausted(self) -> bool:
        return self.st.get("calls", 0) >= self.max_model_calls

    def call_fraction(self) -> float:
        return (self.st.get("calls", 0) / self.max_model_calls
                if self.max_model_calls else 0.0)

    # ---------------------------------------------------------- slot budget --
    def bind_slot(self, slot) -> None:
        """Slot-scoped counters reset when the staged binding advances."""
        if slot != self.st.get("_slot_id"):
            self.st["_slot_id"] = slot
            self.st["_slot_calls"] = 0
            self.st["_slot_warned"] = False

    def slot_exhausted(self, slot) -> bool:
        return (bool(self.max_calls_per_slot) and slot is not None
                and self.st.get("_slot_calls", 0) >= self.max_calls_per_slot)

    def claim_slot_fallback(self, slot) -> bool:
        """True exactly once per starved slot: the caller must commit the
        contract-declared fallback. Idempotent across day-end, global-cap
        retirement, and the in-loop ceiling check — whichever fires first."""
        if not self.slot_exhausted(slot):
            return False
        if self.st.get("_slot_ceiling_fired") == slot:
            return False
        self.st["_slot_ceiling_fired"] = slot
        return True

    def claim_slot_warning(self, slot) -> bool:
        """True exactly once, on the slot's final available call (ceiling-1) —
        a declared apparatus constant, uniform across roles and arms."""
        if (bool(self.max_calls_per_slot) and slot is not None
                and not self.st.get("_slot_warned")
                and self.st.get("_slot_calls", 0) == self.max_calls_per_slot - 1):
            self.st["_slot_warned"] = True
            return True
        return False
