"""M5 organization-structure surface (DESIGN §18.1, §4.9): decision rights, topology
channels, and "tighter scope only narrows" resolution across all policy channels."""

from __future__ import annotations

import pytest

from oaos2.decision_rights import (
    COLLABORATION_DEFAULT_RIGHTS,
    DecisionRights,
    DecisionRightsRegistry,
    UnknownDecisionRight,
)
from oaos2.organizations.precedence import (
    BroadeningRejected,
    order_scopes,
    resolve_scoped_grant,
)
from oaos2.organizations.spec import OrganizationSpec, Role
from oaos2.organizations.topology import Channel, Topology


# --- decision rights: open registry, validated keys, authority checks ------ #

def test_decision_rights_default_and_checks() -> None:
    dr = DecisionRights(may_submit_milestones=False,
                        may_accept_handoffs_from=("reader",),
                        review_authority_over=("builder",))
    assert not dr.can_submit()
    assert dr.can_accept_handoff_from("reader") and not dr.can_accept_handoff_from("reviewer")
    assert dr.has_review_authority_over("builder") and not dr.has_review_authority_over("reader")
    # "*" wildcard accepts any handoff source.
    assert DecisionRights().can_accept_handoff_from("anyone")


def test_registry_rejects_unregistered_right() -> None:
    reg = DecisionRightsRegistry()  # collaboration-default keys only
    assert all(k in reg for k in COLLABORATION_DEFAULT_RIGHTS)
    bad = DecisionRights(extensions={"may_fire_subordinates": ("worker",)})  # politics pack key
    with pytest.raises(UnknownDecisionRight):
        reg.validate(bad, role_id="boss")
    reg.register("may_fire_subordinates")  # a pack registers its key…
    reg.validate(bad, role_id="boss")  # …then it validates


# --- topology channels ----------------------------------------------------- #

def test_topology_complete_by_default_then_whitelist() -> None:
    assert Topology().allows("a", "b", "handoff")  # empty ⇒ complete graph
    strict = Topology(channels=(
        Channel("reader", "builder", frozenset({"handoff"})),
        Channel("builder", "reviewer"),  # "*" kinds
    ))
    assert strict.allows("reader", "builder", "handoff")
    assert not strict.allows("reader", "builder", "message")  # wrong kind on the edge
    assert strict.allows("builder", "reviewer", "anything")   # "*" edge
    assert not strict.allows("reviewer", "reader", "handoff")  # no such edge
    assert strict.reachable_targets("reader", "handoff") == {"builder"}


# --- tighter-scope-narrows across channels (generalized) ------------------- #

def test_resolve_scoped_grant_narrows_and_rejects_broadening() -> None:
    org = frozenset({"read_file", "write_file", "run_python", "submit_results"})
    role = frozenset({"read_file", "submit_results"})
    agent = None  # unspecified ⇒ inherit
    assert resolve_scoped_grant([org, role, agent], dimension="tools") == role
    # An explicit empty narrows to nothing (a read-only-of-nothing role).
    assert resolve_scoped_grant([org, frozenset()], dimension="tools") == frozenset()
    # A tighter scope that ADDS a tool the org never granted is rejected at load.
    with pytest.raises(BroadeningRejected):
        resolve_scoped_grant([role, frozenset({"run_python"})], dimension="tools")


def test_precedence_rules_reorder_dimension() -> None:
    scope_map = {"org": frozenset({"a", "b"}), "role": frozenset({"a"}), "agent": frozenset()}
    # Default ladder uses all three → empty (agent narrows to nothing).
    assert resolve_scoped_grant(order_scopes(scope_map, dimension="tools")) == frozenset()
    # A rule pinning tools to org-only drops the inner scopes entirely.
    pinned = order_scopes(scope_map, dimension="tools", precedence_rules={"tools": ("org",)})
    assert resolve_scoped_grant(pinned) == frozenset({"a", "b"})


# --- OrganizationSpec.validate wires it together --------------------------- #

def _role(rid, **kw):
    return Role(role_id=rid, attention="all", plays=[rid], specialized=False, **kw)


def test_org_validate_accepts_well_formed_structure() -> None:
    org = OrganizationSpec(
        preset_id="structured", scheduler="manager_dispatch",
        roles=[
            _role("lead", decision_rights=DecisionRights(may_submit_milestones=True,
                                                         review_authority_over=("worker",))),
            _role("worker", decision_rights=DecisionRights(may_submit_milestones=False),
                  tools=["read_file"]),
        ],
        tools=frozenset({"read_file", "write_file", "submit_results"}),
        topology=Topology(channels=(Channel("worker", "lead", frozenset({"handoff"})),)),
    )
    org.validate()  # no raise


def test_org_validate_rejects_review_over_unknown_role() -> None:
    org = OrganizationSpec(
        preset_id="bad", roles=[_role("lead", decision_rights=DecisionRights(review_authority_over=("ghost",)))],
    )
    with pytest.raises(ValueError):
        org.validate()


def test_org_validate_rejects_role_tools_broadening_org_ceiling() -> None:
    org = OrganizationSpec(
        preset_id="bad", roles=[_role("w", tools=["run_python"])],
        tools=frozenset({"read_file"}),  # ceiling lacks run_python
    )
    with pytest.raises(BroadeningRejected):
        org.validate()


def test_org_validate_rejects_topology_unknown_role() -> None:
    org = OrganizationSpec(
        preset_id="bad", roles=[_role("a")],
        topology=Topology(channels=(Channel("a", "missing"),)),
    )
    with pytest.raises(ValueError):
        org.validate()
