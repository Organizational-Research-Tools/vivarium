"""Archive read-side (DESIGN §17.3, §6.6): the four standard transcripts +
metrics + dataset export, rendered deterministically from the immutable trace."""

from __future__ import annotations

import json
from pathlib import Path

from oaos2.archive import (
    causal_ancestors,
    compute_metrics,
    file_lineage,
    render_archive,
    run_row,
    runs_to_csv,
    runs_to_jsonl,
)
from oaos2.kernel.run_dir import RunDir
from oaos2.trace.spine import RunSpine


async def _archive_with_events(tmp_path) -> RunDir:
    rd = RunDir.create(tmp_path, "exp1", "pack1", "run1")
    rd.manifest_path.write_text(json.dumps({
        "run_id": "run1", "experiment_id": "exp1", "task_pack_id": "pack1",
        "organization_id": "pipeline", "mode": "pilot", "pricing_table_version": "v1",
    }))
    spine = RunSpine(rd.root, run_id="run1")
    await spine.start()
    c = await spine.emit_event("run.started", payload={"run_id": "run1"})
    c = await spine.emit_event("turn.started", agent_id="A", turn_id="A.t1", caused_by=c,
                               audience="agent", channel="formal")
    c = await spine.emit_event("agent.observed", agent_id="A", turn_id="A.t1", caused_by=c,
                               audience="agent", payload={"observations": [{"kind": "task"}]})
    inv = await spine.emit_event("model.invoked", agent_id="A", turn_id="A.t1", caused_by=c,
                                 audience="researcher", payload={"model_ref": "stub/x"})
    c = await spine.emit_event("model.responded", agent_id="A", turn_id="A.t1", caused_by=inv,
                               audience="researcher",
                               payload={"stop_reason": "end_turn", "usage": {"input": 100, "output": 20}})
    c = await spine.emit_event("cost.recorded", agent_id="A", turn_id="A.t1", caused_by=c,
                               audience="infrastructure", channel="infrastructure",
                               payload={"cost_usd": 0.0123})
    c = await spine.emit_event("tool.called", agent_id="A", turn_id="A.t1", caused_by=c,
                               audience="agent", payload={"tool_name": "write_file"})
    c = await spine.emit_event("file.write", agent_id="A", turn_id="A.t1", caused_by=c,
                               audience="agent",
                               payload={"path": "scratch_A/out.py", "hash_before": "sha256:aaa",
                                        "hash_after": "sha256:bbb"})
    commit = await spine.emit_event("state.committed", agent_id="A", turn_id="A.t1", caused_by=c,
                                    audience="agent",
                                    payload={"state_commitment": {"commitment_id": "impl_v1"},
                                             "content_hash": "sha256:ccc"})
    await spine.emit_event("outcome.closed", caused_by=commit, audience="agent",
                           payload={"outcome_id": "main"})
    await spine.finalize("completed")
    return rd, commit


async def test_render_archive_produces_four_transcripts_and_metrics(tmp_path) -> None:
    rd, _ = await _archive_with_events(tmp_path)
    derived = render_archive(rd.root)
    for f in ("clean.txt", "full.txt", "agent_centric.txt", "file_lineage.txt", "metrics.json"):
        assert (derived / f).exists() and (derived / f).read_text(), f"missing/empty {f}"
    assert derived == rd.derived


async def test_render_is_deterministic(tmp_path) -> None:
    rd, _ = await _archive_with_events(tmp_path)
    first = {f.name: f.read_bytes() for f in render_archive(rd.root).iterdir()}
    second = {f.name: f.read_bytes() for f in render_archive(rd.root).iterdir()}
    assert first == second  # byte-identical re-render (no wall-clock in output)


async def test_clean_is_agent_audience_only(tmp_path) -> None:
    rd, _ = await _archive_with_events(tmp_path)
    derived = render_archive(rd.root)
    clean = (derived / "clean.txt").read_text()
    full = (derived / "full.txt").read_text()
    # cost.recorded is audience=infrastructure → in full, NOT in clean.
    assert "cost.recorded" in full and "cost.recorded" not in clean
    # the agent-facing commit IS in clean.
    assert "state.committed" in clean


async def test_clean_folds_verbatim_model_prose_from_raw(tmp_path) -> None:
    # A model.responded whose raw payload carries text → that prose appears in clean.
    rd = RunDir.create(tmp_path, "exp1", "pack1", "rprose")
    rd.manifest_path.write_text(json.dumps({"run_id": "rprose", "experiment_id": "exp1"}))
    from oaos2.models.raw_store import RawPayloadStore
    ref = RawPayloadStore(rd.root).put({"content": [{"type": "text", "text": "I will compute the SDs."}]})
    spine = RunSpine(rd.root, run_id="rprose")
    await spine.start()
    c = await spine.emit_event("turn.started", agent_id="A", turn_id="A.t1", audience="agent")
    await spine.emit_event("model.responded", agent_id="A", turn_id="A.t1", caused_by=c,
                           audience="researcher",
                           payload={"stop_reason": "end_turn", "usage": {"input": 5, "output": 5},
                                    "raw_provider_response_ref": ref})
    await spine.finalize("completed")
    clean = (render_archive(rd.root) / "clean.txt").read_text()
    assert 'says: "I will compute the SDs."' in clean


async def test_metrics_aggregate(tmp_path) -> None:
    rd, _ = await _archive_with_events(tmp_path)
    m = compute_metrics(rd.root)
    assert m["experiment_id"] == "exp1" and m["organization_id"] == "pipeline"
    assert m["n_model_calls"] == 1 and m["input_tokens"] == 100 and m["output_tokens"] == 20
    assert m["n_commitments"] == 1 and m["outcome_closed"] is True
    assert abs(m["total_cost_usd"] - 0.0123) < 1e-9
    assert m["model_refs"] == ["stub/x"]


async def test_file_lineage_and_causal_ancestors(tmp_path) -> None:
    rd, commit = await _archive_with_events(tmp_path)
    lineage = file_lineage(rd.root)
    assert "scratch_A/out.py" in lineage and len(lineage["scratch_A/out.py"]) == 1
    # the commit's causal ancestry reaches back to run.started (multi-parent walk).
    ancestors = causal_ancestors(rd.root, commit)
    assert len(ancestors) >= 5  # the whole causal chain before the commit


async def test_compute_metrics_tolerates_null_event_class(tmp_path) -> None:
    # A torn/partial event with event_class: null must not crash the registry (T1.4 regress).
    from oaos2.archive import compute_metrics
    rd = RunDir.create(tmp_path, "e", "p", "rnull")
    rd.manifest_path.write_text(json.dumps({"run_id": "rnull"}))
    spine = RunSpine(rd.root, run_id="rnull"); await spine.start()
    await spine.emit_event("run.started", payload={})
    await spine.finalize("completed")
    # Inject a malformed event line directly into the stream.
    ev = rd.root / "trace" / "events.jsonl"
    ev.write_text(ev.read_text() + json.dumps({"event_class": None, "sequence_number": 99}) + "\n")
    m = compute_metrics(rd.root)  # must not raise TypeError on None < str
    assert "?" in m["events_by_class"]


async def test_dataset_export_jsonl_and_csv(tmp_path) -> None:
    rd, _ = await _archive_with_events(tmp_path)
    row = run_row(rd.root)
    assert row["run_id"] == "run1" and row["n_commitments"] == 1 and row["model_ref"] == "stub/x"
    jsonl = runs_to_jsonl([rd.root], tmp_path / "ds.jsonl")
    lines = [json.loads(line) for line in jsonl.read_text().splitlines()]
    assert len(lines) == 1 and lines[0]["experiment_id"] == "exp1"
    csv_path = runs_to_csv([rd.root], tmp_path / "ds.csv")
    assert "run_id" in csv_path.read_text().splitlines()[0]  # header present
