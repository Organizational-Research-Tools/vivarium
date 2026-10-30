"""Route completed work along the task contract's role dependencies.

The procedure is selected for by-role binding with at least two distinct plays.
It follows blocks dependencies for handoffs; it is not restricted to a fixed
reader/builder/reviewer sequence and needs no explicit live_coordination.mode."""

from __future__ import annotations

import json

from oaos2.communication.messages import MessageIntent
from oaos2.experiments.coordination.base import (
    CoordinationContext,
    CoordinationProtocol,
    RoleHooks,
    make_inbound_handler,
    ordered_roles_for_pipeline,
)
from oaos2.protocols.coordination import HandoffContract


class PipelineProtocol(CoordinationProtocol):
    mode = None  # structurally resolved (no live_coordination.mode)
    is_decomposed = True

    def build_chain(self, org_spec, contract) -> list:
        # Binds each role to its commitment and orders by blocks-depth: the
        # pipeline's linear chain — the same DAG machinery serves the hierarchy's
        # fan-in (hierarchical.py).
        return ordered_roles_for_pipeline(org_spec, contract)

    def role_hooks(self, ctx: CoordinationContext, index: int, role,
                   commit_id: str, tool_ctx) -> RoleHooks:
        coordinator = ctx.coordinator
        hooks = RoleHooks()
        if index > 0:
            prev_cid = ctx.chain[index - 1][1]
            hooks.readiness = (lambda pcid=prev_cid: pcid in coordinator.committed)
            hooks.inbound = make_inbound_handler()
        if index < len(ctx.chain) - 1:
            # Hand the committed payload to the next role in the chain.
            nxt = ctx.chain[index + 1][0].role_id
            hooks.post_submit = (lambda to=nxt, cid=commit_id: [MessageIntent(
                to_agent=to, kind="handoff",
                payload=json.dumps(coordinator.payloads.get(cid, {}), sort_keys=True))])
        return hooks

    def handoff_contract(self, ctx: CoordinationContext):
        # The pipeline's handoff topology: the ordered roles may hand off to one
        # another. A handoff to a role outside this set is refused (M6 §1).
        role_ids = [r.role_id for r, _ in ctx.chain]
        return HandoffContract(
            contract_id=f"{ctx.org_spec.preset_id}_pipeline_handoff",
            shape="one_to_one", senders=role_ids, recipients=role_ids,
        )
