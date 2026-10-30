"""Sequence contributions using the task contract's declared dependencies.

The contract supplies stages and role bindings. Organization settings choose
private_fanin (reports to an integrator), shared_sequential (shared contributions),
or concealed (no recipient). The procedure records declared handoff formats and
source references; interpretation of information loss remains archive analysis."""

from __future__ import annotations

import json

from oaos2.communication.messages import MessageIntent
from oaos2.experiments.coordination.base import (
    CoordinationContext,
    CoordinationProtocol,
    RoleHooks,
    make_inbound_handler,
    register_coordination_protocol,
    role_commitment_seq,
)
from oaos2.protocols.coordination import HandoffContract


def _trigger_refs(payload) -> list[str]:
    """Every string under any ``trigger_refs`` key in a committed payload, sorted
    and unique — the source-packet refs a filing cites (task-neutral: the key is
    the platform ExceptionRecord vocabulary)."""
    found: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "trigger_refs" and isinstance(value, list):
                    found.update(str(v) for v in value if str(v).strip())
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)
    walk(payload)
    return sorted(found)


@register_coordination_protocol
class StagedCollectiveProtocol(CoordinationProtocol):
    mode = "staged_collective"
    initial_duty_in_prompt = True

    def build_chain(self, org_spec, contract) -> list:
        # Every role starts at the first commitment its declared `plays` grants.
        # Subsequent bindings follow the contract declaration order; readiness follows
        # `blocks`, so the task manifest—not engine choreography—owns the wave DAG.
        chain = []
        for role in org_spec.roles:
            sequence = role_commitment_seq(org_spec, contract, role)
            if not sequence:
                raise ValueError(
                    f"staged collective role {role.role_id!r} has no commitment binding")
            chain.append((role, sequence[0]))
        return chain

    def role_hooks(self, ctx: CoordinationContext, index: int, role,
                   commit_id: str, tool_ctx) -> RoleHooks:
        coordinator, org_spec = ctx.coordinator, ctx.org_spec
        hooks = RoleHooks()
        # One generic gate serves reports, patches, dispositions, and specifications:
        # the role is runnable exactly when its current contract slot is uncommitted
        # and every declared blocker has crossed commit().
        hooks.readiness = (lambda tc=tool_ctx:
                           tc.submit_commitment_id not in coordinator.committed
                           and all(b in coordinator.committed for b in
                                   coordinator.contract.commitment(
                                       tc.submit_commitment_id).blocks))
        hooks.inbound = make_inbound_handler()

        lc = ctx.lc
        visibility = lc.get("contribution_visibility")
        sink = lc.get("integration_role")
        role_ids = [r.role_id for r in org_spec.roles]
        if visibility == "private_fanin":
            if sink not in role_ids:
                raise ValueError(
                    "staged private_fanin requires a valid live_coordination.integration_role")
            targets = ([rid for rid in role_ids if rid != role.role_id]
                       if role.role_id == sink and lc.get(
                           "integrated_state_visibility") == "broadcast"
                       else ([sink] if role.role_id != sink else []))
        elif visibility == "shared_sequential":
            targets = [rid for rid in role_ids if rid != role.role_id]
        elif visibility == "concealed":
            # A committed contribution reaches NOBODY (roadmap §9B / Study C1's
            # "acts before the other's action is known" cell: a dyad with no
            # integrator sink).  Leaving the pair unblocked in the contract DAG does
            # not conceal on its own — whichever role commits first still fires its
            # post_submit handoff under shared_sequential — so concealment is a
            # declared mode, not the absence of a gate.  An integration_role here
            # would contradict the mode: fail closed rather than silently ignore it.
            if sink is not None:
                raise ValueError(
                    "staged concealed visibility cannot declare an integration_role: "
                    "a concealed contribution has no recipient")
            targets = []
        else:
            raise ValueError(
                "staged collective contribution_visibility must be "
                "'private_fanin', 'shared_sequential' or 'concealed'")

        # CH1: the arm's declared channel form rides every staged handoff, and the
        # payload's ``trigger_refs`` (the platform exception-record vocabulary,
        # protocols/exceptions.py) name the source packets it was written from.
        handoff_format = lc.get("handoff_format")

        def _staged_handoffs(*, tc=tool_ctx, to_roles=tuple(targets)):
            cid = tc.last_submitted_commitment_id
            if cid is None:
                return []
            body = coordinator.payloads.get(cid, {})
            payload = {"commitment_id": cid, "payload": body}
            encoded = json.dumps(payload, sort_keys=True)
            extensions = {"formalized_ref": f"submitted/{cid}.json"}
            if handoff_format is not None:
                extensions["handoff_format"] = str(handoff_format)
            refs = _trigger_refs(body)
            if refs:
                extensions["source_refs"] = refs
            return [MessageIntent(
                to_agent=target, kind="handoff", payload=encoded,
                extensions=dict(extensions),
            )
                    for target in to_roles]

        hooks.post_submit = _staged_handoffs
        return hooks

    def handoff_contract(self, ctx: CoordinationContext):
        # The OrganizationSpec topology supplies the directional whitelist.  This
        # contract supplies the task-neutral formal-handoff boundary and trace delta.
        role_ids = [r.role_id for r in ctx.org_spec.roles]
        return HandoffContract(
            contract_id=f"{ctx.org_spec.preset_id}_staged_record",
            shape="one_to_one", senders=role_ids, recipients=role_ids,
        )
