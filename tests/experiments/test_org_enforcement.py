"""Org-structure enforcement wired into the live seams (M5 §18.1): submit authority
at the commit boundary and topology/handoff-acceptance at the handoff seam. The four
decomposition-only arms set no structure, so these default to permissive."""

from __future__ import annotations

from types import SimpleNamespace

from oaos2.agents.tools import ToolContext, _submit
from oaos2.communication.messages import MessageIntent
from oaos2.decision_rights import DecisionRights
from oaos2.kernel.run_dir import RunDir
from oaos2.kernel.runtime import RuntimeState, _route_handoff, make_agent
from oaos2.organizations.topology import Channel, Topology
from oaos2.trace.invariants import load_all_events
from oaos2.trace.spine import RunSpine


async def _spine(tmp_path, run="r"):
    rd = RunDir.create(tmp_path, "e", "p", run)
    spine = RunSpine(rd.root, run_id=run)
    await spine.start()
    return rd, spine


def _violations(rd):
    return [e["payload"].get("reason") for e in load_all_events(rd.root)
            if e["event_class"] == "protocol.violation"]


# --- submit authority (may_submit_milestones) at the commit boundary ------- #

async def test_submit_refused_without_authority(tmp_path) -> None:
    rd, spine = await _spine(tmp_path)
    ctx = ToolContext(agent_id="worker", rs=SimpleNamespace(spine=spine), backend=None, handle=None,
                      run_dir=rd, coordinator=None, submit_commitment_id="impl_v1",
                      decision_rights=DecisionRights(may_submit_milestones=False))
    seed = await spine.emit_event("turn.started", agent_id="worker", turn_id="t1")
    res = await _submit({"x": 1}, ctx, turn_id="t1", caused_by=seed)
    await spine.finalize("completed")
    assert not res.submitted and "not authorized" in res.text
    assert "submit_without_authority" in _violations(rd)  # refused before any commit


# --- topology + handoff acceptance at the handoff seam --------------------- #

async def _rs_two_agents(spine):
    rs = RuntimeState(run_id="r", spine=spine)
    rs.agents["A"] = make_agent("A", behavior=None, role_id="a")
    rs.agents["B"] = make_agent("B", behavior=None, role_id="b")
    return rs


def _handoff_to_B():
    return MessageIntent(to_agent="B", kind="handoff", payload="{}")


async def test_handoff_blocked_by_org_topology(tmp_path) -> None:
    rd, spine = await _spine(tmp_path)
    rs = await _rs_two_agents(spine)
    rs.topology = Topology(channels=(Channel("a", "c", frozenset({"handoff"})),))  # a→c only, not a→b
    seed = await spine.emit_event("turn.started", agent_id="A", turn_id="t")
    ok = await _route_handoff(_handoff_to_B(), rs.agents["A"], rs, caused_by=seed)
    await spine.finalize("completed")
    assert ok is False and "handoff_not_in_org_topology" in _violations(rd)


async def test_handoff_blocked_by_recipient_acceptance(tmp_path) -> None:
    rd, spine = await _spine(tmp_path)
    rs = await _rs_two_agents(spine)
    rs.decision_rights = {"b": DecisionRights(may_accept_handoffs_from=("c",))}  # B accepts only c, not a
    seed = await spine.emit_event("turn.started", agent_id="A", turn_id="t")
    ok = await _route_handoff(_handoff_to_B(), rs.agents["A"], rs, caused_by=seed)
    await spine.finalize("completed")
    assert ok is False and "handoff_acceptance_denied" in _violations(rd)


async def test_handoff_allowed_when_no_structure_declared(tmp_path) -> None:
    rd, spine = await _spine(tmp_path)
    rs = await _rs_two_agents(spine)  # no topology, no decision_rights → permissive
    seed = await spine.emit_event("turn.started", agent_id="A", turn_id="t")
    ok = await _route_handoff(_handoff_to_B(), rs.agents["A"], rs, caused_by=seed)
    await spine.finalize("completed")
    assert ok is True and not _violations(rd)


# --- general messaging gated by comm-kind + topology (not just handoff) ----- #

async def test_send_blocked_by_comm_kind(tmp_path) -> None:
    from oaos2.kernel.runtime import _send_message
    rd, spine = await _spine(tmp_path)
    rs = await _rs_two_agents(spine)
    rs.comm_kinds = {"a": frozenset({"handoff"})}  # role a may send only handoffs, not messages
    seed = await spine.emit_event("turn.started", agent_id="A", turn_id="t")
    await _send_message(MessageIntent(to_agent="B", kind="message", payload="hi"),
                        rs.agents["A"], rs, caused_by=seed)
    await spine.finalize("completed")
    assert "comm_kind_not_permitted" in _violations(rd)
    assert "message.sent" not in [e["event_class"] for e in load_all_events(rd.root)]


async def test_broadcast_target_blocked_by_topology(tmp_path) -> None:
    from oaos2.kernel.runtime import _send_message
    rd, spine = await _spine(tmp_path)
    rs = await _rs_two_agents(spine)
    rs.topology = Topology(channels=(Channel("a", "c", frozenset({"message"})),))  # a→c only
    seed = await spine.emit_event("turn.started", agent_id="A", turn_id="t")
    await _send_message(MessageIntent(to_agent="B", kind="message", payload="hi"),
                        rs.agents["A"], rs, caused_by=seed)
    await spine.finalize("completed")
    blocked = [e for e in load_all_events(rd.root) if e["event_class"] == "relay.blocked"]
    assert blocked and blocked[0]["payload"].get("reason") == "not_in_org_topology"
