"""Tool-boundary path containment: agent-supplied paths cannot escape their zone.

Without this gate a crafted ``read_file``/``write_file`` path (``..`` segments,
absolute paths, or a symlink planted in scratch) reaches ``trace/events.jsonl``
(M1 single-writer spine), ``submitted/`` (M6 sole-committer via ``commit()``),
or the pack's hidden assets host-side. Escapes must be recorded ``tool.denied``
events — never a silent probe result and never a write.
"""

from __future__ import annotations

import os
import types

from oaos2.agents.tools import ToolContext, dispatch_tool
from oaos2.kernel.run_dir import RunDir
from oaos2.trace.invariants import load_all_events
from oaos2.trace.spine import RunSpine
from oaos2.workspace.monitor import WorkspaceManager


async def _setup(tmp_path):
    rd = RunDir.create(tmp_path / "runs", "e", "p", "run1")
    spine = RunSpine(rd.root, run_id="run1")
    await spine.start()
    wm = WorkspaceManager(rd, spine)
    rs = types.SimpleNamespace(spine=spine, workspace=wm)
    ctx = ToolContext(agent_id="a1", rs=rs, backend=None, handle=None, run_dir=rd,
                      coordinator=None, submit_commitment_id="c")
    return rd, spine, ctx


def _denials(rd) -> list[dict]:
    return [e["payload"] for e in load_all_events(rd.root) if e["event_class"] == "tool.denied"]


async def test_write_traversal_to_spine_denied(tmp_path) -> None:
    rd, spine, ctx = await _setup(tmp_path)
    events = rd.trace / "events.jsonl"
    before = events.read_bytes()
    rel = os.path.relpath(events, rd.agent_scratch("a1"))  # the exact ../ chain to the spine
    res = await dispatch_tool("write_file", {"path": rel, "content": "forged"}, ctx,
                              turn_id="t", caused_by=None)
    assert "denied" in res.text.lower()
    assert events.read_bytes()[: len(before)] == before  # spine bytes untouched
    await spine.finalize("completed")
    assert any(d.get("reason", "").startswith("path_escapes_zone") for d in _denials(rd))


async def test_write_absolute_path_to_submitted_denied(tmp_path) -> None:
    rd, spine, ctx = await _setup(tmp_path)
    forged = rd.submitted / "results.json"
    res = await dispatch_tool("write_file", {"path": str(forged), "content": "{}"}, ctx,
                              turn_id="t", caused_by=None)
    await spine.finalize("completed")
    assert "denied" in res.text.lower()
    assert not forged.exists()  # commit() stays the sole submitted/ writer


async def test_read_traversal_outside_zones_denied(tmp_path) -> None:
    rd, spine, ctx = await _setup(tmp_path)
    secret = tmp_path / "hidden_key.json"  # stands in for library/.../assets/hidden
    secret.write_text("answer")
    rel = os.path.relpath(secret, rd.visible)
    res = await dispatch_tool("read_file", {"path": rel}, ctx, turn_id="t", caused_by=None)
    await spine.finalize("completed")
    assert "denied" in res.text.lower()
    assert "answer" not in res.text


async def test_symlink_escape_from_scratch_denied(tmp_path) -> None:
    # A symlink planted in scratch (e.g. by sandboxed code) must not let a
    # host-side read/write follow it out of the zone.
    rd, spine, ctx = await _setup(tmp_path)
    secret = tmp_path / "outside.txt"
    secret.write_text("outside")
    scratch = rd.ensure_agent_scratch("a1")
    (scratch / "link.txt").symlink_to(secret)
    r = await dispatch_tool("read_file", {"path": "link.txt"}, ctx, turn_id="t", caused_by=None)
    w = await dispatch_tool("write_file", {"path": "link.txt", "content": "x"}, ctx,
                            turn_id="t", caused_by=None)
    await spine.finalize("completed")
    assert "denied" in r.text.lower()
    assert "denied" in w.text.lower()
    assert secret.read_text() == "outside"


async def test_contained_paths_still_work(tmp_path) -> None:
    rd, spine, ctx = await _setup(tmp_path)
    # Nested relative path, the container-absolute scratch spelling, and a
    # benign ".." that resolves back inside the zone all pass the gate.
    w1 = await dispatch_tool("write_file", {"path": "sub/dir/x.txt", "content": "hi"}, ctx,
                             turn_id="t", caused_by=None)
    w2 = await dispatch_tool("write_file", {"path": "/work/agents/a1/y.txt", "content": "yo"}, ctx,
                             turn_id="t", caused_by=None)
    r1 = await dispatch_tool("read_file", {"path": "sub/dir/../dir/x.txt"}, ctx,
                             turn_id="t", caused_by=None)
    await spine.finalize("completed")
    assert w1.text == "wrote sub/dir/x.txt"
    assert w2.text.startswith("wrote ")
    assert (rd.agent_scratch("a1") / "y.txt").read_text() == "yo"
    assert r1.text == "hi"
    assert not _denials(rd)
