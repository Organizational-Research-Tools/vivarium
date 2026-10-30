"""Workbench data layer: library browse/validated-edit/launch records, annotation store."""

from __future__ import annotations

import json

import pytest

from oaos2.annotations.label_registry import LabelSchema
from oaos2.dashboard import annotate, workbench


@pytest.fixture
def tmp_library(tmp_path, monkeypatch):
    """A disposable library so edits never touch the real one."""
    lib = tmp_path / "library"
    (lib / "experiments").mkdir(parents=True)
    (lib / "organizations").mkdir()
    (lib / "tasks").mkdir()
    (lib / "experiments" / "tiny.yaml").write_text(
        "name: tiny\ntask_pack: paper_replication\nmode: pilot\nreplications: 1\n"
        "factors:\n  org_preset: [single_agent]\n  difficulty: [hard]\n"
        "  model: [anthropic/claude-haiku-4-5]\n"
        "unwired_knob: 1\n")
    (lib / "organizations" / "tiny_org.yaml").write_text(
        "preset_id: tiny_org\nscheduler: free\n"
        "roles:\n  - role_id: solo\n    plays: [solo]\n    decision_rights: {may_submit_milestones: false}\n"
        "topology: {}\n")
    monkeypatch.setenv("OAOS2_LIBRARY", str(lib))
    return lib


def test_list_library_resolves_and_reports_ignored_keys(tmp_library) -> None:
    lib = workbench.list_library()
    exp = {e["name"]: e for e in lib["experiments"]}["tiny"]
    assert exp["resolved"]["task_pack"] == "paper_replication"
    assert exp["ignored_keys"] == ["unwired_knob"]  # real text the engine never sees
    org = {o["name"]: o for o in lib["organizations"]}["tiny_org"]
    assert org["resolved"]["n_agents"] == 1
    assert org["ignored_keys"] == []
    assert org["resolved"]["topology"] == []  # empty declaration = complete graph
    assert org["resolved"]["roles"][0]["decision_rights"]["may_submit_milestones"] is False


def test_resolve_library_file_containment(tmp_library) -> None:
    assert workbench.resolve_library_file("experiments/tiny.yaml") is not None
    assert workbench.resolve_library_file("organizations/tiny_org.yaml") is not None
    assert workbench.resolve_library_file("../secrets.yaml") is None
    assert workbench.resolve_library_file("experiments/nope.yaml") is None
    # assets and hidden refs are NOT editable through the dashboard
    assert workbench.resolve_library_file("tasks/x/assets/hidden/key.json") is None


def test_save_validated_reverts_on_loader_rejection(tmp_library) -> None:
    path = tmp_library / "experiments" / "tiny.yaml"
    before = path.read_text()
    ok, msg = workbench.save_validated("experiments/tiny.yaml", "mode: [broken\n")
    assert not ok and "REVERTED" in msg
    assert path.read_text() == before  # byte-for-byte restore
    # a valid edit lands
    ok, msg = workbench.save_validated("experiments/tiny.yaml",
                                       before.replace("replications: 1", "replications: 2"))
    assert ok
    assert "replications: 2" in path.read_text()


def test_save_validated_rejects_confirmatory_without_prereg(tmp_library) -> None:
    path = tmp_library / "experiments" / "tiny.yaml"
    before = path.read_text()
    ok, msg = workbench.save_validated(
        "experiments/tiny.yaml", before.replace("mode: pilot", "mode: confirmatory"))
    assert not ok  # the loader's own confirmatory gate, inherited — not a dashboard rule
    assert path.read_text() == before


def test_launch_records_and_liveness(tmp_path) -> None:
    d = tmp_path / "runs" / ".dashboard" / "launches"
    d.mkdir(parents=True)
    (d / "x.json").write_text(json.dumps({"pid": 999999999, "design": "tiny",
                                          "execution": "offline", "started": "s",
                                          "log": str(d / "x.log")}))
    (d / "x.log").write_text("line1\nline2\n")
    launches = workbench.list_launches(tmp_path / "runs")
    assert len(launches) == 1
    assert launches[0]["alive"] is False  # that pid does not exist
    assert "line2" in launches[0]["log_tail"]


# --- annotation store --------------------------------------------------------- #

def test_schema_store_and_link_roundtrip(build_run) -> None:
    root = build_run.runs_root
    rd = build_run("r1")
    annotate.save_schema(root, LabelSchema(label_schema_ref="attn.v1", namespace="attention",
                                           arity="unary", description="what the agent attends to"))
    with pytest.raises(ValueError):
        annotate.save_schema(root, LabelSchema(label_schema_ref="attn.v1", namespace="attention",
                                               arity="unary"))
    events = __import__("oaos2.dashboard.events", fromlist=["load_events"]).load_events(rd)
    eid = events[0]["event_id"]
    link = annotate.write_link(root, rd, label_schema_ref="attn.v1", event_ids=[eid], note="hm")
    assert link.namespace == "attention" and link.label["coder"] == "human"
    assert (rd / "annotations" / "attention.jsonl").exists()
    assert annotate.links_by_event(rd)[eid][0]["label"]["note"] == "hm"
    # arity is enforced by the platform validator, not re-implemented here
    with pytest.raises(Exception):
        annotate.write_link(root, rd, label_schema_ref="attn.v1",
                            event_ids=[eid, events[1]["event_id"]])
    with pytest.raises(ValueError):
        annotate.write_link(root, rd, label_schema_ref="nope", event_ids=[eid])
