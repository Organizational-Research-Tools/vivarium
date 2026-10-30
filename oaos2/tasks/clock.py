"""Load and validate experiment-defined time settings.

ClockSpec checks horizons, schedule coverage, plan deadlines, daily call settings,
and the binding from commitment timing metadata to cases and due rounds. The
runner consumes this object; CapacityPolicy enforces the call counts. Per-cell
overrides select declared schedule variants without changing canonical assets.
See kernel/clock.py for round advancement and docs/SYSTEM.md for execution flow."""

from __future__ import annotations

from dataclasses import dataclass, field


class InvalidClockSpec(ValueError):
    """A malformed ``clock:`` manifest block or an inconsistent contract/schedule
    binding — always raised at load/preflight, never mid-run."""


_ALLOWED_KEYS = {"rounds_total", "plan_deadline_rounds", "profiles",
                 "calls_per_day", "schedule_tier", "profile_tiers",
                 "schedule_variant", "megabatch"}
# Keys a per-cell experiment override may change (repair item 4): the load lever
# and its derived deadlines, the stamped-schedule variant it pairs with, and the
# apparatus knobs. Profiles and tier are pack identity — never swept.
_OVERRIDE_KEYS = {"rounds_total", "plan_deadline_rounds", "schedule_variant",
                  "calls_per_day", "megabatch"}
# timing.role values a commitment may declare (open to extension via this
# module only — the registry of temporal meanings IS the ClockSpec's to own).
# Strictly temporal: stage routing (report/amendment/comment slots) is a
# SEPARATE `Commitment.routing` field validated by the loader — batched
# profiles never call bind(), so routing smuggled through timing would be an
# unvalidated registry (audit round 6 P2-3).
# ``review`` (LK1 context-shift diagnostic, 2026-10-02): the second disposition of a case
# on which a later notice arrived; due at that notice's stamped deadline.
_TIMING_ROLES = {"filing", "disposition", "plan", "review"}


@dataclass(frozen=True)
class ClockBindings:
    """Contract ↔ schedule binding, derived (validated) once per run.

    All four maps were previously reconstructed in the runner by parsing
    commitment-name prefixes; they now derive from ``Commitment.timing``.
    """
    disposition_id: dict   # case id → disposition commitment id
    case_filings: dict     # case id → [filing commitment ids]
    slot_case: dict        # commitment id → case id (filings + dispositions)
    slot_due: dict         # commitment id → due round (fuse or plan deadline)
    # Commitments timed {due_with: <plan>} — period records (rule logs, office
    # plans). The runner's admission gate holds these until the committing
    # role's scheduled arrivals through the due round are dispatched (low-tier
    # probe forensic 2026-08-30: idle offices filed period reports at round 2,
    # before their mail existed, and per-period crediting could never credit
    # the late arrivals).
    due_with_ids: frozenset = frozenset()
    # case id → review commitment id, and case id → the round its later notice arrives:
    # a review slot is not actionable before the news exists
    review_id: dict = field(default_factory=dict)
    review_arrival: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ClockSpec:
    rounds_total: int
    plan_deadline_rounds: dict = field(default_factory=dict)  # plan cid → round
    profiles: tuple = ()   # contract profiles built for round-dispatched schedules
    calls_per_day: int = 8  # hard per-role per-day provider-call ceiling (§1a)
    schedule_tier: str | None = None  # legacy single tier (all profiles), if uniform
    # Per-profile tier binding (estimand correction 2026-08-27): each clocked
    # profile's per-case slots are derived from ONE tier's schedule, so a pack
    # may carry both tiers' profiles side by side. Keys ⊆ profiles; a profile
    # absent here falls back to ``schedule_tier``.
    profile_tiers: dict = field(default_factory=dict)
    # Which stamped-schedule variant this spec pairs with (None = the canonical
    # schedule). Variants are separate hash-pinned hidden assets — per-cell
    # horizon sweeps select one; canonical files are never mutated.
    schedule_variant: str | None = None
    # Apparatus knob (§1a): True = the engine may continue a role in-turn onto
    # its next actionable duty; False pins the one-commit-per-turn mechanical
    # floor (manipulation-check baselines). Recorded in the manifest clock block.
    megabatch: bool = True

    # ---------------------------------------------------------------- load --
    @classmethod
    def from_manifest(cls, block: dict | None) -> "ClockSpec | None":
        """Validate a manifest ``clock:`` block into a spec (None = batched pack).

        Fail-closed at load: unknown keys, wrong types, or out-of-range values
        refuse the pack rather than surfacing as a mid-run crash.
        """
        if not block:
            return None
        if not isinstance(block, dict):
            raise InvalidClockSpec(f"clock: must be a mapping, got {type(block).__name__}")
        unknown = set(block) - _ALLOWED_KEYS
        if unknown:
            raise InvalidClockSpec(f"clock: unknown keys {sorted(unknown)}")
        try:
            rounds_total = int(block["rounds_total"])
        except (KeyError, TypeError, ValueError):
            raise InvalidClockSpec("clock.rounds_total: required positive integer")
        if rounds_total < 1:
            raise InvalidClockSpec(f"clock.rounds_total must be >= 1, got {rounds_total}")
        deadlines_raw = block.get("plan_deadline_rounds") or {}
        if not isinstance(deadlines_raw, dict):
            raise InvalidClockSpec("clock.plan_deadline_rounds: must be a mapping")
        deadlines: dict[str, int] = {}
        for pid, rnd in deadlines_raw.items():
            try:
                rnd = int(rnd)
            except (TypeError, ValueError):
                raise InvalidClockSpec(f"clock.plan_deadline_rounds[{pid!r}]: not an integer")
            if not 1 <= rnd <= rounds_total:
                raise InvalidClockSpec(
                    f"clock.plan_deadline_rounds[{pid!r}]={rnd} outside [1, {rounds_total}]")
            deadlines[str(pid)] = rnd
        deadlines = dict(sorted(deadlines.items(), key=lambda kv: kv[1]))
        profiles = tuple(block.get("profiles") or ())
        if not profiles:
            raise InvalidClockSpec("clock.profiles: at least one clocked contract profile required")
        try:
            calls_per_day = int(block.get("calls_per_day", 8))
        except (TypeError, ValueError):
            raise InvalidClockSpec("clock.calls_per_day: not an integer")
        if calls_per_day < 1:
            raise InvalidClockSpec(f"clock.calls_per_day must be >= 1, got {calls_per_day}")
        tier = block.get("schedule_tier")
        profile_tiers_raw = block.get("profile_tiers") or {}
        if not isinstance(profile_tiers_raw, dict):
            raise InvalidClockSpec("clock.profile_tiers: must be a mapping")
        unknown_profiles = set(profile_tiers_raw) - set(profiles)
        if unknown_profiles:
            raise InvalidClockSpec(
                f"clock.profile_tiers names unknown profiles: {sorted(unknown_profiles)}")
        profile_tiers = {str(p): str(t) for p, t in profile_tiers_raw.items()}
        variant = block.get("schedule_variant")
        megabatch = block.get("megabatch", True)
        if not isinstance(megabatch, bool):
            raise InvalidClockSpec("clock.megabatch: must be a boolean")
        return cls(rounds_total=rounds_total, plan_deadline_rounds=deadlines,
                   profiles=profiles, calls_per_day=calls_per_day,
                   schedule_tier=(str(tier) if tier is not None else None),
                   profile_tiers=profile_tiers,
                   schedule_variant=(str(variant) if variant is not None else None),
                   megabatch=megabatch)

    def to_manifest(self) -> dict:
        """Round-trip form for run provenance (manifest extensions/clock block)."""
        return {"rounds_total": self.rounds_total,
                "plan_deadline_rounds": dict(self.plan_deadline_rounds),
                "profiles": list(self.profiles),
                "calls_per_day": self.calls_per_day,
                "schedule_tier": self.schedule_tier,
                "profile_tiers": dict(self.profile_tiers),
                "schedule_variant": self.schedule_variant,
                "megabatch": self.megabatch}

    def override(self, overrides: dict) -> "ClockSpec":
        """A new spec with per-cell experiment overrides applied (repair item 4).

        Merges onto the manifest form and re-runs the full ``from_manifest``
        validation, so an override can never smuggle in an invariant violation
        the manifest itself would have refused. Immutable: self is untouched.
        """
        unknown = set(overrides) - _OVERRIDE_KEYS
        if unknown:
            raise InvalidClockSpec(
                f"clock override: keys {sorted(unknown)} are not sweepable "
                f"(allowed: {sorted(_OVERRIDE_KEYS)})")
        return ClockSpec.from_manifest({**self.to_manifest(), **overrides})

    # ----------------------------------------------------------- preflight --
    def is_clocked_profile(self, profile: str | None) -> bool:
        return profile in self.profiles

    def validate_tier(self, tier: str, profile: str | None = None) -> None:
        """Refuse a profile ↔ tier mismatch (per-case slots are tier-derived).

        A profile listed in ``profile_tiers`` is checked against its own tier;
        otherwise the legacy pack-wide ``schedule_tier`` applies.
        """
        bound = self.profile_tiers.get(profile) if profile is not None else None
        if bound is not None:
            if bound != tier:
                raise InvalidClockSpec(
                    f"clocked profile {profile!r} is built for tier {bound!r}; got {tier!r}")
            return
        if self.schedule_tier not in (None, tier):
            raise InvalidClockSpec(
                f"clocked profiles are built for tier {self.schedule_tier!r}; got {tier!r}")

    def validate_schedule(self, driver) -> None:
        """Horizon + coverage preflight (audit rounds 3 P2-6, 4 P2-7).

        Every packet classified and stamped inside [1, rounds_total]; every
        EXCEPTION packet carries a fuse — an unstamped packet would strand
        ``fully_dispatched()``; a fuse-less exception silently loses its
        deadline discipline. Runs before any run resource is staged.
        """
        if driver.coverage_summary()["unclassified"] > 0:
            raise InvalidClockSpec("clocked schedule has unclassified packets")
        bad = []
        for pid, cls_ in sorted(driver.classifications.items()):
            arrival = cls_.get("arrival_round")
            deadline = cls_.get("response_deadline_round")
            if (arrival is None or not 1 <= int(arrival) <= self.rounds_total
                    or (deadline is not None
                        and not 1 <= int(deadline) <= self.rounds_total)
                    or (cls_.get("rule_coverage") == "exception" and deadline is None)):
                bad.append(pid)
        if bad:
            raise InvalidClockSpec(
                f"clocked schedule fails horizon preflight (arrival/fuse in "
                f"[1, {self.rounds_total}]; exceptions must carry a fuse): {bad[:8]}")

    # ---------------------------------------------------------------- bind --
    def bind(self, contract, case_rounds: dict, update_rounds: dict | None = None) -> ClockBindings:
        """Bind contract commitments to schedule cases via declared ``timing``.

        Timing metadata schema (per commitment, in the contract profile YAML):
          ``{role: filing|disposition, case: <case id>}`` — due at the case fuse;
          ``{role: plan}`` — due at ``plan_deadline_rounds[commitment_id]``;
          ``{due_with: <plan cid>}`` — due at that plan's deadline (rule logs,
          office plans); ``{due_round: N}`` — a period record due at round N
          (CH2 workload design: the quarter report, due after the wave's last
          arrival and before its fuses), admitted like a due_with record.
          ``{role: review, case: <case id>}`` — the review disposition of a case
          with a later notice, due at that notice's stamped deadline
          (``update_rounds``, from the schedule's update packets).
          No timing = untimed (allowed; e.g. ancillary slots).
        """
        update_rounds = dict(update_rounds or {})
        review_id: dict[str, str] = {}
        contract_ids = [c.commitment_id for c in contract.commitments]
        unknown = set(self.plan_deadline_rounds) - set(contract_ids)
        if unknown:
            raise InvalidClockSpec(
                f"clock.plan_deadline_rounds names unknown commitments: {sorted(unknown)}")
        disposition_id: dict[str, str] = {}
        case_filings: dict[str, list] = {}
        slot_due: dict[str, int] = {}
        due_with_ids: set[str] = set()
        bad_cases, bad_roles, bad_due = [], [], []
        for c in contract.commitments:
            t = getattr(c, "timing", None) or {}
            role = t.get("role")
            if role is not None and role not in _TIMING_ROLES:
                bad_roles.append(c.commitment_id)
                continue
            if role == "review":
                case = t.get("case")
                if case not in update_rounds or case not in case_rounds:
                    bad_cases.append(c.commitment_id)
                    continue
                if case in review_id:
                    raise InvalidClockSpec(
                        f"case {case!r} has two review commitments: {review_id[case]!r}, {c.commitment_id!r}")
                review_id[case] = c.commitment_id
            elif role in ("filing", "disposition"):
                case = t.get("case")
                if case not in case_rounds:
                    bad_cases.append(c.commitment_id)
                    continue
                if role == "disposition":
                    if case in disposition_id:
                        raise InvalidClockSpec(
                            f"case {case!r} has two disposition commitments: "
                            f"{disposition_id[case]!r}, {c.commitment_id!r}")
                    disposition_id[case] = c.commitment_id
                else:
                    case_filings.setdefault(case, []).append(c.commitment_id)
            elif role == "plan":
                if c.commitment_id not in self.plan_deadline_rounds:
                    bad_due.append(c.commitment_id)
                    continue
                slot_due[c.commitment_id] = self.plan_deadline_rounds[c.commitment_id]
            if "due_with" in t:
                anchor = t["due_with"]
                if anchor not in self.plan_deadline_rounds:
                    bad_due.append(c.commitment_id)
                    continue
                slot_due[c.commitment_id] = self.plan_deadline_rounds[anchor]
                due_with_ids.add(c.commitment_id)
            elif "due_round" in t:
                due = int(t["due_round"])
                if not 1 <= due <= self.rounds_total:
                    raise InvalidClockSpec(
                        f"commitment {c.commitment_id!r} is due at round {due}, outside "
                        f"[1, {self.rounds_total}]")
                slot_due[c.commitment_id] = due
                due_with_ids.add(c.commitment_id)
        if bad_roles:
            raise InvalidClockSpec(
                f"commitments declare unknown timing.role: {sorted(bad_roles)}")
        if bad_cases:
            raise InvalidClockSpec(
                f"commitments name cases absent from the stamped schedule: "
                f"{sorted(bad_cases)}")
        if bad_due:
            raise InvalidClockSpec(
                f"commitments time against plans absent from "
                f"plan_deadline_rounds: {sorted(bad_due)}")
        # Fused cases (a stamped deadline) must each own exactly one disposition
        # slot — a fused case without one would lapse invisibly.
        missing = sorted(case for case, rounds in case_rounds.items()
                         if rounds.get("deadline") is not None
                         and case not in disposition_id)
        if missing:
            raise InvalidClockSpec(
                f"clocked contract/schedule mismatch: fused cases without "
                f"disposition slots {missing}")
        case_filings = {case: cids for case, cids in case_filings.items()
                        if case in disposition_id}
        slot_case = {cid: case for case, cids in case_filings.items() for cid in cids}
        slot_case.update({did: case for case, did in disposition_id.items()})
        for case, did in disposition_id.items():
            fuse = case_rounds[case].get("deadline")
            if fuse is not None:
                slot_due[did] = fuse
                for fid in case_filings.get(case, []):
                    slot_due[fid] = fuse
        # A stamped update owns exactly one review slot, and a review needs its
        # case's first disposition: the later notice revises something decided.
        unreviewed = sorted(case for case, u in update_rounds.items()
                            if u.get("deadline") is not None and case not in review_id)
        if unreviewed:
            raise InvalidClockSpec(
                f"clocked contract/schedule mismatch: updated cases without review slots {unreviewed}")
        for case, rid in review_id.items():
            if case not in disposition_id:
                raise InvalidClockSpec(f"review {rid!r} names case {case!r}, which has no disposition slot")
            slot_case[rid] = case
            deadline = update_rounds[case].get("deadline")
            if deadline is not None:
                slot_due[rid] = int(deadline)
        return ClockBindings(disposition_id=disposition_id, case_filings=case_filings,
                             slot_case=slot_case, slot_due=slot_due,
                             due_with_ids=frozenset(due_with_ids), review_id=review_id,
                             review_arrival={case: int(update_rounds[case]["arrival"]) for case in review_id})
