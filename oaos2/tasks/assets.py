"""Validate declared task dependency graphs and rule collections.

Task files define nodes, scopes, coupling names, and rule content. These classes
check their shapes and cross-references, including whether scheduled classifications
cite known rules and whether those rules refer to declared graph elements.
A successful check establishes consistency of the declarations, not that an
exception is substantively genuine or a rule sufficient; those need task review."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class TaskAssetError(ValueError):
    """A typed task asset is malformed or its cross-references do not hold."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _nonempty(name: str, value: str) -> str:
    value = str(value).strip()
    if not value:
        raise ValueError(f"{name} must be nonempty")
    return value


# --------------------------------------------------------------------------- #
# Dependency graph (§11.2)
# --------------------------------------------------------------------------- #


class DependencyNode(StrictModel):
    node_id: str  # participant vocabulary (a program/module id), not a platform ULID
    scope: str    # the attention scope that owns/observes this node
    label: str | None = None

    @field_validator("node_id", "scope")
    @classmethod
    def clean(cls, value: str) -> str:
        return _nonempty("node field", value)


class DependencyEdge(StrictModel):
    edge_id: str
    nodes: tuple[str, str]
    coupling: str          # must be one of the graph's declared coupling_types
    directed: bool = False

    @field_validator("edge_id", "coupling")
    @classmethod
    def clean(cls, value: str) -> str:
        return _nonempty("edge field", value)

    @model_validator(mode="after")
    def distinct_endpoints(self):
        if self.nodes[0] == self.nodes[1]:
            raise ValueError("an edge must join two distinct nodes")
        return self


class DependencyGraph(StrictModel):
    """The task's coupling structure.  The coupling vocabulary is declared IN the
    asset — pooled/sequential/reciprocal or anything else a design needs."""

    schema_version: Literal[1] = 1
    coupling_types: list[str] = Field(min_length=1)
    nodes: list[DependencyNode] = Field(min_length=1)
    edges: list[DependencyEdge] = Field(default_factory=list)

    @field_validator("coupling_types")
    @classmethod
    def unique_couplings(cls, value: list[str]) -> list[str]:
        cleaned = [_nonempty("coupling_types entry", v) for v in value]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("coupling_types must be unique")
        return cleaned

    @model_validator(mode="after")
    def coherent(self):
        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("node_id values must be unique")
        known = set(node_ids)
        edge_ids: set[str] = set()
        seen_pairs: set[tuple] = set()
        for edge in self.edges:
            if edge.edge_id in edge_ids:
                raise ValueError(f"duplicate edge_id {edge.edge_id!r}")
            edge_ids.add(edge.edge_id)
            unknown = [n for n in edge.nodes if n not in known]
            if unknown:
                raise ValueError(f"edge {edge.edge_id!r} references unknown nodes {unknown}")
            if edge.coupling not in self.coupling_types:
                raise ValueError(
                    f"edge {edge.edge_id!r} coupling {edge.coupling!r} is not a declared "
                    "coupling type")
            pair = tuple(edge.nodes) if edge.directed else tuple(sorted(edge.nodes))
            key = (pair, edge.coupling, edge.directed)
            if key in seen_pairs:
                raise ValueError(f"edge {edge.edge_id!r} duplicates an existing edge")
            seen_pairs.add(key)
        return self

    # -- mechanical queries (used by materials review, evaluators, projections) --

    def scopes(self) -> list[str]:
        return sorted({node.scope for node in self.nodes})

    def nodes_in_scope(self, scope: str) -> list[str]:
        return sorted(node.node_id for node in self.nodes if node.scope == scope)

    def owning_scopes(self, node_ids) -> list[str]:
        wanted = set(node_ids)
        unknown = wanted - {node.node_id for node in self.nodes}
        if unknown:
            raise TaskAssetError(f"unknown node ids {sorted(unknown)}")
        return sorted({node.scope for node in self.nodes if node.node_id in wanted})

    def coupled_nodes(self, node_ids) -> list[str]:
        """Nodes sharing an edge with any named node (1-hop, excluding the inputs)."""
        wanted = set(node_ids)
        touched: set[str] = set()
        for edge in self.edges:
            ends = set(edge.nodes)
            if ends & wanted:
                touched |= ends
        return sorted(touched - wanted)

    def affected_scopes(self, node_ids) -> list[str]:
        """Scopes owning the named nodes or any 1-hop coupled node — the mechanical
        'whose information is jointly necessary' primitive (doc 06 manipulation check)."""
        wanted = set(node_ids)
        return sorted(set(self.owning_scopes(wanted))
                      | set(self.owning_scopes(self.coupled_nodes(wanted))))


# --------------------------------------------------------------------------- #
# Rule repertoire (§11.3)
# --------------------------------------------------------------------------- #


class ContingencyRule(StrictModel):
    """One ex ante programmed response.  Both task conditions carry the SAME
    repertoire; what the manipulation varies is whether realized events are
    covered by it (doc 06 §Factor 1)."""

    rule_id: str
    condition: str  # participant-facing trigger description
    response: str   # the programmed local response
    scopes: list[str] = Field(min_length=1)  # who may apply it locally
    changes_nodes: list[str] | None = None   # legal local repair surface, if bounded

    @field_validator("rule_id", "condition", "response")
    @classmethod
    def clean(cls, value: str) -> str:
        return _nonempty("rule field", value)

    @field_validator("scopes")
    @classmethod
    def clean_scopes(cls, value: list[str]) -> list[str]:
        cleaned = [_nonempty("scopes entry", v) for v in value]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("scopes must be unique")
        return cleaned

    @field_validator("changes_nodes")
    @classmethod
    def clean_changes(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [_nonempty("changes_nodes entry", v) for v in value]
        if not cleaned or len(cleaned) != len(set(cleaned)):
            raise ValueError("changes_nodes must be nonempty and unique when present")
        return cleaned


class RuleRepertoire(StrictModel):
    schema_version: Literal[1] = 1
    rules: list[ContingencyRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_rule_ids(self):
        ids = [rule.rule_id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("rule_id values must be unique")
        return self

    def rule_ids(self) -> list[str]:
        return sorted(rule.rule_id for rule in self.rules)


# --------------------------------------------------------------------------- #
# Loading + mechanical cross-checks
# --------------------------------------------------------------------------- #


def _load(model, path: Path | str, what: str):
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise TaskAssetError(f"cannot read {what} at {path}: {exc}") from exc
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise TaskAssetError(f"invalid {what} at {path}: {exc}") from exc


def load_dependency_graph(path: Path | str) -> DependencyGraph:
    return _load(DependencyGraph, path, "dependency graph")


def load_rule_repertoire(path: Path | str) -> RuleRepertoire:
    return _load(RuleRepertoire, path, "rule repertoire")


def verify_rule_coverage(repertoire: RuleRepertoire, schedule: dict) -> list[str]:
    """The WP1 gate, mechanical: every packet the schedule classifies as
    rule_covered must cite a rule that exists in the repertoire.

    A rule with no realized event is NOT a problem — the unprogrammable schedule
    deliberately realizes events its (identical) repertoire does not cover.
    """
    known = set(repertoire.rule_ids())
    problems: list[str] = []
    for wave in schedule.get("waves") or []:
        for packet in wave.get("packets") or []:
            classification = packet.get("classification")
            if not isinstance(classification, dict):
                continue
            if classification.get("rule_coverage") != "rule_covered":
                continue
            rule_ref = classification.get("rule_ref")
            if rule_ref not in known:
                problems.append(
                    f"packet {packet.get('packet_id')!r} is rule_covered by "
                    f"{rule_ref!r}, which is not in the repertoire")
    return problems


def verify_matched_shells(schedule_a: dict, schedule_b: dict) -> list[str]:
    """The matched-magnitude audit (INSTRUMENT_DESIGN.md §5), mechanical.

    Both schedules must realize the same EVENT multiset per wave INDEX: same
    effective shell ids, and per effective id the same (type, TOTAL
    magnitude).  How a shell is realized (covered vs exception, which
    packets) is exactly what may differ — including (materials v13, review
    2026-08-27 blocker 2) one tier realizing a shell as SUB-SHELLS
    (``parent_shell_id``): two locally-coverable events whose magnitudes sum
    to the parent's and whose type matches, so only the join requirement
    separates the tiers.
    """
    problems: list[str] = []

    def shells_by_wave(schedule: dict, name: str) -> list[dict[str, tuple]]:
        waves = []
        for wave in schedule.get("waves") or []:
            shells: dict[str, tuple] = {}   # sub-shell id -> (parent, type, magnitude)
            for packet in wave.get("packets") or []:
                shell = (packet.get("classification") or {}).get("shell")
                if not isinstance(shell, dict):
                    problems.append(
                        f"{name} wave {wave.get('wave_id')!r} packet "
                        f"{packet.get('packet_id')!r} declares no shell")
                    continue
                key = str(shell.get("shell_id"))
                parent = str(shell.get("parent_shell_id") or key)
                value = (parent, str(shell.get("type")),
                         float(shell.get("magnitude")))
                if shells.setdefault(key, value) != value:
                    problems.append(
                        f"{name} wave {wave.get('wave_id')!r} shell {key!r} is "
                        "declared with inconsistent parent/type/magnitude")
            # Aggregate to effective events: total magnitude per parent id,
            # one consistent type. A parent id may not also stand alone.
            merged: dict[str, tuple] = {}
            for key, (parent, type_, magnitude) in sorted(shells.items()):
                if parent != key and parent in shells:
                    problems.append(
                        f"{name} wave {wave.get('wave_id')!r}: parent shell "
                        f"{parent!r} also appears as a bare shell id")
                if parent in merged:
                    prior_type, prior_total = merged[parent]
                    if prior_type != type_:
                        problems.append(
                            f"{name} wave {wave.get('wave_id')!r} parent "
                            f"{parent!r}: sub-shells disagree on type")
                    merged[parent] = (prior_type, prior_total + magnitude)
                else:
                    merged[parent] = (type_, magnitude)
            waves.append(merged)
        return waves

    waves_a = shells_by_wave(schedule_a, "schedule_a")
    waves_b = shells_by_wave(schedule_b, "schedule_b")
    if len(waves_a) != len(waves_b):
        problems.append(f"wave counts differ: {len(waves_a)} vs {len(waves_b)}")
    for index, (shells_a, shells_b) in enumerate(zip(waves_a, waves_b)):
        if set(shells_a) != set(shells_b):
            problems.append(
                f"wave index {index}: shell ids differ "
                f"({sorted(set(shells_a) ^ set(shells_b))})")
            continue
        for shell_id in sorted(shells_a):
            if shells_a[shell_id] != shells_b[shell_id]:
                problems.append(
                    f"wave index {index} shell {shell_id!r}: type/magnitude differ "
                    f"{shells_a[shell_id]} vs {shells_b[shell_id]}")
    return problems


def verify_graph_alignment(graph: DependencyGraph, repertoire: RuleRepertoire,
                           schedule: dict | None = None) -> list[str]:
    """Rules (and, if given, schedule classifications) must name scopes and nodes
    the graph actually declares — no phantom repair surfaces."""
    scopes = set(graph.scopes())
    node_ids = {node.node_id for node in graph.nodes}
    problems: list[str] = []
    for rule in repertoire.rules:
        bad_scopes = sorted(set(rule.scopes) - scopes)
        if bad_scopes:
            problems.append(f"rule {rule.rule_id!r} names unknown scopes {bad_scopes}")
        if rule.changes_nodes:
            bad_nodes = sorted(set(rule.changes_nodes) - node_ids)
            if bad_nodes:
                problems.append(f"rule {rule.rule_id!r} changes unknown nodes {bad_nodes}")
    for wave in (schedule or {}).get("waves") or []:
        for packet in wave.get("packets") or []:
            classification = packet.get("classification")
            if not isinstance(classification, dict):
                continue
            expected = classification.get("expected_scopes")
            bad = sorted(set(expected or []) - scopes)
            if bad:
                problems.append(
                    f"packet {packet.get('packet_id')!r} expects unknown scopes {bad}")
    return problems
