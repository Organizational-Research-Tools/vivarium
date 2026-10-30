"""Open-registry canaries for the four remaining register-don't-edit seams
(structural audit 2026-08-17): pack-composed trace vocabulary injected into
``RunSpine``/``Router``, scheduler policies, evaluator builders, and provider
namespaces. Each canary proves EXTENSION BY REGISTRATION — novel vocabulary
lands via config + a plugin, zero core edits — and that unregistered vocabulary
still fails closed. The coordination-mode analogue is
``test_coordination_protocol_canary.py``."""

from __future__ import annotations

import importlib
import json
import textwrap

import pytest

from oaos2.communication.messages import COMM_KIND_REGISTRY
from oaos2.organizations.loader import load_org_spec
from oaos2.organizations.scheduler import (
    register_scheduler_policy,
    resolve_scheduler_policy,
)
from oaos2.tasks.loader import ManifestError, load_task_pack
from oaos2.trace.emit import ProtocolViolation, make_event
from oaos2.trace.spine import RunSpine


# --------------------------------------------------------------------------- #
# 1. Pack-composed trace vocabulary → RunSpine / Router
# --------------------------------------------------------------------------- #


def _write_vocab_pack(root, extra_manifest: str = "") -> None:
    pack = root / "tasks" / "vocab_canary"
    (pack / "assets" / "prompts").mkdir(parents=True)
    (pack / "assets" / "prompts" / "writer.md").write_text("Submit a summary.")
    (pack / "manifest.yaml").write_text(textwrap.dedent("""\
        pack_id: vocab_canary
        task_id: vocab_canary
        science_image: oaos2-science:py311
        zones: {materials: task_visible, artifacts: agent_writable}
        prompts: {writer: writer.md}
        evaluators:
          schema_validator: {required: []}
        public_feedback:
          schema_id: paper_replication_v1
          allowed_fields: [passed, problem_count]
          forbidden_substrings: []
        contracts:
          single_results:
            closure: all_required_committed
            commitments:
              - {id: summary_v1, kind: artifact_submission, required: true, committer_roles: [writer], evaluator: schema_validator}
        task_dimensions: {difficulty: easy}
        trace_vocabulary:
          event_classes:
            canary.case_ping: {phase_class: execution, audience: researcher, channel: formal, emitted_by: canary}
          phase_names:
            canary_triage: execution
          comm_kinds:
            canary_petition: request
    """) + textwrap.dedent(extra_manifest))


async def test_pack_vocabulary_composes_into_spine_and_router(tmp_path, monkeypatch) -> None:
    lib = tmp_path / "library"
    _write_vocab_pack(lib)
    monkeypatch.setenv("OAOS2_LIBRARY", str(lib))
    pack = load_task_pack("vocab_canary", profile="single_results")

    # The loader COMPOSED (not replaced): foundation + novel entries coexist.
    assert "canary.case_ping" in pack.event_class_registry
    assert "run.started" in pack.event_class_registry
    assert "canary_triage" in pack.phase_name_registry
    assert "canary_petition" in pack.comm_kind_registry
    assert pack.comm_kind_registry["canary_petition"] == "request"
    # The foundation registries themselves were NEVER edited.
    assert "canary_petition" not in COMM_KIND_REGISTRY

    # A spine built the runner's way accepts the novel class end-to-end…
    spine = RunSpine(tmp_path / "run", run_id="vocab1",
                     event_class_registry=pack.event_class_registry,
                     phase_name_registry=pack.phase_name_registry)
    await spine.start()
    await spine.emit_event("run.started", payload={})
    eid = await spine.emit_event("canary.case_ping", phase_name="canary_triage",
                                 payload={"case": "c1"})
    report = await spine.finalize("completed")
    assert report.ok
    lines = [json.loads(l) for l in
             ((tmp_path / "run" / "trace" / "events.jsonl").read_text().splitlines())]
    novel = [e for e in lines if e["event_class"] == "canary.case_ping"]
    assert novel and novel[0]["event_id"] == eid
    assert novel[0]["phase_name"] == "canary_triage"

    # …while the FOUNDATION registry still refuses it (fail-closed, no leak).
    with pytest.raises(ProtocolViolation, match="canary.case_ping"):
        make_event("canary.case_ping", "vocab1")


def test_vocabulary_collision_with_foundation_fails_at_load(tmp_path, monkeypatch) -> None:
    # Shadowing a foundation event class is a naming bug, not an extension.
    lib = tmp_path / "library"
    _write_vocab_pack(lib)
    manifest = lib / "tasks" / "vocab_canary" / "manifest.yaml"
    manifest.write_text(manifest.read_text().replace(
        "canary.case_ping:", "run.started:"))
    monkeypatch.setenv("OAOS2_LIBRARY", str(lib))
    with pytest.raises(ManifestError, match="redefines inherited entry"):
        load_task_pack("vocab_canary", profile="single_results")


def test_vocabulary_bad_values_fail_at_load(tmp_path, monkeypatch) -> None:
    lib = tmp_path / "library"
    _write_vocab_pack(lib)
    manifest = lib / "tasks" / "vocab_canary" / "manifest.yaml"
    manifest.write_text(manifest.read_text().replace(
        "canary_petition: request", "canary_petition: broadcastish"))
    monkeypatch.setenv("OAOS2_LIBRARY", str(lib))
    with pytest.raises(ManifestError, match="primitive 'broadcastish'"):
        load_task_pack("vocab_canary", profile="single_results")


def test_vocabulary_unknown_section_fails_at_load(tmp_path, monkeypatch) -> None:
    lib = tmp_path / "library"
    _write_vocab_pack(lib, extra_manifest="""\
    """)
    manifest = lib / "tasks" / "vocab_canary" / "manifest.yaml"
    manifest.write_text(manifest.read_text().replace(
        "  comm_kinds:", "  zone_classes: {x: y}\n  comm_kinds:"))
    monkeypatch.setenv("OAOS2_LIBRARY", str(lib))
    with pytest.raises(ManifestError, match="unknown sections"):
        load_task_pack("vocab_canary", profile="single_results")


# --------------------------------------------------------------------------- #
# 2. Scheduler policies — plugin registers via org-declared scheduler_module
# --------------------------------------------------------------------------- #


def test_scheduler_plugin_registers_via_org_yaml(tmp_path, monkeypatch) -> None:
    orgs = tmp_path / "library" / "organizations"
    orgs.mkdir(parents=True)
    (orgs / "canary_sched_org.yaml").write_text(textwrap.dedent("""\
        preset_id: canary_sched_org
        scheduler: canary_last_idle
        scheduler_module: tests.experiments.canary_scheduler_policy
        roles:
          - {role_id: writer, attention: all, plays: [writer], specialized: true}
    """))
    monkeypatch.setenv("OAOS2_LIBRARY", str(tmp_path / "library"))
    org = load_org_spec("canary_sched_org")  # import side effect registers the policy
    policy = resolve_scheduler_policy(org.scheduler)

    class _Snap:
        idle_agents = ["a", "b", "c"]
        all_agent_order = ["a", "b", "c"]

    assert policy(_Snap()) == {"c"}  # provably the plugin's behavior, no built-in's


def test_unknown_scheduler_policy_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown scheduler policy 'no_such'"):
        resolve_scheduler_policy("no_such")


def test_conflicting_scheduler_registration_refused() -> None:
    from tests.experiments.canary_scheduler_policy import canary_last_idle_policy
    register_scheduler_policy("canary_last_idle", canary_last_idle_policy)  # idempotent
    with pytest.raises(ValueError, match="already registered"):
        register_scheduler_policy("canary_last_idle", lambda snap: set())


# --------------------------------------------------------------------------- #
# 3. Evaluators — plugin registers via manifest-declared evaluator_modules
# --------------------------------------------------------------------------- #


def test_evaluator_plugin_registers_via_manifest(tmp_path, monkeypatch) -> None:
    lib = tmp_path / "library"
    _write_vocab_pack(lib)
    manifest = lib / "tasks" / "vocab_canary" / "manifest.yaml"
    manifest.write_text(manifest.read_text().replace(
        "evaluators:\n  schema_validator: {required: []}",
        "evaluator_modules: [tests.experiments.canary_evaluator_plugin]\n"
        "evaluators:\n  canary.score: {required: []}"))
    monkeypatch.setenv("OAOS2_LIBRARY", str(lib))
    pack = load_task_pack("vocab_canary", profile="single_results")
    assert "canary.score" in pack.evaluators  # registered by the plugin import, resolved by id


def test_conflicting_evaluator_registration_refused() -> None:
    from oaos2.tasks.registry import register_evaluator
    from tests.experiments.canary_evaluator_plugin import build_canary_evaluator
    register_evaluator("canary.score", build_canary_evaluator)  # idempotent
    with pytest.raises(ValueError, match="already registered"):
        register_evaluator("canary.score", lambda spec: object())


# --------------------------------------------------------------------------- #
# 4. Provider namespaces — register, resolve, fail closed
# --------------------------------------------------------------------------- #


class _CanaryAdapter:
    @classmethod
    def for_reasoning(cls, *, reasoning_kind, interleaved_thinking):
        return cls()


def _load_canary_adapter() -> type:
    return _CanaryAdapter


def test_provider_namespace_registers_and_resolves() -> None:
    from oaos2.experiments.runner import _adapter_for
    from oaos2.models.adapters import register_provider_adapter
    register_provider_adapter("canary_prov", _load_canary_adapter)
    adapter = _adapter_for("canary_prov/model-x", reasoning_kind="none",
                           interleaved_thinking=False)
    assert isinstance(adapter, _CanaryAdapter)  # dispatched to the registered plugin


def test_unknown_provider_namespace_still_fails_closed() -> None:
    from oaos2.experiments.runner import _adapter_for
    with pytest.raises(ValueError, match="unknown provider namespace 'typo'"):
        _adapter_for("typo/model", reasoning_kind="none", interleaved_thinking=False)
    with pytest.raises(ValueError, match="provider namespace"):
        _adapter_for("no_slash_model", reasoning_kind="none", interleaved_thinking=False)


def test_conflicting_provider_registration_refused() -> None:
    from oaos2.models.adapters import register_provider_adapter
    register_provider_adapter("canary_prov", _load_canary_adapter)  # idempotent
    with pytest.raises(ValueError, match="already registered"):
        register_provider_adapter("canary_prov", lambda: object())


# --------------------------------------------------------------------------- #
# 5. Provenance, not presence (probe round 2): a bogus declared module cannot
#    launder another config's earlier registration; unowned gate keys fail at
#    LOAD, not mid-run.
# --------------------------------------------------------------------------- #


def test_bogus_evaluator_module_cannot_launder_leaked_id(tmp_path, monkeypatch) -> None:
    importlib.import_module("tests.experiments.canary_evaluator_plugin")  # leak canary.score globally
    from oaos2.tasks.loader import ManifestError

    lib = tmp_path / "library"
    _write_vocab_pack(lib)
    manifest = lib / "tasks" / "vocab_canary" / "manifest.yaml"
    manifest.write_text(manifest.read_text().replace(
        "evaluators:\n  schema_validator: {required: []}",
        "evaluator_modules: [json]\n"  # imports fine, registers NOTHING
        "evaluators:\n  canary.score: {required: []}"))
    monkeypatch.setenv("OAOS2_LIBRARY", str(lib))
    with pytest.raises(ManifestError, match="registered by"):
        load_task_pack("vocab_canary", profile="single_results")


def test_bogus_scheduler_module_cannot_launder_leaked_policy(tmp_path, monkeypatch) -> None:
    importlib.import_module("tests.experiments.canary_scheduler_policy")  # leak the policy globally

    orgs = tmp_path / "library" / "organizations"
    orgs.mkdir(parents=True)
    (orgs / "laundered.yaml").write_text(textwrap.dedent("""\
        preset_id: laundered
        scheduler: canary_last_idle
        scheduler_module: json
        roles:
          - {role_id: writer, attention: all, plays: [writer], specialized: true}
    """))
    monkeypatch.setenv("OAOS2_LIBRARY", str(tmp_path / "library"))
    with pytest.raises(ValueError, match="not registered by this org"):
        load_org_spec("laundered")


def test_bogus_protocol_module_cannot_launder_leaked_mode() -> None:
    importlib.import_module("tests.experiments.canary_relay_protocol")  # leak relay_ring globally
    from types import SimpleNamespace

    from oaos2.experiments.coordination import resolve_coordination_protocol

    org = SimpleNamespace(live_coordination={"mode": "relay_ring",
                                             "protocol_module": "json"},
                          roles=[], committer_binding="by_role")
    with pytest.raises(ValueError, match="not registered by this org's declared"):
        resolve_coordination_protocol(org)
    # The honest declaration still resolves (repeated loads stay valid).
    org_ok = SimpleNamespace(
        live_coordination={"mode": "relay_ring",
                           "protocol_module": "tests.experiments.canary_relay_protocol"},
        roles=[], committer_binding="by_role")
    assert resolve_coordination_protocol(org_ok).mode == "relay_ring"


def test_unowned_submission_gate_key_fails_at_load(tmp_path, monkeypatch) -> None:
    # A typo'd/unowned gate key must fail when the manifest LOADS — not burn a
    # live cell at the first submit (probe round 2 findings 4+5). Cross-pack
    # borrowing is judged by provenance, so pre-loading another pack's gates
    # does not rescue an undeclared key.
    importlib.import_module("oaos2.tasks.plugins.budget_execution.submission_gates")  # leak gates
    from oaos2.tasks.loader import ManifestError

    lib = tmp_path / "library"
    _write_vocab_pack(lib)
    manifest = lib / "tasks" / "vocab_canary" / "manifest.yaml"
    manifest.write_text(manifest.read_text().replace(
        "evaluator: schema_validator}",  # give the commitment an unowned gate key
        "evaluator: schema_validator, submission: {case_disposition: {v: 1}}}"))
    monkeypatch.setenv("OAOS2_LIBRARY", str(lib))
    with pytest.raises(ManifestError, match="nothing would enforce them"):
        load_task_pack("vocab_canary", profile="single_results")
