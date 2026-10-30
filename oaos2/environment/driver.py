"""Deliver fixed, version-checked notices when their declared triggers occur.

The task manifest selects a JSON schedule and its content hash. Commitments or
logical-round arrivals trigger packets for the appropriate role scopes. Delivery
is recorded and linked to the recipient's next observation. Private keys and
researcher classifications are kept out of participant payloads. Notice content
is fixed in the schedule; agent actions do not generate new content here."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from oaos2.communication.mailbox import Mailbox, MailboxItem, MailboxPolicy
from oaos2.trace.records import EnvironmentEvent
from oaos2.ulid import new_ulid


class EnvironmentScheduleError(ValueError):
    """A schedule is malformed, tampered with, incomplete, or cannot be delivered."""


@dataclass(frozen=True)
class ScheduledPacket:
    wave_id: str
    trigger_commitment_id: str
    packet_id: str
    target_scopes: tuple[str, ...]
    payload: dict
    # Clocked-rounds stamps (decision (c), clock_design.md §2): researcher-side
    # instrument data. None = batched-only packet; batched runs ignore stamps.
    arrival_round: int | None = None
    response_deadline_round: int | None = None
    # A later notice on a case already scheduled (classification ``update``): the case
    # it bears on, researcher-side. The payload need not name the case.
    update_of: str | None = None


class EnvironmentDriver(Protocol):
    driver_ref: str

    def packets_after(self, commitment_id: str) -> list[ScheduledPacket]: ...
    def assert_complete(self) -> None: ...


_FORBIDDEN_PARTICIPANT_KEYS = frozenset({
    "answer", "answer_key", "oracle", "oracle_payload", "researcher_diagnostics",
})

# Researcher-side per-packet classification (platform_theory_audit.md §11.3): the
# ex ante rule-coverage map that makes the WP1 gate ("classify every event as
# rule-covered or a genuine exception without organizational outcomes") mechanical.
# It sits BESIDE ``payload`` in the schedule and is never delivered — dispatch
# sends only ``packet.payload`` — so, unlike the payload, it MAY name the oracle
# classification.
# ``update`` (LK1 context-shift diagnostic, design §3.5, 2026-10-02): a later notice that
# changes a fact on a case the schedule already carries. It opens no case of its own:
# ``update_of`` names the case researcher-side, ``arrival_round`` is when the news
# arrives, and ``response_deadline_round`` is the fuse of that case's review commitment.
_RULE_COVERAGE_VALUES = ("rule_covered", "exception", "update")
# ``facts``: materials-v9 integration-width registration — the per-packet fact
# inventory ({fact_id, anchor}) whose anchors the instrument tests hold verbatim
# to the payload text. Researcher-side like the rest of the classification.
# ``arrival_round``/``response_deadline_round``: clocked-rounds stamps
# (decision (c)) — dispatch timing and the case fuse, in rounds.
_CLASSIFICATION_KEYS = frozenset(
    {"rule_coverage", "rule_ref", "refs", "expected_scopes", "shell", "facts",
     "arrival_round", "response_deadline_round", "update_of"})


def _validate_classification(packet_id: str, classification) -> dict:
    if not isinstance(classification, dict):
        raise EnvironmentScheduleError(f"packet {packet_id!r} classification must be an object")
    unknown = set(classification) - _CLASSIFICATION_KEYS
    if unknown:
        raise EnvironmentScheduleError(
            f"packet {packet_id!r} classification has unknown keys: {sorted(unknown)}")
    coverage = classification.get("rule_coverage")
    if coverage not in _RULE_COVERAGE_VALUES:
        raise EnvironmentScheduleError(
            f"packet {packet_id!r} classification.rule_coverage must be one of "
            f"{list(_RULE_COVERAGE_VALUES)}")
    rule_ref = classification.get("rule_ref")
    if coverage == "rule_covered":
        # A covered event must name its covering rule, or the coverage map is vacuous.
        if not isinstance(rule_ref, str) or not rule_ref.strip():
            raise EnvironmentScheduleError(
                f"packet {packet_id!r} is rule_covered but names no rule_ref")
    elif rule_ref is not None:
        raise EnvironmentScheduleError(
            f"packet {packet_id!r} is an exception but names rule_ref {rule_ref!r}")
    update_of = classification.get("update_of")
    if (coverage == "update") != (update_of is not None) or (
            update_of is not None and not (isinstance(update_of, str) and update_of.strip())):
        raise EnvironmentScheduleError(
            f"packet {packet_id!r}: an update packet, and only an update packet, names the case "
            "it bears on in classification.update_of")
    for key in ("refs", "expected_scopes"):
        values = classification.get(key)
        if values is None:
            continue
        if (not isinstance(values, list) or not values
                or not all(isinstance(v, str) and v.strip() for v in values)
                or len(values) != len(set(values))):
            raise EnvironmentScheduleError(
                f"packet {packet_id!r} classification.{key} must be a nonempty list of "
                "unique nonempty strings")
    # The matched-shell taxonomy (INSTRUMENT_DESIGN.md §5): the researcher-side
    # identity of the event this packet realizes, letting a checker prove the two
    # condition schedules realize the same event multiset per wave. A SUB-SHELL
    # (materials v13: one tier realizes a shell as two locally-coverable
    # events) additionally names its parent via ``parent_shell_id``; the
    # matched-shell verifier sums sub-shells to the parent, and the stamp
    # script stamps them from the parent's slot.
    shell = classification.get("shell")
    if shell is not None:
        if (not isinstance(shell, dict)
                or set(shell) - {"parent_shell_id"} != {"shell_id", "type", "magnitude"}
                or not str(shell.get("shell_id", "")).strip()
                or not str(shell.get("type", "")).strip()
                or isinstance(shell.get("magnitude"), bool)
                or not isinstance(shell.get("magnitude"), (int, float))
                or ("parent_shell_id" in shell
                    and not str(shell.get("parent_shell_id", "")).strip())):
            raise EnvironmentScheduleError(
                f"packet {packet_id!r} classification.shell must be "
                "{shell_id, type, magnitude(number)[, parent_shell_id]}")
    for key in ("arrival_round", "response_deadline_round"):
        value = classification.get(key)
        if value is not None and (isinstance(value, bool)
                                  or not isinstance(value, int) or value < 1):
            raise EnvironmentScheduleError(
                f"packet {packet_id!r} classification.{key} must be a round "
                "number >= 1")
    arrival = classification.get("arrival_round")
    deadline = classification.get("response_deadline_round")
    if deadline is not None and arrival is not None and deadline < arrival:
        raise EnvironmentScheduleError(
            f"packet {packet_id!r} response_deadline_round precedes arrival_round")
    return dict(classification)


def _contains_forbidden_key(value) -> bool:
    if isinstance(value, dict):
        if {str(k).casefold() for k in value} & _FORBIDDEN_PARTICIPANT_KEYS:
            return True
        return any(_contains_forbidden_key(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_forbidden_key(v) for v in value)
    return False


class DeterministicScheduleDriver:
    """One-shot commitment-triggered packets loaded from a pinned JSON schedule."""

    driver_ref = "deterministic_schedule.v1"

    def __init__(self, *, schedule_ref: str, content_hash: str):
        self.schedule_path = str(schedule_ref)
        # Archive-facing ref is deliberately tier-neutral.  The manifest and digest
        # identify the schedule for researchers; participant records must not leak a
        # filename such as ``schedule_high``.
        self.schedule_ref = "manifest.environment.schedule"
        self.schedule_hash = content_hash
        raw = Path(self.schedule_path).read_bytes()
        actual = "sha256:" + hashlib.sha256(raw).hexdigest()
        if actual != content_hash:
            raise EnvironmentScheduleError(
                f"environment schedule hash mismatch: expected {content_hash}, got {actual}"
            )
        try:
            data = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise EnvironmentScheduleError(f"invalid environment schedule JSON: {exc}") from exc
        self._packets, self._classifications = self._validate(data)
        self._dispatched_waves: set[str] = set()
        self._dispatched_packets: set[str] = set()
        self.delivered_event_ids: list[str] = []

    @property
    def classifications(self) -> dict[str, dict]:
        """Researcher-side {packet_id: classification} — host analysis only, never delivered."""
        return dict(self._classifications)

    def coverage_summary(self) -> dict[str, int]:
        """Ex ante coverage counts for the manipulation check (WP1 gate)."""
        counts = {"rule_covered": 0, "exception": 0, "unclassified": 0}
        for packet in self._packets:
            classification = self._classifications.get(packet.packet_id)
            key = classification["rule_coverage"] if classification else "unclassified"
            counts[key] = counts.get(key, 0) + 1  # ``update`` appears only where a schedule has one
        return counts

    @staticmethod
    def _validate(data: dict) -> tuple[tuple[ScheduledPacket, ...], dict[str, dict]]:
        if data.get("schema_version") != 1:
            raise EnvironmentScheduleError("environment schedule schema_version must be 1")
        waves = data.get("waves")
        if not isinstance(waves, list) or not waves:
            raise EnvironmentScheduleError("environment schedule must declare non-empty waves")
        wave_ids: set[str] = set()
        packet_ids: set[str] = set()
        packets: list[ScheduledPacket] = []
        classifications: dict[str, dict] = {}
        for wave in waves:
            wave_id = str(wave.get("wave_id", "")).strip()
            trigger = str(wave.get("trigger_commitment_id", "")).strip()
            if not wave_id or not trigger or wave_id in wave_ids:
                raise EnvironmentScheduleError(f"invalid or duplicate wave {wave_id!r}")
            wave_ids.add(wave_id)
            declared_packets = wave.get("packets")
            if not isinstance(declared_packets, list) or not declared_packets:
                raise EnvironmentScheduleError(f"wave {wave_id!r} has no packets")
            for packet in declared_packets:
                packet_id = str(packet.get("packet_id", "")).strip()
                scopes = packet.get("target_scopes")
                payload = packet.get("payload")
                if not packet_id or packet_id in packet_ids:
                    raise EnvironmentScheduleError(f"invalid or duplicate packet {packet_id!r}")
                if not isinstance(scopes, list) or not scopes or not all(
                    isinstance(s, str) and s for s in scopes
                ):
                    raise EnvironmentScheduleError(f"packet {packet_id!r} has invalid target_scopes")
                if not isinstance(payload, dict) or _contains_forbidden_key(payload):
                    raise EnvironmentScheduleError(
                        f"packet {packet_id!r} has invalid or oracle-bearing participant payload"
                    )
                packet_ids.add(packet_id)
                if "classification" in packet:
                    classifications[packet_id] = _validate_classification(
                        packet_id, packet["classification"])
                stamps = classifications.get(packet_id) or {}
                packets.append(ScheduledPacket(
                    wave_id=wave_id, trigger_commitment_id=trigger, packet_id=packet_id,
                    target_scopes=tuple(scopes), payload=payload,
                    arrival_round=stamps.get("arrival_round"),
                    response_deadline_round=stamps.get("response_deadline_round"),
                    update_of=stamps.get("update_of"),
                ))
        # an update bears on an exception case of this schedule, arrives after it, and its
        # payload does not open a case of its own
        exception_arrival: dict[str, int] = {}
        for p in packets:
            if (classifications.get(p.packet_id) or {}).get("rule_coverage") == "exception":
                case = str((p.payload or {}).get("case_id") or "")
                if case and p.arrival_round is not None:
                    exception_arrival[case] = min(exception_arrival.get(case, p.arrival_round), p.arrival_round)
        updated: set[str] = set()
        for p in packets:
            if p.update_of is None:
                continue
            if p.update_of in updated:
                raise EnvironmentScheduleError(f"case {p.update_of!r} has more than one update packet")
            updated.add(p.update_of)
            if "case_id" in (p.payload or {}):
                raise EnvironmentScheduleError(
                    f"update packet {p.packet_id!r} must not carry a case_id: it opens no case")
            base = exception_arrival.get(p.update_of)
            if base is None or p.arrival_round is None or p.arrival_round <= base:
                raise EnvironmentScheduleError(
                    f"update packet {p.packet_id!r} must arrive after the exception case "
                    f"{p.update_of!r} it bears on")
        # ``refs`` are the participant-vocabulary join keys the archive projection
        # matches exception trigger_refs against — ambiguity would corrupt the join.
        ref_owners: dict[str, str] = {}
        for pid in sorted(classifications):
            for ref in classifications[pid].get("refs") or []:
                if ref in ref_owners:
                    raise EnvironmentScheduleError(
                        f"classification ref {ref!r} claimed by packets "
                        f"{ref_owners[ref]!r} and {pid!r}")
                ref_owners[ref] = pid
        return tuple(packets), classifications

    def packets_after(self, commitment_id: str) -> list[ScheduledPacket]:
        matching = [p for p in self._packets if p.trigger_commitment_id == commitment_id]
        wave_ids = {p.wave_id for p in matching}
        duplicate = wave_ids & self._dispatched_waves
        if duplicate:
            raise EnvironmentScheduleError(
                f"environment wave dispatched more than once: {sorted(duplicate)}"
            )
        duplicate_packets = {p.packet_id for p in matching} & self._dispatched_packets
        if duplicate_packets:
            raise EnvironmentScheduleError(
                f"environment packet dispatched more than once: {sorted(duplicate_packets)}"
            )
        self._dispatched_waves.update(wave_ids)
        self._dispatched_packets.update(p.packet_id for p in matching)
        return matching

    def packets_at_round(self, round_no: int) -> list[ScheduledPacket]:
        """Clocked-rounds dispatch (decision (c)): packets stamped for this round.

        Per-packet once-only, mode-exclusive with ``packets_after`` for any given
        packet — the runner picks ONE dispatch mode per run; a packet reaching
        both paths is a wiring error and fails closed.
        """
        matching = [p for p in self._packets if p.arrival_round == round_no]
        duplicate = {p.packet_id for p in matching} & self._dispatched_packets
        if duplicate:
            raise EnvironmentScheduleError(
                f"environment packet dispatched more than once: {sorted(duplicate)}"
            )
        self._dispatched_packets.update(p.packet_id for p in matching)
        return matching

    def case_rounds(self) -> dict[str, dict]:
        """Researcher-side case timing from the stamps: case_id -> {arrival,
        deadline} in rounds (arrival = earliest packet, deadline = latest stamp;
        None deadline = no fuse). Cases with unstamped packets are omitted —
        the clocked runner treats an omission on an exception case as a wiring
        error and refuses the run."""
        out: dict[str, dict] = {}
        for p in self._packets:
            case = (p.payload or {}).get("case_id")
            if not case or p.arrival_round is None:
                continue
            row = out.setdefault(case, {"arrival": p.arrival_round,
                                        "deadline": p.response_deadline_round})
            row["arrival"] = min(row["arrival"], p.arrival_round)
            if p.response_deadline_round is not None:
                row["deadline"] = (p.response_deadline_round
                                   if row["deadline"] is None
                                   else max(row["deadline"],
                                            p.response_deadline_round))
        return out

    def update_rounds(self) -> dict[str, dict]:
        """Researcher-side timing of the later notices: case id -> {arrival, deadline,
        packet_id, target_scopes}. ``deadline`` is the fuse of the case's review
        commitment (None = no review is timed)."""
        return {p.update_of: {"arrival": p.arrival_round, "deadline": p.response_deadline_round,
                              "packet_id": p.packet_id, "target_scopes": list(p.target_scopes)}
                for p in self._packets if p.update_of is not None}

    def fully_dispatched(self) -> bool:
        """True once every packet has gone out (clocked closure gate: the run
        must not be closable while scheduled arrivals remain — a trailing
        rule-covered packet has no case slot to hold the door open)."""
        return {p.packet_id for p in self._packets} <= self._dispatched_packets

    def pending_for_scope(self, scope: str, through_round: int) -> bool:
        """True while any stamped packet targeting ``scope`` with
        ``arrival_round <= through_round`` is still undispatched. The clocked
        runner's period-record admission gate (2026-08-30 low-tier probe
        forensic): an office's period report is not composable before that
        office's period mail has arrived — idle lanes otherwise race the slot
        and truthfully certify an empty period at round 2, which per-period
        crediting can never repair. Same scope semantics as delivery
        (``_scope_receives``), so the gate holds exactly for mail the role
        would receive."""
        for p in self._packets:
            if p.arrival_round is None or p.arrival_round > through_round:
                continue
            if p.packet_id in self._dispatched_packets:
                continue
            if _scope_receives(scope, p.target_scopes):
                return True
        return False

    def assert_complete(self) -> None:
        # A wave is complete when dispatched wholesale (commitment mode) or when
        # every one of its packets went out round-by-round (clocked mode).
        by_wave: dict[str, set[str]] = {}
        for p in self._packets:
            by_wave.setdefault(p.wave_id, set()).add(p.packet_id)
        missing = [wave for wave, ids in sorted(by_wave.items())
                   if wave not in self._dispatched_waves
                   and not ids <= self._dispatched_packets]
        if missing:
            raise EnvironmentScheduleError(
                f"environment schedule incomplete; undispatched waves: {missing}"
            )


DRIVER_BUILDERS = {
    "deterministic_schedule": DeterministicScheduleDriver,
}


def build_environment_driver(config: dict | None, tier: str | None,
                             variant: str | None = None) -> EnvironmentDriver | None:
    """Build the manifest-selected driver for one cell, or ``None`` for static packs.

    ``variant`` selects a stamped-schedule variant (a separate hash-pinned
    asset, resolved by the loader) — per-cell horizon sweeps pass it; the
    canonical schedule is the ``None`` default and is never mutated.
    """
    if not config:
        return None
    driver_id = config.get("driver")
    if variant is None:
        schedule = config.get("schedules", {}).get(tier)
    else:
        schedule = config.get("schedule_variants", {}).get(variant, {}).get(tier)
        if not schedule:
            raise EnvironmentScheduleError(
                f"no stamped schedule variant {variant!r} for tier {tier!r} "
                f"(declare it under environment.schedule_variants)")
    if driver_id not in DRIVER_BUILDERS:
        raise EnvironmentScheduleError(f"unknown environment driver {driver_id!r}")
    if not schedule:
        raise EnvironmentScheduleError(f"no environment schedule for tier {tier!r}")
    return DRIVER_BUILDERS[driver_id](
        schedule_ref=schedule["ref"], content_hash=schedule["content_hash"]
    )


def _scope_receives(agent_scope, target_scopes: tuple[str, ...]) -> bool:
    """``agent_scope`` is one attention scope or a tuple of scopes (a role with
    extra ``packet_scopes``, CH1): the role receives a packet targeting any of them."""
    scopes = (agent_scope,) if isinstance(agent_scope, str) else tuple(agent_scope)
    return ("all" in scopes or "all" in target_scopes
            or any(s in target_scopes for s in scopes))


async def dispatch_after_commit(
    driver: EnvironmentDriver,
    *,
    commitment_id: str,
    runtime_state,
    caused_by: str,
) -> list[str]:
    """Emit and deliver every packet triggered by ``commitment_id``.

    Each recipient gets a separate event so its next AgentView can cite that
    exact packet as a causal parent.  A packet with no recipient fails closed.
    """
    return await _deliver_packets(
        driver, driver.packets_after(commitment_id),
        runtime_state=runtime_state, caused_by=caused_by)


async def dispatch_at_round(
    driver,
    *,
    round_no: int,
    runtime_state,
    caused_by: str,
) -> list[str]:
    """Clocked-rounds arrival dispatch (decision (c)): deliver every packet
    stamped ``arrival_round == round_no``. Same delivery semantics as
    commitment-triggered dispatch — separate event per recipient, fail closed
    on an unroutable packet."""
    return await _deliver_packets(
        driver, driver.packets_at_round(round_no),
        runtime_state=runtime_state, caused_by=caused_by)


async def _deliver_packets(driver, packets, *, runtime_state, caused_by) -> list[str]:
    event_ids: list[str] = []
    for packet in packets:
        recipients = [
            agent_id for agent_id, agent in runtime_state.agents.items()
            if _scope_receives(
                runtime_state.environment_scopes.get(agent_id, agent.role_id),
                packet.target_scopes,
            )
        ]
        if not recipients:
            raise EnvironmentScheduleError(
                f"packet {packet.packet_id!r} has no recipient for scopes "
                f"{list(packet.target_scopes)!r}"
            )
        for agent_id in recipients:
            target_role = runtime_state.agents[agent_id].role_id
            record = EnvironmentEvent(
                environment_event_id=new_ulid(), driver_ref=driver.driver_ref,
                schedule_ref=driver.schedule_ref, schedule_hash=driver.schedule_hash,
                wave_id=packet.wave_id, packet_id=packet.packet_id,
                trigger_commitment_id=packet.trigger_commitment_id,
                target_role_id=target_role, payload=packet.payload,
            )
            event_id = await runtime_state.spine.emit_event(
                "environment.event", agent_id=agent_id, role_id=target_role,
                caused_by=caused_by, phase_name="environment", audience="agent",
                channel="formal", payload={"environment_event": record.model_dump()},
            )
            mailbox = runtime_state.mailbox.setdefault(agent_id, Mailbox(MailboxPolicy()))
            overflow = mailbox.enqueue(MailboxItem(
                item_id=record.environment_event_id, kind="environment_event",
                payload=packet.payload, source_event_id=event_id,
            ))
            if overflow:
                raise EnvironmentScheduleError(
                    f"environment delivery overflow for {agent_id!r}: {overflow}"
                )
            sink = getattr(runtime_state, "environment_delivery_sink", None)
            if sink is not None:
                # Fail closed: a missing correspondence file would be a silent
                # apparatus difference between cells.
                sink(agent_id=agent_id, packet=packet)
            driver.delivered_event_ids.append(event_id)
            event_ids.append(event_id)
    if event_ids:
        runtime_state.kick_scheduler()
    return event_ids
