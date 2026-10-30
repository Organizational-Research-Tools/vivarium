"""M4 workspace/ACL/lineage tests, incl. the concurrent-capture gate (DESIGN §22)."""

from __future__ import annotations

import asyncio
import json
import os
import types

import pytest

from oaos2.agents.tools import ToolContext, dispatch_tool
from oaos2.kernel.run_dir import RunDir
from oaos2.trace.invariants import load_all_events
from oaos2.trace.retention import FileChangeFidelity, RetentionPolicy
from oaos2.trace.spine import RunSpine
from oaos2.workspace.acl import (
    AccessDenied,
    Enforcement,
    FileAccessPolicy,
    Zone,
    resolve_file_access_policy,
)
from oaos2.workspace.monitor import WorkspaceManager, canonical_real_path
from oaos2.workspace.zones import ZoneClass


async def _setup(tmp_path, artifact_zones=frozenset()):
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = RunSpine(rd.root, run_id="run1")
    await spine.start()
    wm = WorkspaceManager(rd, spine, artifact_zones=artifact_zones)
    return rd, spine, wm


def _classes(rd) -> list[str]:
    return [e["event_class"] for e in load_all_events(rd.root)]


async def test_private_write_captured(tmp_path) -> None:
    rd, spine, wm = await _setup(tmp_path)
    zone = Zone(name="scratch_a1", zone_class=ZoneClass.AGENT_WRITABLE.value, is_shared=False)
    tc = await spine.emit_event("tool.called", agent_id="a1", payload={"tool": "write"})
    fc = await wm.capture_write(
        agent_id="a1", path=rd.agent_scratch("a1") / "f.txt", new_bytes=b"hello",
        zone=zone, tool_call_event_id=tc,
    )
    await spine.finalize("completed")
    assert fc.operation == "create"
    assert fc.hash_after is not None
    assert "file.write" in _classes(rd)


async def test_concurrent_capture_gate(tmp_path) -> None:
    # The M4 concurrent-capture gate: 2+ agents writing concurrently — private
    # scratch (parallel) + a contended shared file — produce one coherent archive
    # of FileChange records: every write captured, the race recorded, none lost.
    rd, spine, wm = await _setup(tmp_path)
    shared = Zone(name="shared", zone_class=ZoneClass.AGENT_WRITABLE.value, is_shared=True)
    priv_a = Zone(name="scratch_a", zone_class=ZoneClass.AGENT_WRITABLE.value)
    priv_b = Zone(name="scratch_b", zone_class=ZoneClass.AGENT_WRITABLE.value)
    shared_file = rd.shared / "artifact.txt"

    tc_a = await spine.emit_event("tool.called", agent_id="a", payload={})
    tc_b = await spine.emit_event("tool.called", agent_id="b", payload={})
    tc_pa = await spine.emit_event("tool.called", agent_id="a", payload={})
    tc_pb = await spine.emit_event("tool.called", agent_id="b", payload={})

    # Two agents write the SAME shared file concurrently; two write their OWN scratch.
    results = await asyncio.gather(
        wm.capture_write(agent_id="a", path=shared_file, new_bytes=b"from-a",
                         zone=shared, tool_call_event_id=tc_a),
        wm.capture_write(agent_id="b", path=shared_file, new_bytes=b"from-b",
                         zone=shared, tool_call_event_id=tc_b),
        wm.capture_write(agent_id="a", path=rd.agent_scratch("a") / "p.txt", new_bytes=b"a-priv",
                         zone=priv_a, tool_call_event_id=tc_pa),
        wm.capture_write(agent_id="b", path=rd.agent_scratch("b") / "p.txt", new_bytes=b"b-priv",
                         zone=priv_b, tool_call_event_id=tc_pb),
    )
    report = await spine.finalize("completed")
    assert report.ok, report.failures  # one coherent, causally-consistent archive

    # All four writes captured as FileChange records (none lost).
    file_writes = [
        e for e in load_all_events(rd.root) if e["event_class"] in ("file.write", "file.edit")
    ]
    assert len(file_writes) == 4
    # The same-file race is recorded.
    assert "file.write_contended" in _classes(rd)
    # Last-writer-wins on disk, but BOTH shared writes are in the archive.
    shared_changes = [
        e["payload"]["file_change"] for e in file_writes
        if e["payload"]["file_change"]["zone"] == "shared"
    ]
    assert len(shared_changes) == 2
    assert {c["agent_id"] for c in shared_changes} == {"a", "b"}
    assert shared_file.read_bytes() in (b"from-a", b"from-b")


async def test_artifact_versioning_lineage(tmp_path) -> None:
    rd, spine, wm = await _setup(tmp_path, artifact_zones=frozenset({"shared"}))
    shared = Zone(name="shared", zone_class=ZoneClass.AGENT_WRITABLE.value, is_shared=True)
    f = rd.shared / "report.md"
    tc1 = await spine.emit_event("tool.called", agent_id="a", payload={})
    fc1 = await wm.capture_write(agent_id="a", path=f, new_bytes=b"v1", zone=shared, tool_call_event_id=tc1)
    tc2 = await spine.emit_event("tool.called", agent_id="a", payload={})
    fc2 = await wm.capture_write(agent_id="a", path=f, new_bytes=b"v2", zone=shared, tool_call_event_id=tc2)
    await spine.finalize("completed")
    assert fc1.artifact_version_id is not None
    assert fc2.artifact_version_id is not None
    versioned = [e for e in load_all_events(rd.root) if e["event_class"] == "artifact.versioned"]
    assert len(versioned) == 2
    # The second supersedes the first (a chain).
    assert versioned[1]["payload"]["supersedes"] == fc1.artifact_version_id


async def test_execute_scan_capture(tmp_path) -> None:
    rd, spine, wm = await _setup(tmp_path)
    zone = Zone(name="scratch_a", zone_class=ZoneClass.AGENT_WRITABLE.value)
    scratch = rd.ensure_agent_scratch("a")
    tc = await spine.emit_event("tool.called", agent_id="a", payload={"tool": "execute"})

    async def fake_execute():
        # Simulate a subprocess side effect inside the agent's private scratch.
        (scratch / "built.o").write_bytes(b"compiled output")

    changes = await wm.execute_with_capture(
        agent_id="a", scratch_root=scratch, run_execute=fake_execute,
        tool_call_event_id=tc, zone=zone,
    )
    await spine.finalize("completed")
    assert len(changes) == 1
    assert changes[0].operation == "create"
    assert changes[0].capture_source == "hash_scan"


def test_canonical_real_path_collapses_aliases(tmp_path) -> None:
    target = tmp_path / "real.txt"
    target.write_text("x")
    link = tmp_path / "alias.txt"
    link.symlink_to(target)
    # A symlink spelling and the dotted spelling resolve to the SAME lock key.
    assert canonical_real_path(link) == canonical_real_path(target)
    assert canonical_real_path(tmp_path / "./real.txt") == canonical_real_path(target)


def test_file_access_policy_fall_through_deny() -> None:
    pol = FileAccessPolicy(zones_writable=frozenset({"scratch"}))
    assert pol.may_write("scratch")
    assert not pol.may_write("shared")  # not granted → denied (fall_through)
    with pytest.raises(AccessDenied):
        pol.require_write("hidden")


def test_empty_grant_narrows_to_nothing() -> None:
    # An EXPLICIT empty grant at a tighter scope narrows to nothing (previously it
    # was treated as "no constraint" and the outer grant leaked through).
    org = FileAccessPolicy(zones_writable=frozenset({"scratch", "shared"}))
    agent = FileAccessPolicy(zones_writable=frozenset())  # explicitly grants no writable zone
    resolved = resolve_file_access_policy(org=org, role=None, agent=agent)
    assert resolved.zones_writable == frozenset()
    assert not resolved.may_write("scratch")


async def test_acl_denies_write_at_dispatch_with_tool_denied(tmp_path) -> None:
    """The software ACL is ENFORCED at tool dispatch (M4 §1, §8): a write to a
    zone the policy doesn't grant is refused and recorded as tool.denied, not a
    silent drop. Previously FileAccessPolicy was never consulted at dispatch."""
    rd, spine, wm = await _setup(tmp_path)
    rs = types.SimpleNamespace(spine=spine, workspace=wm)
    deny_pol = FileAccessPolicy(zones_writable=frozenset())  # grants no writable zone
    ctx = ToolContext(agent_id="a1", rs=rs, backend=None, handle=None, run_dir=rd,
                      coordinator=None, submit_commitment_id="c", file_access_policy=deny_pol)
    res = await dispatch_tool("write_file", {"path": "x.txt", "content": "hi"}, ctx,
                              turn_id="t", caused_by=None)
    await spine.finalize("completed")
    assert "denied" in res.text.lower()
    assert "tool.denied" in _classes(rd)
    # And the granted case is allowed through (no denial).
    rd2, spine2, wm2 = await _setup(tmp_path / "ok")
    rs2 = types.SimpleNamespace(spine=spine2, workspace=wm2)
    allow_pol = FileAccessPolicy(zones_writable=frozenset({"scratch_a1"}))
    ctx2 = ToolContext(agent_id="a1", rs=rs2, backend=None, handle=None, run_dir=rd2,
                       coordinator=None, submit_commitment_id="c", file_access_policy=allow_pol)
    res2 = await dispatch_tool("write_file", {"path": "x.txt", "content": "hi"}, ctx2,
                               turn_id="t", caused_by=None)
    await spine2.finalize("completed")
    assert "denied" not in res2.text.lower()
    assert "tool.denied" not in _classes(rd2)


async def test_reconcile_flags_unexplained_and_phantom_not_delete(tmp_path) -> None:
    rd, spine, wm = await _setup(tmp_path)
    scratch = rd.ensure_agent_scratch("a1")
    zone = Zone(name="scratch_a1", zone_class=ZoneClass.AGENT_WRITABLE.value)
    tc = await spine.emit_event("tool.called", agent_id="a1", payload={})
    await wm.capture_write(agent_id="a1", path=scratch / "kept.txt", new_bytes=b"x",
                           zone=zone, tool_call_event_id=tc)
    wm._captured[os.path.realpath(str(scratch / "gone.txt"))] = "delete"  # legitimately deleted
    wm._captured[os.path.realpath(str(scratch / "phantom.txt"))] = "create"  # claimed, never on disk
    (scratch / "sneaky.txt").write_bytes(b"!!")  # appeared on disk, never captured
    # A registered platform write (a committed submission payload) is
    # explained; an unregistered sibling still flags (audit 2026-09-03).
    platform = rd.container_mount / "submitted" / "choice_x.json"
    platform.parent.mkdir(parents=True, exist_ok=True)
    platform.write_text("{}")
    wm.record_platform_write(platform)
    mismatches = await wm.reconcile([rd.container_mount])
    assert not any(m["path"].endswith("choice_x.json") for m in mismatches)
    await spine.finalize("completed")
    causes = {m["cause"] for m in mismatches}
    assert "unexplained_change" in causes
    assert "phantom_write" in causes
    assert not any("gone.txt" in m["path"] for m in mismatches)  # delete is not a phantom


async def test_capture_move_emits_file_moved(tmp_path) -> None:
    rd, spine, wm = await _setup(tmp_path)
    scratch = rd.ensure_agent_scratch("a1")
    (scratch / "b.txt").write_bytes(b"data")  # the moved content is present at the destination
    zone = Zone(name="scratch_a1", zone_class=ZoneClass.AGENT_WRITABLE.value)
    tc = await spine.emit_event("tool.called", agent_id="a1", payload={})
    fc = await wm.capture_move(agent_id="a1", src=scratch / "a.txt", dst=scratch / "b.txt",
                               zone=zone, tool_call_event_id=tc)
    await spine.finalize("completed")
    assert fc.operation == "move"
    assert "file.moved" in _classes(rd)


async def test_confirmatory_full_patch_floor_for_outcome_zone(tmp_path) -> None:
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = RunSpine(rd.root, run_id="run1")
    await spine.start()
    ret = RetentionPolicy(file_changes=FileChangeFidelity.HASHES_ONLY)
    wm = WorkspaceManager(rd, spine, retention=ret, mode="confirmatory",
                          outcome_feeding_zones=frozenset({"results"}))
    zone = Zone(name="results", zone_class=ZoneClass.AGENT_WRITABLE.value)
    tc = await spine.emit_event("tool.called", agent_id="a1", payload={})
    fc = await wm.capture_write(agent_id="a1", path=rd.agent_scratch("a1") / "r.txt",
                                new_bytes=b"line\n", zone=zone, tool_call_event_id=tc)
    await spine.finalize("completed")
    # hashes_only would normally drop the patch; the confirmatory floor keeps it full.
    assert fc.patch_ref is not None


def test_file_access_policy_precedence_narrows() -> None:
    org = FileAccessPolicy(zones_writable=frozenset({"scratch", "shared"}))
    agent = FileAccessPolicy(zones_writable=frozenset({"scratch"}))  # narrows
    resolved = resolve_file_access_policy(org=org, role=None, agent=agent)
    assert resolved.zones_writable == frozenset({"scratch"})
    # forbidden is the union (a tighter scope may always forbid more).
    agent2 = FileAccessPolicy(zones_writable=frozenset({"scratch"}), forbidden=frozenset({"secret"}))
    resolved2 = resolve_file_access_policy(org=org, role=None, agent=agent2)
    assert "secret" in resolved2.forbidden
