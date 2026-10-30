"""Advance experiment-defined work days when the current round is idle.

Each live role may complete at most one turn in a round. The clock advances when
no role has remaining work it can start in that round. It tracks counters;
the runner's on_round callback records round events, delivers notices, and
applies deadlines. RuntimeState.clock=None leaves this mechanism inactive.
Round advancement depends on work state, not elapsed seconds."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ClockState:
    """Round bookkeeping for one clocked run.

    ``rounds_total`` is the final scheduled round; one further advance (the
    past-final tick) is allowed so the runner's callback can force outstanding
    deadline fallbacks and close the outcome. If the outcome still does not
    close, the run's deadlock backstop is the safety net — the clock never spins
    past ``rounds_total + 1``.
    """

    rounds_total: int
    round_no: int = 0  # 0 = pre-first-round; the first advance opens round 1
    acted: set[str] = field(default_factory=set)  # agent_ids that used this round's turn
    on_round: object | None = None  # async callback(round_no), wired by the runner

    def exhausted(self) -> bool:
        return self.round_no >= self.rounds_total + 1

    async def advance(self) -> bool:
        """Open the next round. Returns False when the clock is exhausted."""
        if self.exhausted():
            return False
        self.round_no += 1
        self.acted.clear()
        if self.on_round is not None:
            await self.on_round(self.round_no)
        return True
