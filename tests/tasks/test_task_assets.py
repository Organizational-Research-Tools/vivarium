"""Typed dependency-graph + rule-repertoire assets (platform_theory_audit.md §11.2–§11.3)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from oaos2.tasks.assets import (
    DependencyGraph,
    RuleRepertoire,
    TaskAssetError,
    load_dependency_graph,
    load_rule_repertoire,
    verify_graph_alignment,
    verify_rule_coverage,
)


def _graph(**overrides) -> dict:
    base = {
        "coupling_types": ["shared_vendor", "sequential_input"],
        "nodes": [
            {"node_id": "parks_maint", "scope": "office/parks"},
            {"node_id": "roads_paving", "scope": "office/roads"},
            {"node_id": "roads_signs", "scope": "office/roads"},
            {"node_id": "water_mains", "scope": "office/water"},
        ],
        "edges": [
            {"edge_id": "e1", "nodes": ["parks_maint", "roads_paving"],
             "coupling": "shared_vendor"},
            {"edge_id": "e2", "nodes": ["roads_paving", "water_mains"],
             "coupling": "sequential_input", "directed": True},
        ],
    }
    base.update(overrides)
    return base


def _repertoire() -> dict:
    return {"rules": [
        {"rule_id": "R1", "condition": "vendor cost rises under 10%",
         "response": "absorb within office contingency", "scopes": ["office/parks"],
         "changes_nodes": ["parks_maint"]},
        {"rule_id": "R2", "condition": "paving delayed one wave",
         "response": "reorder segments", "scopes": ["office/roads"]},
    ]}


# --- dependency graph ------------------------------------------------------- #

def test_graph_validates_and_answers_queries() -> None:
    graph = DependencyGraph.model_validate(_graph())
    assert graph.scopes() == ["office/parks", "office/roads", "office/water"]
    assert graph.nodes_in_scope("office/roads") == ["roads_paving", "roads_signs"]
    assert graph.owning_scopes(["parks_maint"]) == ["office/parks"]
    assert graph.coupled_nodes(["parks_maint"]) == ["roads_paving"]
    # the doc-06 manipulation-check primitive: jointly necessary scopes, 1-hop
    assert graph.affected_scopes(["parks_maint"]) == ["office/parks", "office/roads"]
    assert graph.affected_scopes(["roads_paving"]) == [
        "office/parks", "office/roads", "office/water"]
    with pytest.raises(TaskAssetError, match="unknown node"):
        graph.owning_scopes(["phantom"])


def test_graph_rejects_incoherence() -> None:
    bad_edge = _graph(edges=[{"edge_id": "e1", "nodes": ["parks_maint", "phantom"],
                              "coupling": "shared_vendor"}])
    with pytest.raises(ValidationError, match="unknown nodes"):
        DependencyGraph.model_validate(bad_edge)
    bad_coupling = _graph(edges=[{"edge_id": "e1", "nodes": ["parks_maint", "roads_paving"],
                                  "coupling": "reciprocal"}])
    with pytest.raises(ValidationError, match="not a declared coupling"):
        DependencyGraph.model_validate(bad_coupling)
    self_loop = _graph(edges=[{"edge_id": "e1", "nodes": ["parks_maint", "parks_maint"],
                               "coupling": "shared_vendor"}])
    with pytest.raises(ValidationError, match="distinct nodes"):
        DependencyGraph.model_validate(self_loop)
    duplicate = _graph(edges=[
        {"edge_id": "e1", "nodes": ["parks_maint", "roads_paving"], "coupling": "shared_vendor"},
        {"edge_id": "e2", "nodes": ["roads_paving", "parks_maint"], "coupling": "shared_vendor"},
    ])
    with pytest.raises(ValidationError, match="duplicates an existing edge"):
        DependencyGraph.model_validate(duplicate)


def test_directed_edges_distinguish_orientation() -> None:
    both = _graph(edges=[
        {"edge_id": "e1", "nodes": ["parks_maint", "roads_paving"],
         "coupling": "sequential_input", "directed": True},
        {"edge_id": "e2", "nodes": ["roads_paving", "parks_maint"],
         "coupling": "sequential_input", "directed": True},
    ])
    graph = DependencyGraph.model_validate(both)  # opposite directions are distinct
    assert len(graph.edges) == 2


# --- rule repertoire -------------------------------------------------------- #

def test_repertoire_validates_and_lists_ids() -> None:
    repertoire = RuleRepertoire.model_validate(_repertoire())
    assert repertoire.rule_ids() == ["R1", "R2"]
    assert RuleRepertoire.model_validate({"rules": []}).rule_ids() == []

    duplicated = {"rules": _repertoire()["rules"] * 2}
    with pytest.raises(ValidationError, match="unique"):
        RuleRepertoire.model_validate(duplicated)


# --- cross-checks (the mechanical WP1 gate) --------------------------------- #

_SCHEDULE = {"waves": [{
    "wave_id": "w1", "trigger_commitment_id": "initial_plan",
    "packets": [
        {"packet_id": "p1", "target_scopes": ["office/parks"], "payload": {"n": 1},
         "classification": {"rule_coverage": "rule_covered", "rule_ref": "R1",
                            "expected_scopes": ["office/parks"]}},
        {"packet_id": "p2", "target_scopes": ["office/roads"], "payload": {"n": 2},
         "classification": {"rule_coverage": "exception",
                            "expected_scopes": ["office/roads", "office/water"]}},
    ],
}]}


def test_rule_coverage_verified_mechanically() -> None:
    repertoire = RuleRepertoire.model_validate(_repertoire())
    assert verify_rule_coverage(repertoire, _SCHEDULE) == []
    # a covered packet citing a phantom rule is caught; unused rules are NOT flagged
    schedule = json.loads(json.dumps(_SCHEDULE))
    schedule["waves"][0]["packets"][0]["classification"]["rule_ref"] = "R99"
    problems = verify_rule_coverage(repertoire, schedule)
    assert problems and "R99" in problems[0]


def test_graph_alignment_catches_phantom_scopes_and_nodes() -> None:
    graph = DependencyGraph.model_validate(_graph())
    repertoire = RuleRepertoire.model_validate(_repertoire())
    assert verify_graph_alignment(graph, repertoire, _SCHEDULE) == []

    bad_rules = RuleRepertoire.model_validate({"rules": [
        {"rule_id": "R9", "condition": "c", "response": "r",
         "scopes": ["office/mars"], "changes_nodes": ["phantom"]}]})
    problems = verify_graph_alignment(graph, bad_rules)
    assert any("office/mars" in p for p in problems)
    assert any("phantom" in p for p in problems)

    schedule = json.loads(json.dumps(_SCHEDULE))
    schedule["waves"][0]["packets"][1]["classification"]["expected_scopes"] = ["office/mars"]
    problems2 = verify_graph_alignment(graph, repertoire, schedule)
    assert any("p2" in p and "office/mars" in p for p in problems2)


# --- file loading ----------------------------------------------------------- #

def test_load_helpers_fail_closed(tmp_path) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(_graph()))
    assert load_dependency_graph(graph_path).scopes()

    repertoire_path = tmp_path / "rules.json"
    repertoire_path.write_text(json.dumps(_repertoire()))
    assert load_rule_repertoire(repertoire_path).rule_ids() == ["R1", "R2"]

    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    with pytest.raises(TaskAssetError, match="cannot read"):
        load_dependency_graph(broken)
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"nodes": []}))
    with pytest.raises(TaskAssetError, match="invalid dependency graph"):
        load_dependency_graph(wrong)
