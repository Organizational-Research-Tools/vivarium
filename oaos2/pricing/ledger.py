"""Reserve and settle a run's shared spending and output-token budgets.

admit checks completed usage plus outstanding reservations before starting a call.
It estimates input at the normal input rate and output at max_output_tokens.
Concurrent calls therefore cannot all claim the same remaining estimated budget.
apply settles reported usage; release removes reservations only when no usage
remains unknown. Unsettled dispatched calls keep their reservation and block
further dispatch until usage can be resolved.

The check does not interrupt an in-progress call. Its spending protection depends
on the adapter estimate and the recorded pricing table being appropriate. The
optional final token reserve limits earlier work; it does not guarantee that an
agent completes a final submission."""

from __future__ import annotations

from dataclasses import dataclass, field
import math

from oaos2.models.types import ModelRequest
from oaos2.pricing.attribution import CostRecord
from oaos2.pricing.table import PricingTable


def validate_spending_cap(value: float, *, allow_unbounded: bool = False) -> float:
    """Require a positive dollar ceiling; infinity is only an explicit internal option."""
    if isinstance(value, bool):
        raise ValueError("spending cap must be a positive finite number")
    cap = float(value)
    if cap <= 0 or math.isnan(cap) or (not allow_unbounded and not math.isfinite(cap)):
        raise ValueError("spending cap must be a positive finite number")
    return cap


class CostCapWouldBreach(Exception):
    """The projected cost of the next call would breach the cap (M3 §3.2)."""

    def __init__(self, projected_usd: float, cap_usd: float, spent_usd: float):
        self.projected_usd = projected_usd
        self.cap_usd = cap_usd
        self.spent_usd = spent_usd
        super().__init__(
            f"projected {projected_usd:.6f} would breach cap {cap_usd:.6f} "
            f"(already committed {spent_usd:.6f})"
        )


class TokenCapWouldBreach(CostCapWouldBreach):
    """The projected output tokens of the next call would breach the shared cap."""

    def __init__(self, projected_tokens: int, cap_tokens: int, spent_tokens: int):
        self.projected_tokens = projected_tokens
        self.cap_tokens = cap_tokens
        self.spent_tokens = spent_tokens
        # Keep this as a CostCapWouldBreach subtype so all existing cap fallback
        # paths handle both parity bases, but initialise the exception directly:
        # the parent constructor intentionally accepts USD-specific fields.
        Exception.__init__(self,
            f"projected {projected_tokens} output tokens would breach cap {cap_tokens} "
            f"(already committed {spent_tokens})"
        )


@dataclass(frozen=True)
class _Reservation:
    projected_usd: float
    projected_output_tokens: int


@dataclass
class CostLedger:
    pricing_table: PricingTable
    cap_usd: float = float("inf")
    spent_usd: float = 0.0
    cap_output_tokens: int | None = None
    spent_output_tokens: int = 0
    # Keep part of the shared output-token budget available for final submission.
    # Other calls use cap minus reserve; reserve-exempt calls can use the full cap.
    # This preserves resources but does not guarantee a successful submission.
    final_reserve_tokens: int = 0
    # Keep part of the dollar cap for the run's closing calls (informal workarounds handover notes, October 28,
    # 2026): other calls are admitted against cap minus this reserve, closing calls against the full cap.
    closing_reserve_usd: float = 0.0
    records: list[CostRecord] = field(default_factory=list)
    # Admission is a reservation, not a look-only check. Multiple agent coroutines share
    # this ledger and can await provider calls concurrently; counting only completed calls
    # lets every sibling pass against the same remaining cap. These mutations contain no
    # await, so they are atomic with respect to the host-owned asyncio agent loop.
    reserved_usd: float = 0.0
    reserved_output_tokens: int = 0
    _reservations: dict[str, _Reservation] = field(default_factory=dict, repr=False)
    unsettled_calls: dict[str, str] = field(default_factory=dict)
    # Possible cost of resent attempts whose usage is unknown (a timeout or server error the
    # adapter resent; October 19, 2026). Each is held at its call's projected cost and counts
    # against the cap at admission, so spending caps hold through an outage. It is not
    # spending: it never enters ``spent_usd``, the cost records, or the realized pressure that
    # produces participant-visible notices.
    uncertain_usd: float = 0.0

    def __post_init__(self) -> None:
        # Zero is useful for deterministic offline work; live entry points require
        # a positive finite cap through validate_spending_cap.
        if isinstance(self.cap_usd, bool) or math.isnan(self.cap_usd) or self.cap_usd < 0:
            raise ValueError("ledger cap must be nonnegative and not NaN")

    def apply(self, record: CostRecord, *, call_id: str | None = None) -> None:
        """Replace a call reservation with its reported usage and calculated cost."""
        if call_id is not None:
            reservation = self._reservations.pop(call_id, None)
            if reservation is None:
                raise RuntimeError(f"no active cost reservation for model call {call_id!r}")
            self.reserved_usd = sum(r.projected_usd for r in self._reservations.values())
            self.reserved_output_tokens = sum(
                r.projected_output_tokens for r in self._reservations.values())
            self.unsettled_calls.pop(call_id, None)
        self.records.append(record)
        self.spent_usd += record.cost_usd
        self.spent_output_tokens += int(record.token_split.output or 0)

    def release(self, call_id: str) -> bool:
        """Release a reservation only when no usage remains to be settled."""
        if call_id in self.unsettled_calls:
            raise RuntimeError("cannot release unresolved model usage")
        reservation = self._reservations.pop(call_id, None)
        if reservation is None:
            return False
        self.reserved_usd = sum(r.projected_usd for r in self._reservations.values())
        self.reserved_output_tokens = sum(
            r.projected_output_tokens for r in self._reservations.values())
        return True

    def hold_uncertain(self, usd: float) -> None:
        """Hold the possible cost of one resent attempt whose usage is unknown."""
        if math.isnan(usd) or usd < 0:
            raise ValueError("an uncertain hold must be nonnegative")
        self.uncertain_usd += usd

    def mark_unsettled(self, call_id: str, reason: str) -> None:
        """Keep dispatched liability reserved and stop new calls until it is settled."""
        if call_id in self._reservations:
            self.unsettled_calls[call_id] = reason

    def project_next_call_usd(self, req: ModelRequest, adapter) -> float:
        """Estimate call cost using estimated input and the maximum requested output.

        No cache discount is assumed. The estimate depends on the adapter's token
        heuristic and the configured prices; it is not a guaranteed billing ceiling."""
        input_tok = adapter.estimate_tokens(req.messages, req.tools)
        row = self.pricing_table.price(req.model_ref).for_prompt(input_tok)
        out_tok = req.sampling.max_output_tokens
        return (input_tok * row.input + out_tok * row.output) / 1e6

    def admit(self, req: ModelRequest, adapter, *, reserve_exempt: bool = False,
              closing_call: bool = False) -> float:
        """Atomically reserve the projected call or raise if it breaches the cap.

        ``reserve_exempt``: the calling agent's current submit binding is the contract's
        FINAL scored commitment — its calls draw on the full token cap; all other work
        (intake, deliberation, amendments, compaction) is admitted only against
        (cap - final_reserve_tokens). ``closing_call``: a call after the work period that may draw on
        ``closing_reserve_usd``; every other call is admitted against (cap_usd - closing_reserve_usd).
        The gateway must later call ``apply(..., call_id=)``
        or ``release(call_id)``. Returns the USD projection on success.
        """
        if self.unsettled_calls:
            raise RuntimeError("model usage is unresolved; refusing further dispatch")
        if req.call_id in self._reservations:
            raise RuntimeError(f"duplicate active model-call reservation: {req.call_id!r}")
        projected = self.project_next_call_usd(req, adapter)
        committed_usd = self.spent_usd + self.reserved_usd + self.uncertain_usd
        cap_usd = self.cap_usd if closing_call else self.cap_usd - float(self.closing_reserve_usd or 0.0)
        if committed_usd + projected > cap_usd:
            raise CostCapWouldBreach(projected, cap_usd, committed_usd)
        projected_tokens = int(req.sampling.max_output_tokens)
        if self.cap_output_tokens is not None:
            effective_cap = self.cap_output_tokens - (
                0 if reserve_exempt else int(self.final_reserve_tokens or 0))
            committed_tokens = self.spent_output_tokens + self.reserved_output_tokens
            if committed_tokens + projected_tokens > effective_cap:
                raise TokenCapWouldBreach(
                    projected_tokens, effective_cap, committed_tokens)
        self._reservations[req.call_id] = _Reservation(projected, projected_tokens)
        self.reserved_usd += projected
        self.reserved_output_tokens += projected_tokens
        return projected

    def pressure_fraction(self) -> float:
        """Realized pressure for the intervention ladder; reservations only gate dispatch.

        Using worst-case in-flight projections here would inject wrap-up interventions
        that disappear again when low-usage sibling calls settle — an apparatus change,
        not merely a concurrency-safe cap.
        """
        fractions = []
        if self.cap_usd != float("inf"):
            fractions.append(self.spent_usd / self.cap_usd)
        if self.cap_output_tokens:
            fractions.append(self.spent_output_tokens / self.cap_output_tokens)
        return max(fractions, default=0.0)
