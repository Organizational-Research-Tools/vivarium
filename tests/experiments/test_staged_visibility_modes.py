"""``contribution_visibility`` is the staged collective's whole disclosure surface.

The three declared modes are asserted at the seam that computes recipients, because
Study C1's "acts before the other's action is known" cell (roadmap §9B) rests on the
claim that a committed contribution reaches nobody.  Leaving the pair unblocked in the
contract DAG is NOT sufficient: under ``shared_sequential`` the first committer's
``post_submit`` handoff still discloses.  Concealment therefore has to be its own
declared, fail-closed mode — which is what these tests pin.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from oaos2.experiments.coordination.base import CoordinationContext
from oaos2.experiments.coordination.staged import StagedCollectiveProtocol


@dataclass
class _Role:
    role_id: str
    plays: list = field(default_factory=list)


@dataclass
class _Commitment:
    commitment_id: str
    blocks: list = field(default_factory=list)
    committer_roles: list = field(default_factory=list)


class _Contract:
    def __init__(self, cids):
        self.commitments = [_Commitment(c) for c in cids]

    def commitment(self, cid):
        return next(c for c in self.commitments if c.commitment_id == cid)


class _Coordinator:
    def __init__(self, contract):
        self.contract = contract
        self.committed: dict = {}
        self.payloads = {"choice_a": {"option": "A2"}}


@dataclass
class _OrgSpec:
    preset_id: str
    roles: list
    live_coordination: dict
    committer_binding: str = "by_role"


class _ToolCtx:
    def __init__(self, cid):
        self.submit_commitment_id = cid
        self.last_submitted_commitment_id = cid


def _targets(live_coordination: dict, *, from_role: str = "office_a") -> list[str]:
    """Recipients of ``from_role``'s committed contribution under this declaration."""
    roles = [_Role("office_a", ["a"]), _Role("office_b", ["b"]), _Role("integrator", ["i"])]
    contract = _Contract(["choice_a"])
    ctx = CoordinationContext(
        org_spec=_OrgSpec("c1_probe", roles, live_coordination), pack=None,
        coordinator=_Coordinator(contract), chain=[], clocked=False,
        integrator_rotation=0, integrator_id=None, spine=None)
    role = next(r for r in roles if r.role_id == from_role)
    hooks = StagedCollectiveProtocol().role_hooks(ctx, 0, role, "choice_a", _ToolCtx("choice_a"))
    return [m.to_agent for m in hooks.post_submit()]


def test_shared_sequential_discloses_to_every_peer() -> None:
    assert sorted(_targets({"contribution_visibility": "shared_sequential"})) == [
        "integrator", "office_b"]


def test_private_fanin_discloses_only_to_the_sink() -> None:
    assert _targets({"contribution_visibility": "private_fanin",
                     "integration_role": "integrator"}) == ["integrator"]


def test_concealed_discloses_to_nobody() -> None:
    # The C1 `before` cell: committed, scoreable, and invisible to the partner.
    assert _targets({"contribution_visibility": "concealed"}) == []


def test_concealed_carries_the_payload_nowhere_for_either_role() -> None:
    # Symmetry matters: "concealed" must not be an artefact of commit ORDER.
    for role_id in ("office_a", "office_b", "integrator"):
        assert _targets({"contribution_visibility": "concealed"}, from_role=role_id) == []


def test_concealed_with_an_integration_role_fails_closed() -> None:
    # A declared sink contradicts the mode; silently ignoring it would let a
    # mis-authored preset look concealed while a reviewer reads the sink as intent.
    with pytest.raises(ValueError, match="concealed .* no recipient"):
        _targets({"contribution_visibility": "concealed", "integration_role": "integrator"})


def test_unknown_visibility_still_fails_closed() -> None:
    with pytest.raises(ValueError, match="'private_fanin', 'shared_sequential' or 'concealed'"):
        _targets({"contribution_visibility": "eventually_shared"})


def test_disclosed_handoff_carries_the_committed_payload() -> None:
    # Guards the negative test above: `concealed` is empty because there is no
    # recipient, not because the payload path silently produced nothing.
    roles = [_Role("office_a", ["a"]), _Role("office_b", ["b"])]
    contract = _Contract(["choice_a"])
    ctx = CoordinationContext(
        org_spec=_OrgSpec("c1_probe", roles, {"contribution_visibility": "shared_sequential"}),
        pack=None, coordinator=_Coordinator(contract), chain=[], clocked=False,
        integrator_rotation=0, integrator_id=None, spine=None)
    hooks = StagedCollectiveProtocol().role_hooks(
        ctx, 0, roles[0], "choice_a", _ToolCtx("choice_a"))
    (msg,) = hooks.post_submit()
    assert json.loads(msg.payload)["payload"] == {"option": "A2"}
