"""Choose which ready agents may work from a snapshot of runtime state.

free admits all idle agents; sequential and round_robin admit one ready agent
at a time in rotation; manager_dispatch uses the manager's
latest admission directive. clocked_rounds also limits work to one turn per
live role per logical day. The runtime applies dependency overrides for waiting
requests and conversations, with separate stall detection.

Register additional policies with register_scheduler_policy and load their module
through scheduler_module in the organization file. Unknown policies are refused.
The scheduling function returns a set of agent IDs; it does not run the agents."""

from __future__ import annotations

from typing import Callable, Protocol

# A scheduler policy is a pure function over the snapshot.
SchedulerPolicy = Callable[["object"], set]


class _Snapshot(Protocol):
    idle_agents: list[str]  # admittable now (not running, not paused, not retired)
    last_actor: str | None
    all_agent_order: list[str]  # stable ordering of all agents
    manager_last_dispatch: list[str] | None


def free_policy(snap) -> set:
    return set(snap.idle_agents)


def _next_after(snap) -> set:
    """Admit exactly one idle agent: the next in rotation after ``last_actor``.

    Rotating (rather than always picking the lowest) is what keeps a one-at-a-time
    policy from starving later agents — the turn advances past whoever just acted.
    """
    # Ordinary turns are serial. The runtime can still explicitly admit a
    # dependency responder while another agent is paused.
    if getattr(snap, "running_agents", ()):
        return set()
    order = snap.all_agent_order
    if not order:
        return set()
    start = 0
    if snap.last_actor in order:
        start = (order.index(snap.last_actor) + 1) % len(order)
    n = len(order)
    for i in range(n):
        cand = order[(start + i) % n]
        if cand in snap.idle_agents:
            return {cand}
    return set()


def sequential_policy(snap) -> set:
    # One at a time, rotating so no agent is starved (the researcher's turn-taking
    # treatment, implemented as an admission constraint over the concurrent engine).
    return _next_after(snap)


def round_robin_policy(snap) -> set:
    return _next_after(snap)


def manager_dispatch_policy(snap) -> set:
    directive = snap.manager_last_dispatch or []
    return {a for a in directive if a in snap.idle_agents}


def clocked_rounds_policy(snap) -> set:
    """Decision (c), clock_design.md §1: one turn per live role per round.

    Admit every idle agent that has not yet spent this round's turn — genuine
    parallelism within the round (headcount = lanes), a hard per-round cap per
    agent. Round advance itself is the kernel's quiescence rule (runtime.py);
    this policy only enforces the per-round turn budget.
    """
    if getattr(snap, "clock_round", 0) == 0:
        return set()  # nothing acts before the first round opens
    acted = getattr(snap, "clock_acted", frozenset())
    return {a for a in snap.idle_agents if a not in acted}


SCHEDULER_POLICIES: dict[str, SchedulerPolicy] = {
    "free": free_policy,
    "sequential": sequential_policy,
    "round_robin": round_robin_policy,
    "manager_dispatch": manager_dispatch_policy,
    "clocked_rounds": clocked_rounds_policy,
}

# The names core itself ships. Registration is process-global (Python import
# semantics), so an org naming a PLUGIN policy must declare its
# ``scheduler_module`` in every YAML that uses it — a prior load's import is
# never a substitute for the declaration (probe 2026-08-17).
FOUNDATION_SCHEDULER_POLICIES: frozenset[str] = frozenset(SCHEDULER_POLICIES)

# name → the module that registered it (probe round 2): the org loader verifies
# the org's declared scheduler_module IS the policy's registering module, so a
# bogus declaration cannot launder another config's earlier import.
SCHEDULER_PROVENANCE: dict[str, str] = {name: __name__ for name in SCHEDULER_POLICIES}


def register_scheduler_policy(name: str, policy: SchedulerPolicy) -> None:
    """Register an admission policy under its org-declared name (open registry).

    The coordination-registry rule applied to schedulers: idempotent for the
    same function (org specs load repeatedly per sweep), refuses a CONFLICTING
    re-registration — two plugins may not fight over one policy name. A plugin
    policy registers when the org YAML's declared ``scheduler_module`` is
    imported at load time — config-as-data, never a core edit."""
    if not name:
        raise ValueError("scheduler policy name must be non-empty")
    existing = SCHEDULER_POLICIES.get(name)
    if existing is not None and existing is not policy:
        raise ValueError(f"scheduler policy {name!r} is already registered")
    SCHEDULER_POLICIES[name] = policy
    SCHEDULER_PROVENANCE[name] = getattr(policy, "__module__", "") or ""


def resolve_scheduler_policy(name: str) -> SchedulerPolicy:
    """Resolve a policy name — FAILS CLOSED with the registered vocabulary."""
    policy = SCHEDULER_POLICIES.get(name)
    if policy is None:
        raise ValueError(
            f"unknown scheduler policy {name!r} (registered: "
            f"{sorted(SCHEDULER_POLICIES)}); a plugin policy must be registered "
            f"via register_scheduler_policy (org YAML: scheduler_module)")
    return policy
