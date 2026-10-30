"""A NOVEL coordination mode built entirely OUTSIDE core — the round-8 canary plugin.

Everything here uses only the public protocol seam
(``oaos2.experiments.coordination``): if this module plus an org declaration can
drive ``run_org_live`` end-to-end, a new organizational form is data + a
registered plugin — zero core diff. The org spec names this module via
``live_coordination.protocol_module``; importing it registers the mode."""

from __future__ import annotations

import json

from oaos2.communication.messages import MessageIntent
from oaos2.experiments.coordination import (
    CoordinationProtocol,
    RoleHooks,
    make_inbound_handler,
    register_coordination_protocol,
    role_commitment_seq,
)
from oaos2.protocols.coordination import HandoffContract


@register_coordination_protocol
class RelayRingProtocol(CoordinationProtocol):
    """An org-declared relay: ``live_coordination.relay_order`` names the
    submission order; each role unlocks when its predecessor commits and
    receives the predecessor's payload; the platform announces the relay at
    start. Deliberately NOT the pipeline: the order is org data, not the
    contract's blocks-depth."""

    mode = "relay_ring"
    is_decomposed = True  # rides the decomposed contract, like the pipeline arm

    def build_chain(self, org_spec, contract) -> list:
        order = list((org_spec.live_coordination or {}).get("relay_order") or [])
        by_id = {r.role_id: r for r in org_spec.roles}
        if sorted(order) != sorted(by_id):
            raise ValueError("relay_ring requires live_coordination.relay_order "
                             "naming every role exactly once")
        chain = []
        for rid in order:
            seq = role_commitment_seq(org_spec, contract, by_id[rid])
            if not seq:
                raise ValueError(f"relay role {rid!r} has no commitment binding")
            chain.append((by_id[rid], seq[0]))
        return chain

    def role_hooks(self, ctx, index, role, commit_id, tool_ctx) -> RoleHooks:
        coordinator = ctx.coordinator
        hooks = RoleHooks()
        if index > 0:
            prev_cid = ctx.chain[index - 1][1]
            hooks.readiness = (lambda pcid=prev_cid: pcid in coordinator.committed)
            hooks.inbound = make_inbound_handler()
        if index < len(ctx.chain) - 1:
            nxt = ctx.chain[index + 1][0].role_id
            hooks.post_submit = (lambda to=nxt, cid=commit_id: [MessageIntent(
                to_agent=to, kind="handoff",
                payload=json.dumps(coordinator.payloads.get(cid, {}), sort_keys=True))])
        return hooks

    def handoff_contract(self, ctx):
        role_ids = [r.role_id for r, _ in ctx.chain]
        return HandoffContract(
            contract_id=f"{ctx.org_spec.preset_id}_relay_ring",
            shape="one_to_one", senders=role_ids, recipients=role_ids,
        )

    def make_on_start(self, ctx):
        async def _kickoff():
            await ctx.spine.emit_event(
                "coordination.stage_advanced",
                payload={"phase": "relay_kickoff",
                         "order": [r.role_id for r, _ in ctx.chain]})
            ctx.rs.kick_scheduler()
        return _kickoff
