"""Define the coordination interface and registry used by the runner.

A CoordinationProtocol binds roles to commitments, controls readiness, routes
accepted contributions, and supplies any work alongside the agent loops. Resolve
one procedure per run from live_coordination.mode and protocol_module. An unknown
mode fails resolution. New task-specific procedures belong in plugins; shared
engine changes require the research need documented in AGENTS.md."""

from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


def make_inbound_handler():
    """Accumulate handoffs and stage duties until the role is admission-ready.

    Mailboxes drain on observation even when a contract blocker still withholds the
    model call.  Persisting the platform's next-slot notice beside handoffs prevents a
    duty assigned early in a wave from disappearing before its environment packet lands.
    """
    def handler(observations, st):
        # query / reply / assent / update: the budget exchange's agent-initiated case
        # messages (2026-09-25; update 2026-10-02); rendered like handoffs so they reach
        # the recipient's next turn.
        texts = [str(o.get("payload")) for o in observations
                 if o.get("kind") in {"handoff", "stage_assignment", "query", "reply", "assent", "update"}]
        if texts:
            st["inbox_text"] = "\n".join(filter(None, [st.get("inbox_text", ""), *texts])).strip()
        # Clock notices SUPERSEDE rather than accumulate (audit round 3 P2-9):
        # every delivery stays in the trace, but the model sees only the
        # latest day snapshot, rendered once per acted turn by model_agent.
        # They never enter inbox_text — its delta consumption is offset-based,
        # and mutating history there swallows queued duty announcements.
        clock_lines = [str(o.get("payload")) for o in observations
                       if o.get("kind") == "clock_notice"]
        if clock_lines:
            st["clock_snapshot"] = clock_lines[-1]
    return handler


def role_commitment_seq(org_spec, contract, role) -> list[str]:
    """The ordered commitments this role itself submits (contract declaration order:
    stage 1 before stage 2 — report before comment, draft before final). Drives the
    stage-aware retire gate + the platform's binding advances (D9)."""
    if org_spec.committer_binding == "any":
        return [c.commitment_id for c in contract.commitments]
    plays = set(role.plays or [role.role_id])
    return [c.commitment_id for c in contract.commitments
            if set(c.committer_roles or []) & plays]


def commitment_depth(contract, cid: str, _seen=None) -> int:
    """Length of the longest ``blocks`` chain into ``cid`` (spec_v1=0, implementation_v1=1)."""
    blocks = contract.commitment(cid).blocks
    return 0 if not blocks else 1 + max(commitment_depth(contract, b) for b in blocks)


def ordered_roles_for_pipeline(org_spec, contract):
    """Order the pipeline's roles into the handoff chain reader→builder→reviewer.

    Each role binds to the one commitment its ``plays`` matches; the chain follows the
    ``blocks`` DAG (required milestones by depth), with the optional review last. Returns
    ``[(role, commitment_id), …]`` in handoff order.
    """
    bound = []
    for role in org_spec.roles:
        cid = next((c.commitment_id for c in contract.commitments
                    if set(c.committer_roles) & set(role.plays)), None)
        if cid is not None:
            bound.append((role, cid))
    bound.sort(key=lambda rc: (0 if contract.commitment(rc[1]).required else 1,
                               commitment_depth(contract, rc[1])))
    return bound


def is_structurally_decomposed(org_spec) -> bool:
    """True for the pipeline arm: ≥2 distinct specialized roles bound ``by_role``.

    The other presets close the *single-submission* contract — one agent
    (``single_agent``), one context-expanded agent (``context_expanded_single_agent``),
    or N role-blind agents racing (``role_blind_ensemble``). The SCORED result is
    ``numeric_compare`` on the replicated numbers either way, so the arms stay
    comparable while the org structure differs (M7 §3). Running the literal
    decomposed-contract-held-by-one-agent for the single/ensemble arms is a documented
    deferral — it yields the same scored number and adds multi-commit-per-agent
    machinery for no scoring difference.
    """
    distinct_plays = {tuple(sorted(r.plays)) for r in org_spec.roles}
    return org_spec.committer_binding == "by_role" and len(distinct_plays) > 1


@dataclass
class RoleHooks:
    """What a protocol installs on one role's agent behavior at staging time.

    ``readiness`` gates scheduler admission (registered in ``rs.readiness`` when not
    None); ``inbound`` renders delivered mailbox items into the role's next turn;
    ``post_submit`` maps a successful submit to outbound ``MessageIntent`` handoffs.
    A protocol may also mutate the role's ``ToolContext`` directly (e.g. the
    deliberative participant lockout narrows ``decision_rights``)."""

    readiness: Callable[[], bool] | None = None
    inbound: Callable | None = None
    post_submit: Callable | None = None
    # Continuation after an accepted submit_results (M8 §1): when a procedure
    # supplies these, the runner uses them instead of deriving retirement from
    # the role's fixed commitment sequence and continuation from clocked
    # megabatching. None keeps the runner's defaults.
    retire_after_submit: Callable[[], bool] | None = None
    continue_after_submit: Callable[[], bool] | None = None


@dataclass
class CoordinationContext:
    """Everything a protocol's closures may reach — populated progressively by the
    runner: constructed after the coordinator exists; ``rs`` attaches after
    ``build_runtime``; ``tc_by_role`` fills during the staging loop (the dict is
    shared by reference, so closures created early observe later staging)."""

    org_spec: Any
    pack: Any
    coordinator: Any
    chain: list  # [(role, commitment_id), …] in staging order
    clocked: bool
    integrator_rotation: int
    integrator_id: str | None
    spine: Any
    tc_by_role: dict = field(default_factory=dict)
    rs: Any = None  # set after build_runtime, before make_on_start
    # Managed execution surface for procedures that run their own jobs (grading and
    # assessment containers, M8 §4): the run's backend, its Docker policy, the session
    # that owns every container, and the run directory. None on paths that stage no
    # containers.
    backend: Any = None
    policy: Any = None
    session: Any = None
    run_dir: Any = None

    @property
    def lc(self) -> dict:
        return self.org_spec.live_coordination or {}

    def role_commitment_seq(self, role) -> list[str]:
        return role_commitment_seq(self.org_spec, self.pack.outcome_contract, role)


async def stub_missing(ctx: CoordinationContext, cids: list, timeout: float,
                       stub_payload_for) -> None:
    """Bounded wait for ``cids``, then platform-commit an honest empty stand-in for
    each still missing (agent_id "coordination") — a CONSTRAINT (coordination.report_timeout),
    never an intervention. One dead participant must not starve the cell."""
    import time as _time
    coordinator, rs = ctx.coordinator, ctx.rs
    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        if all(c in coordinator.committed for c in cids) or rs.is_done():
            return
        await asyncio.sleep(1.0)
    missing = [c for c in cids if c not in coordinator.committed]
    if not missing:
        return
    ev = await ctx.spine.emit_event(
        "coordination.report_timeout",
        payload={"missing": missing, "waited_s": timeout})
    for cid in missing:
        await coordinator.commit(commitment_id=cid, payload=stub_payload_for(cid),
                                 agent_id="coordination", session_id="coordination",
                                 caused_by=ev)
    rs.kick_scheduler()


class CoordinationProtocol:
    """One organizational form's live choreography, behind a typed seam.

    Class attributes are the form's *declared* structural properties, read by the
    runner before any resource exists: ``contract_profile`` selects the pack's
    default profile (an org's ``live_coordination.contract_profile`` still
    overrides); ``is_decomposed`` loads the decomposed contract and stamps the
    manifest; ``is_deliberative`` switches the behavior into volley production and
    the deliberation cache policy. Instances are per-run and may hold per-run
    state resolved in ``build_chain``."""

    mode: str | None = None  # registry key; None = structurally-resolved built-in
    is_deliberative: bool = False
    is_decomposed: bool = False
    contract_profile: str | None = None
    # Append the first bound commitment's duty text to the initial prompt (the
    # staged collective's wave kickoff; auto_advance packs get it regardless).
    initial_duty_in_prompt: bool = False

    def integrator_role(self, org_spec, pack, integrator_rotation: int) -> str | None:
        """The designated composer's role_id, when the form has one (manifest pin)."""
        return None

    def build_chain(self, org_spec, contract) -> list:
        """Bind each role to its first commitment, in staging order — PREFLIGHT,
        resource-free; raise to refuse the run before anything stages."""
        raise NotImplementedError

    def role_hooks(self, ctx: CoordinationContext, index: int, role,
                   commit_id: str, tool_ctx) -> RoleHooks:
        """Per-role admission/inbound/post-submit closures, built at staging time."""
        return RoleHooks()

    def handoff_contract(self, ctx: CoordinationContext):
        """The form's declared handoff topology (None = no formal handoff channel)."""
        return None

    def make_on_start(self, ctx: CoordinationContext) -> Callable[[], Awaitable] | None:
        """The platform orchestration run beside the agent loops (None = none)."""
        return None


# Open protocol registry (validated, never enumerated in core): built-ins register
# on package import; plugin modes register when the org's declared
# ``live_coordination.protocol_module`` is imported at resolve time.
_PROTOCOLS: dict[str, type] = {}

# The mode keys core itself ships (registered on package import). Registration
# is process-global, so an org naming a PLUGIN mode must declare its
# ``protocol_module`` in every spec that uses it — a prior resolve's import is
# never a substitute for the declaration (probe 2026-08-17).
BUILTIN_MODES: frozenset[str] = frozenset({"staged_collective"})


def register_coordination_protocol(cls: type) -> type:
    """Register a protocol class under its declared ``mode`` (decorator-friendly).

    Idempotent for the same class (org specs resolve repeatedly per sweep);
    refuses a CONFLICTING re-registration — two plugins may not fight over one
    mode key, that is a naming bug worth failing loudly on."""
    key = getattr(cls, "mode", None)
    if not key:
        raise ValueError(f"{cls.__name__} declares no registry mode")
    existing = _PROTOCOLS.get(key)
    if existing is not None and existing is not cls:
        raise ValueError(f"coordination mode {key!r} already registered by "
                         f"{existing.__module__}.{existing.__name__}")
    _PROTOCOLS[key] = cls
    return cls


def resolve_coordination_protocol(org_spec) -> CoordinationProtocol:
    """ONE protocol instance per run, resolved from the org's declaration.

    ``live_coordination.mode`` keys the registry (fail-closed on unknown);
    ``live_coordination.protocol_module`` is imported first so a plugin mode can
    register itself (config-as-data — the coordination analogue of the manifest's
    ``submission_gates`` modules). With no declared mode, the built-in structural
    split applies: the by-role multi-play pipeline, else the single-submission
    default."""
    lc = org_spec.live_coordination or {}
    module_ref = lc.get("protocol_module")
    if module_ref:
        importlib.import_module(str(module_ref))  # registration side effect; idempotent
    mode = lc.get("mode")
    if mode is not None:
        cls = _PROTOCOLS.get(mode)
        if cls is None:
            raise ValueError(
                f"unknown live_coordination.mode {mode!r} (registered: "
                f"{sorted(_PROTOCOLS)}); a plugin mode must declare its "
                f"live_coordination.protocol_module")
        # PROVENANCE, not presence (probe round 2, 2026-08-17): a non-built-in
        # mode must be registered BY the module this org itself declares — a
        # bogus protocol_module cannot launder an earlier resolve's import.
        # Provenance is the protocol class's defining module, so repeated
        # resolves stay valid.
        if (mode not in BUILTIN_MODES
                and cls.__module__ != str(module_ref or "")):
            raise ValueError(
                f"live_coordination.mode {mode!r} is not a built-in mode and is "
                f"not registered by this org's declared protocol_module "
                f"({module_ref!r}; registered by: {cls.__module__!r}) — another "
                "spec's earlier import is not a declaration (declare the module "
                "that DEFINES the protocol class)")
        return cls()
    from oaos2.experiments.coordination.default import SingleSubmissionProtocol
    from oaos2.experiments.coordination.pipeline import PipelineProtocol
    return (PipelineProtocol() if is_structurally_decomposed(org_spec)
            else SingleSubmissionProtocol())
