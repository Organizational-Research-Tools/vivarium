"""Configurations are declarative DATA, loaded into the engine's own dataclasses
(DESIGN §5 config-over-code, §18, §19, §20, §23).

Two claims under test:

1. **Round-trip** — the committed ``library/`` YAML loads into the exact dataclasses
   the engine consumes (``TaskPack`` / ``OrganizationSpec`` / ``ExperimentDesign``),
   so the source of truth for *what an experiment is* is data, not code.

2. **Tool-buildability** — a brand-new experiment (new task pack + new org structure +
   new design) can be built by writing YAML into a library directory and running it
   end-to-end **with zero new Python**. A config-building tool that just emits these
   files is therefore sufficient. We point ``OAOS2_LIBRARY`` at a synthetic library and
   run the offline framework path against it.

(The offline stub solver + ``_score`` glue in ``runner.py`` remain paper-replication
specific; what this proves generic is the loader → dataclass → ``run_one`` path and the
evaluator registry resolving an id to a code plugin.)
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from oaos2.experiments.loader import available_designs, load_design
from oaos2.experiments.runner import run_one
from oaos2.organizations.loader import available_org_specs, load_org_spec
from oaos2.tasks.loader import load_task_pack


# --------------------------------------------------------------------------- #
# 1. Round-trip: the committed library loads into engine dataclasses
# --------------------------------------------------------------------------- #


def test_real_library_task_pack_round_trips() -> None:
    pack = load_task_pack("paper_replication", decomposed=True)
    assert pack.pack_id == "paper_replication"
    # Evaluator id resolved to a code plugin instance via the registry.
    assert "paper_replication.numeric_compare" in pack.evaluators
    # Decomposed profile → the three-commitment milestone graph.
    ids = {c.commitment_id for c in pack.outcome_contract.commitments}
    assert ids == {"spec_v1", "implementation_v1", "review_v1"}
    # The single-results profile drives the live submit commitment.
    assert pack.live_submit_commitment == "results"


def test_attention_scope_partitions_materials_per_role() -> None:
    # The decomposition is a real information PARTITION (DESIGN §18.1/§8), not just role
    # instructions: the pipeline builder is NOT given the paper (it works from the handoff
    # + data), while the reader/reviewer and the single-agent baseline are.
    pack = load_task_pack("paper_replication", decomposed=True)
    _, reader_user = pack.build_initial_prompt("hard", role="reader", attention="sample/spec")
    _, builder_user = pack.build_initial_prompt("hard", role="builder", attention="implementation")
    _, solo_user = pack.build_initial_prompt("hard", role="replicator", attention="all")
    assert len(reader_user) > 50_000 and len(solo_user) > 50_000  # full paper inlined
    assert len(builder_user) < 5_000                              # NO paper for the builder
    assert "you do not have the paper" in builder_user.lower()
    # An unlisted/`all` scope defaults to full (back-compat): a pack with no policy is unchanged.
    assert pack._materials_for_attention("hard", "all") == pack.tier_materials["hard"]

    # Required-output TEMPLATE is Condition-A/B gated (injection vs communication): the
    # single-agent/reader get the template; the pipeline builder does NOT (it learns what
    # to compute from the reader's handoff). Both the paper AND the template are partitioned.
    inj = "Submit a value for every result below"
    comm = "specified in the upstream handoff"
    assert inj in reader_user and inj in solo_user        # injection condition
    assert inj not in builder_user and comm in builder_user  # communication condition
    assert "sigma_alpha" not in builder_user              # no result names leak to the builder


def test_real_library_org_specs_round_trip() -> None:
    assert set(available_org_specs()) >= {
        "single_agent", "pipeline", "role_blind_ensemble", "context_expanded_single_agent"
    }
    pipeline = load_org_spec("pipeline")
    assert pipeline.preset_id == "pipeline"
    assert pipeline.n_agents == len(pipeline.roles) >= 2


def test_org_loader_round_trips_structure_controls(tmp_path, monkeypatch) -> None:
    lib = tmp_path / "library"
    orgs = lib / "organizations"
    orgs.mkdir(parents=True)
    (orgs / "strict.yaml").write_text(textwrap.dedent("""\
        preset_id: strict
        scheduler: sequential
        committer_binding: by_role
        tools: [read_file, submit_results]
        precedence_rules: {tools: [org, role]}
        topology:
          channels:
            - {from_role: worker, to_role: lead, kinds: [handoff]}
        roles:
          - role_id: worker
            plays: [worker]
            specialized: true
            tools: [read_file]
            comm_kinds: [handoff]
            decision_rights: {may_submit_milestones: false}
          - {role_id: lead, plays: [lead], specialized: false}
    """))
    monkeypatch.setenv("OAOS2_LIBRARY", str(lib))
    org = load_org_spec("strict")
    assert org.topology.allows("worker", "lead", "handoff")
    assert not org.topology.allows("lead", "worker", "handoff")
    assert org.roles[0].decision_rights.can_submit() is False
    assert org.roles[0].comm_kinds == frozenset({"handoff"})
    assert org.tools == frozenset({"read_file", "submit_results"})
    assert org.precedence_rules["tools"] == ("org", "role")


def test_real_library_design_round_trips() -> None:
    assert "first_experiment" in available_designs()
    d = load_design("first_experiment")
    assert d.task_pack == "paper_replication"
    assert d.mode == "confirmatory" and d.preregistration_ref
    assert d.parity_policy.cap_usd is None  # no design-declared cap → launcher decides


def test_design_declared_cap_round_trips() -> None:
    # The budget designs VERSION their cap (it sets the cost-pressure nudge threshold —
    # apparatus, not logistics; see the 2026-07-05 failure-tail autopsy).
    d = load_design("budget_calibration")
    assert d.parity_policy.cap_usd == 6.0


def test_draft_preregistration_is_barred_at_load(tmp_path) -> None:
    # Existence is not authorization: a confirmatory design pointing at a DRAFT
    # preregistration refuses at load. (The real budget_confirmatory froze
    # 2026-08-31, so the gate is covered by fixture; the frozen design's own
    # load is asserted below.)
    from oaos2.experiments.loader import validate_final_preregistration
    draft = tmp_path / "prereg.md"
    draft.write_text("# prereg\n\n> STATUS: DRAFT — NOT FINAL\n")
    with pytest.raises(ValueError, match="STATUS: FINAL"):
        validate_final_preregistration("prereg.md", root=tmp_path)


def test_frozen_confirmatory_design_loads_with_evidence_pair() -> None:
    # The FINAL freeze (2026-08-31): the design loads, carries the FORM ×
    # REQUIREMENT arms, the frozen brackets, and the typed evidence pair with
    # declared capacity roles. Loading is NOT launching — the live readiness
    # preflight and explicit PI authorization still gate any spend.
    d = load_design("budget_confirmatory")
    assert d.mode == "confirmatory" and d.task_pack == "budget_execution"
    assert d.replications == 8 and d.parity_policy.cap_usd == 8.0
    assert d.platform_seed == 20260910
    assert d.confirmatory_evidence["capacity_roles"] == {
        "unprogrammable": "premise", "programmable": "manipulation_check"}
    assert len(d.confirmatory_evidence["capacity_calibration"]) == 2


def test_token_matched_policy_requires_and_resolves_token_cap() -> None:
    from oaos2.experiments.design import ParityPolicy
    pp = ParityPolicy(basis="tokens", regime="budget_matched", cap_usd=10,
                      cap_tokens=50_000)
    assert pp.resolve_budgets(base_cap_usd=10) == [
        ("budget_matched", {"cap_usd": 10, "cap_output_tokens": 50_000,
                            "final_reserve_tokens": 20_000})]  # settlement reserve default


# --------------------------------------------------------------------------- #
# 2. Tool-buildability: a NEW experiment from YAML, zero new code
# --------------------------------------------------------------------------- #


def _write_synthetic_library(root: Path) -> None:
    """Emit a complete, novel experiment as pure data — exactly what a config tool would."""
    pack = root / "tasks" / "demo_survey"
    (pack / "assets" / "prompts").mkdir(parents=True)
    (pack / "assets" / "prompts" / "writer.md").write_text("You are the writer. Submit a summary.")
    # A new pack reusing the GENERIC schema_validator evaluator — no new scoring code.
    (pack / "manifest.yaml").write_text(textwrap.dedent("""\
        pack_id: demo_survey
        task_id: synthetic_demo
        science_image: oaos2-science:py311
        zones: {materials: task_visible, artifacts: agent_writable}
        prompts: {writer: writer.md}
        evaluators:
          schema_validator: {required: []}   # accepts any submission (buildability proof)
        public_feedback:
          schema_id: paper_replication_v1     # runner glue currently keys on this id
          allowed_fields: [passed, problem_count]   # the schema_validator's agent feedback
          forbidden_substrings: []
        contracts:
          decomposed:
            closure: all_required_committed
            commitments:
              - {id: summary_v1, kind: artifact_submission, required: true, committer_roles: [writer], evaluator: schema_validator}
          single_results:
            closure: all_required_committed
            commitments:
              - {id: summary_v1, kind: artifact_submission, required: true, committer_roles: [writer], evaluator: schema_validator}
        task_dimensions: {difficulty: easy}
    """))

    orgs = root / "organizations"
    orgs.mkdir(parents=True)
    # A new org structure (a single "writer" seat) — a new YAML, no code.
    (orgs / "demo_solo.yaml").write_text(textwrap.dedent("""\
        preset_id: demo_solo
        scheduler: free
        committer_binding: by_role
        roles:
          - {role_id: writer, attention: all, plays: [writer], specialized: true}
    """))

    exps = root / "experiments"
    exps.mkdir(parents=True)
    (exps / "demo_exp.yaml").write_text(textwrap.dedent("""\
        name: demo.synthetic_experiment
        task_pack: demo_survey
        factors: {org_preset: [demo_solo], difficulty: [easy]}
        replications: 1
        mode: pilot
        parity_policy: {basis: usd, regime: both}
        platform_seed: 7
    """))


async def test_new_experiment_built_from_yaml_runs_offline(tmp_path, monkeypatch) -> None:
    lib = tmp_path / "library"
    _write_synthetic_library(lib)
    monkeypatch.setenv("OAOS2_LIBRARY", str(lib))  # loaders resolve library_dir() at call time

    # Loaded purely from the YAML a tool emitted — no new Python anywhere.
    design = load_design("demo_exp")
    assert design.name == "demo.synthetic_experiment" and design.task_pack == "demo_survey"
    org = load_org_spec("demo_solo")
    pack = load_task_pack("demo_survey", decomposed=True)
    assert "schema_validator" in pack.evaluators  # id → code plugin, resolved by the registry

    # And it RUNS end-to-end offline: the org seat commits, the registry-resolved
    # evaluator scores it, the run closes and the archive validates.
    result = await run_one(pack, org, tmp_path / "runs", run_id="demo__easy__rep01",
                           experiment_id="demo_exp", mode="pilot")
    assert result.closed and result.archive_valid
    assert result.preset_id == "demo_solo" and result.n_agents == 1


def test_confirmatory_design_with_dangling_preregistration_fails_at_load(tmp_path, monkeypatch) -> None:
    # A confirmatory design must point at a preregistration that ACTUALLY EXISTS — a
    # dangling ref passes the dataclass check but leaves the claim unregistered (§19).
    lib = tmp_path / "library"
    (lib / "experiments").mkdir(parents=True)
    (lib / "experiments" / "bad.yaml").write_text(textwrap.dedent("""\
        name: bad.confirmatory
        task_pack: paper_replication
        mode: confirmatory
        preregistration_ref: library/experiments/does_not_exist.md
    """))
    monkeypatch.setenv("OAOS2_LIBRARY", str(lib))
    with pytest.raises(FileNotFoundError, match="preregistration_ref does not exist"):
        load_design("bad")


def test_confirmatory_design_with_existing_draft_preregistration_fails(tmp_path, monkeypatch) -> None:
    lib = tmp_path / "library"
    (lib / "experiments").mkdir(parents=True)
    (lib / "experiments" / "draft.md").write_text("# Prereg\n\n> STATUS: **DRAFT**\n")
    (lib / "experiments" / "bad.yaml").write_text(textwrap.dedent("""\
        name: bad.confirmatory
        task_pack: paper_replication
        mode: confirmatory
        preregistration_ref: library/experiments/draft.md
    """))
    monkeypatch.setenv("OAOS2_LIBRARY", str(lib))
    with pytest.raises(ValueError, match="STATUS: FINAL"):
        load_design("bad")


def test_unknown_evaluator_id_fails_loudly(tmp_path, monkeypatch) -> None:
    # A manifest that references an unregistered evaluator id must fail at load — the
    # one place a genuinely new scoring family needs a (registered) code plugin.
    # Two layers (probe 2026-08-17): a non-foundation id WITHOUT an
    # evaluator_modules declaration is refused at the manifest (process-global
    # registrations from other loads are not a declaration); with a declaration
    # whose modules still don't register the id, resolution fails loudly.
    from oaos2.tasks.loader import ManifestError
    from oaos2.tasks.registry import UnknownEvaluator

    lib = tmp_path / "library"
    pack = lib / "tasks" / "broken"
    (pack / "assets" / "prompts").mkdir(parents=True)
    manifest = textwrap.dedent("""\
        pack_id: broken
        task_id: x
        prompts: {}
        evaluators: {no_such_evaluator: {}}
        public_feedback: {schema_id: paper_replication_v1, allowed_fields: [], forbidden_substrings: []}
        contracts:
          decomposed: {closure: all_required_committed, commitments: [{id: a, committer_roles: [w], evaluator: no_such_evaluator}]}
          single_results: {closure: all_required_committed, commitments: [{id: a, committer_roles: [w], evaluator: no_such_evaluator}]}
    """)
    monkeypatch.setenv("OAOS2_LIBRARY", str(lib))

    (pack / "manifest.yaml").write_text(manifest)
    with pytest.raises(ManifestError, match="evaluator_modules"):
        load_task_pack("broken", decomposed=True)

    # With a declaration whose modules register OTHER ids, the unknown id is
    # refused on PROVENANCE (probe round 2): nothing this manifest declares
    # registered it. (UnknownEvaluator remains the direct-resolution error.)
    (pack / "manifest.yaml").write_text(
        "evaluator_modules: [tests.experiments.canary_evaluator_plugin]\n" + manifest)
    with pytest.raises(ManifestError, match="registered by"):
        load_task_pack("broken", decomposed=True)
    assert UnknownEvaluator is not None  # class stays the resolve-time error
