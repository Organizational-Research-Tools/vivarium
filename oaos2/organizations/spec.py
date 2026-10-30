"""Define and validate organization settings independently of task materials.

A Role describes one agent position, its materials, task-role bindings, tools,
rights, model override, context limit, and notice scopes. OrganizationSpec groups
roles with scheduling, communication paths, and coordination settings. n_agents
is the number of Role entries; plays names task roles, not copies of an agent.

Concrete presets live in library/organizations/. The loader reads them and the
runtime enforces supported controls. Validation here checks rights, referenced
roles, and tool-grant narrowing; it is not a complete behavioral treatment audit."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

from oaos2.decision_rights import DecisionRights, DecisionRightsRegistry
from oaos2.organizations.precedence import check_not_broadening
from oaos2.organizations.topology import Topology


@dataclass
class Role:
    role_id: str
    attention: str  # material scope, such as "sample/spec", "implementation", or "all"
    plays: list[str]  # task-role names used to bind this agent to submission contracts
    specialized: bool  # whether the offline solver uses implementation specialization
    role_packet: str | None = None  # task prompt packet; defaults to role_id
    tools: list[str] | None = None  # None inherits the organization's tool grant
    decision_rights: DecisionRights | None = None  # submission, handoff, and review authority
    comm_kinds: frozenset[str] | None = None  # allowed outgoing kinds; None adds no role limit
    model_ref: str | None = None  # inherits the run's model when unset
    out_of_scope_areas: tuple = ()  # declared attention exclusions for audit
    # A study can restrict retained context below the model's own context limit.
    # A run-level sweep override applies one budget across roles.
    context_budget_tokens: int | None = None
    max_calls_per_slot: int | None = None  # calls for one bound submission; resets on advance
    # A role-specific daily call ceiling in clocked runs (LK1 amendment §12): unset means the
    # clock's calls_per_day. Identical across arms for the same role; recorded in the manifest.
    calls_per_day: int | None = None
    # Additional notice scopes, beyond attention. This changes incoming notices,
    # not the task materials selected by attention. CH1's evidence integrator uses
    # office scopes to receive the source notices alongside submitted reports.
    packet_scopes: tuple = ()


@dataclass
class OrganizationSpec:
    preset_id: str
    roles: list[Role]
    scheduler: str = "free"  # any registered scheduler policy (open registry,
                             # organizations/scheduler.py; plugins via the org
                             # YAML's scheduler_module)
    committer_binding: str = "by_role"  # by_role | any
    context_expansion: str | None = None  # e.g. "pipeline_decomposition"
    # --- §18.1 structure surface (optional). topology=None ⇒ complete graph (default).
    topology: Topology | None = None  # which kinds flow between which roles
    tools: frozenset[str] | None = None  # org-level tool ceiling; role.tools must narrow it
    precedence_rules: dict = field(default_factory=dict)  # per-dimension scope-order overrides
    live_coordination: dict | None = None  # coordination mode and its protocol settings
    decision_rights_registry: DecisionRightsRegistry | None = None  # validates role rights keys
    source_ref: Path | None = None  # canonical YAML when loaded from the library
    base_refs: tuple[Path, ...] = ()  # the presets source_ref names as its base, outermost first
    n_agents: int = field(init=False)

    def __post_init__(self) -> None:
        self.n_agents = len(self.roles)

    def validate(self) -> None:
        """Check registered rights, referenced roles, role tools against the organization grant, and the
        task settings against what the task plugin reads."""
        registry = self.decision_rights_registry or DecisionRightsRegistry()
        role_ids = {r.role_id for r in self.roles}
        for r in self.roles:
            if r.decision_rights is not None:
                registry.validate(r.decision_rights, role_id=r.role_id)
                # review_authority / handoff acceptance must name roles that exist.
                for target in r.decision_rights.review_authority_over:
                    if target not in role_ids:
                        raise ValueError(f"role {r.role_id!r} claims review authority over "
                                         f"unknown role {target!r}")
            # A role's tool grant may only narrow the org-level ceiling (never broaden).
            if self.tools is not None and r.tools is not None:
                check_not_broadening(self.tools, frozenset(r.tools), dimension=f"tools[{r.role_id}]")
        if self.topology is not None:
            for c in self.topology.channels:
                missing = {c.from_role, c.to_role} - role_ids
                if missing:
                    raise ValueError(f"topology channel references unknown role(s) {sorted(missing)}")
        # A task plugin checks its own settings: its protocol module may define validate_settings(spec),
        # which refuses an unknown or ignored setting by name (oaos2/tasks/settings.py; October 19, 2026).
        module = (self.live_coordination or {}).get("protocol_module")
        if module:
            check = getattr(importlib.import_module(str(module)), "validate_settings", None)
            if check is not None:
                check(self)
