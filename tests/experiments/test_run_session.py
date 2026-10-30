"""RunSession lifecycle gates: ordering is enforced, not stylistic.

The audit failure class these pin: a refused preflight must be UNABLE to have
staged anything; teardown covers exactly the registered set; the spine
finalizes exactly once on every path."""

from __future__ import annotations

import pytest

from oaos2.experiments.session import LifecycleError, RunSession


class _Spine:
    def __init__(self) -> None:
        self.finalized: list[str] = []

    async def finalize(self, status: str) -> str:
        self.finalized.append(status)
        return f"report:{status}"


def test_resources_refuse_to_attach_before_preflight() -> None:
    s = RunSession(rd=None, run_id="r")
    with pytest.raises(LifecycleError):
        s.attach_resources(spine=_Spine(), backend=None, policy=None)


def test_nothing_stages_in_preflight() -> None:
    s = RunSession(rd=None, run_id="r")
    with pytest.raises(LifecycleError):
        s.register_handle(object())


async def test_abort_before_resources_stages_and_finalizes_nothing() -> None:
    # A validation failure path: no spine, no containers — abort just raises.
    s = RunSession(rd=None, run_id="r")
    with pytest.raises(ValueError, match="preflight refused"):
        await s.abort(ValueError("preflight refused"))
    assert s.handles == [] and s.spine is None


async def test_finalize_exactly_once() -> None:
    s = RunSession(rd=None, run_id="r")
    s.preflight_ok()
    spine = _Spine()
    s.attach_resources(spine=spine, backend=None, policy=None)
    s.begin_execution()
    s.begin_winddown()
    assert await s.finalize("completed") == "report:completed"
    assert spine.finalized == ["completed"]
    with pytest.raises(LifecycleError):
        await s.finalize("completed")


async def test_abort_finalizes_failed_and_propagates() -> None:
    s = RunSession(rd=None, run_id="r")
    s.preflight_ok()
    spine = _Spine()
    s.attach_resources(spine=spine, backend=None, policy=None)
    with pytest.raises(RuntimeError, match="boom"):
        await s.abort(RuntimeError("boom"), teardown=False)
    assert spine.finalized == ["failed"]
    assert s.phase == "closed"


def test_lifecycle_never_moves_backwards() -> None:
    s = RunSession(rd=None, run_id="r")
    s.preflight_ok()
    s.attach_resources(spine=_Spine(), backend=None, policy=None)
    s.begin_execution()
    s.begin_winddown()
    with pytest.raises(LifecycleError):
        s.begin_execution()


def test_lifecycle_never_skips_a_phase() -> None:
    # Audit round 6 P1-2: skipping forward is as much a bug as moving back —
    # only abort() may jump (directly to closed, from any phase).
    s = RunSession(rd=None, run_id="r")
    s.preflight_ok()
    s.attach_resources(spine=_Spine(), backend=None, policy=None)
    with pytest.raises(LifecycleError):
        s.begin_winddown()  # resources -> winddown skips execution


def _calibration_archive(cell, *, model_ref, tier, cost=1.25,
                         task_pack="budget_execution",
                         terminal="run.completed", **status_over):
    """The minimal REAL-archive shape the linkage gate demands (2026-08-27
    hardening): valid+closed status, pack-attesting manifest, spine ending in
    a terminal — a bare three-field status is no longer an archive."""
    import json

    cell.mkdir(parents=True, exist_ok=True)
    status = {"model_ref": model_ref, "difficulty": tier, "cost_usd": cost,
              "archive_valid": True, "closed": True}
    status.update(status_over)
    (cell / "run_status.json").write_text(json.dumps(status))
    (cell / "manifest.json").write_text(json.dumps(
        {"task_pack_id": task_pack, "mode": "calibration",
         "extensions": {"research_setup_sha256": "sha256:" + "a" * 64}}))
    trace = cell / "trace"
    trace.mkdir(exist_ok=True)
    (trace / "events.jsonl").write_text(
        json.dumps({"event_class": "docker.launched"}) + "\n"
        + json.dumps({"event_class": terminal}) + "\n")
    return cell


async def test_confirmatory_readiness_gate_is_preflight(tmp_path) -> None:
    # Audit round 8 P1-4, hardened probe rounds 2026-08-17: readiness is typed
    # and fail-closed BEFORE any cell. Evidence is a HASH-PINNED artifact
    # LINKED to real live archives, COVERING every launched model×tier — a
    # hand-typed self-attested file, membership-of-one-among-many, and an
    # empty launch set all refuse.
    import hashlib
    import json
    from types import SimpleNamespace

    from oaos2.experiments.confirmatory import (
        ConfirmatoryReadinessError, assert_confirmatory_ready)

    prereg = tmp_path / "prereg.md"
    prereg.write_text("# Prereg\nSTATUS: FINAL\n")
    solo = SimpleNamespace(preset_id="solo", live_coordination={})
    organic = SimpleNamespace(preset_id="organic",
                              live_coordination={"mode": "deliberative"})
    MODEL, TIER = "anthropic/claude-sonnet-4-6", "unprogrammable"
    LAUNCH = dict(task_pack="budget_execution", model_refs=(MODEL,), tiers=(TIER,),
                  setup_sha256s=("sha256:" + "a" * 64,))

    def _pin(path):
        return {"path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    # A real (live-spend) calibration archive the evidence must link to —
    # full archive shape, not just a status file (2026-08-27 hardening).
    _calibration_archive(tmp_path / "batch" / "cell1",
                         model_ref=MODEL, tier=TIER)

    def _doc(path, **over):
        payload = {"kind": "capacity_calibration", "task_pack": "budget_execution",
                   "tier": TIER, "model_ref": MODEL, "capacity_established": True,
                   "batch_ref": str(tmp_path / "batch"),
                   "setup_sha256s": ["sha256:" + "a" * 64]}
        payload.update(over)
        path.write_text(json.dumps(payload))
        return path

    ev = _doc(tmp_path / "capacity.json")

    with pytest.raises(ConfirmatoryReadinessError, match="capacity evidence"):
        assert_confirmatory_ready(org_specs=[solo], evidence={},
                                  preregistration_ref=str(prereg), **LAUNCH)
    # A bare file path is no longer evidence — the probe's README.md hole.
    with pytest.raises(ConfirmatoryReadinessError, match="hash-pinned"):
        assert_confirmatory_ready(
            org_specs=[solo], evidence={"capacity_calibration": str(ev)},
            preregistration_ref=str(prereg), **LAUNCH)
    with pytest.raises(ConfirmatoryReadinessError, match="does not exist"):
        assert_confirmatory_ready(
            org_specs=[solo],
            evidence={"capacity_calibration": {
                "path": str(tmp_path / "missing.json"), "sha256": "0" * 64}},
            preregistration_ref=str(prereg), **LAUNCH)
    with pytest.raises(ConfirmatoryReadinessError, match="sha256"):
        assert_confirmatory_ready(
            org_specs=[solo],
            evidence={"capacity_calibration": {"path": str(ev), "sha256": "0" * 64}},
            preregistration_ref=str(prereg), **LAUNCH)
    # An arbitrary pinned file is still not evidence: the artifact is TYPED.
    readme = tmp_path / "README.md"
    readme.write_text("# not evidence\n")
    with pytest.raises(ConfirmatoryReadinessError, match="not a JSON artifact"):
        assert_confirmatory_ready(
            org_specs=[solo], evidence={"capacity_calibration": _pin(readme)},
            preregistration_ref=str(prereg), **LAUNCH)
    # An unsuccessful calibration is not evidence.
    bad = _doc(tmp_path / "failed.json", capacity_established=False)
    with pytest.raises(ConfirmatoryReadinessError, match="capacity_established"):
        assert_confirmatory_ready(
            org_specs=[solo], evidence={"capacity_calibration": _pin(bad)},
            preregistration_ref=str(prereg), **LAUNCH)
    # Estimand correction 2026-08-27 (+ external review finding 5): the LOW-
    # requirement tier's evidence attests the MIRROR verdict
    # (role=manipulation_check, capacity NOT exceeded), and the launch must
    # DECLARE which tier expects which verdict via capacity_roles. A two-tier
    # FORM × REQUIREMENT launch passes with the pair + the declaration...
    _calibration_archive(tmp_path / "low_batch" / "cell1",
                         model_ref=MODEL, tier="programmable")
    check = _doc(tmp_path / "check.json", tier="programmable",
                 role="manipulation_check", capacity_established=False,
                 batch_ref=str(tmp_path / "low_batch"))
    ROLES = {TIER: "premise", "programmable": "manipulation_check"}
    TWO_TIER = dict(preregistration_ref=str(prereg),
                    task_pack="budget_execution",
                    model_refs=(MODEL,), tiers=(TIER, "programmable"),
                    setup_sha256s=("sha256:" + "a" * 64,))
    assert_confirmatory_ready(
        org_specs=[solo],
        evidence={"capacity_calibration": [_pin(ev), _pin(check)],
                  "capacity_roles": ROLES}, **TWO_TIER)
    # ...without the declaration a manipulation_check doc refuses (the
    # inverted expectation is never inferred from the artifacts)...
    with pytest.raises(ConfirmatoryReadinessError, match="capacity_roles"):
        assert_confirmatory_ready(
            org_specs=[solo],
            evidence={"capacity_calibration": [_pin(ev), _pin(check)]},
            **TWO_TIER)
    # ...a PREMISE-labeled artifact cannot cover a tier the design declares
    # manipulation_check (the finding's exact hole)...
    prem_low = _doc(tmp_path / "prem_low.json", tier="programmable",
                    batch_ref=str(tmp_path / "low_batch"))
    with pytest.raises(ConfirmatoryReadinessError, match="do not match"):
        assert_confirmatory_ready(
            org_specs=[solo],
            evidence={"capacity_calibration": [_pin(ev), _pin(prem_low)],
                      "capacity_roles": ROLES}, **TWO_TIER)
    # ...a declaration that skips a launched tier refuses...
    with pytest.raises(ConfirmatoryReadinessError, match="no entry"):
        assert_confirmatory_ready(
            org_specs=[solo],
            evidence={"capacity_calibration": [_pin(ev), _pin(check)],
                      "capacity_roles": {TIER: "premise"}}, **TWO_TIER)
    # ...a manipulation check that found capacity BOUND is the halt-for-PI
    # condition, never launch evidence...
    bound_low = _doc(tmp_path / "bound_low.json", tier="programmable",
                     role="manipulation_check", capacity_established=True,
                     batch_ref=str(tmp_path / "low_batch"))
    with pytest.raises(ConfirmatoryReadinessError, match="halt for PI"):
        assert_confirmatory_ready(
            org_specs=[solo],
            evidence={"capacity_calibration": [_pin(ev), _pin(bound_low)],
                      "capacity_roles": ROLES}, **TWO_TIER)
    # ...and role is a closed registry.
    odd_role = _doc(tmp_path / "odd_role.json", role="vibes")
    with pytest.raises(ConfirmatoryReadinessError, match="unknown role"):
        assert_confirmatory_ready(
            org_specs=[solo], evidence={"capacity_calibration": _pin(odd_role)},
            preregistration_ref=str(prereg), **LAUNCH)
    # A self-attested doc with no resolvable batch linkage is not evidence.
    dangling = _doc(tmp_path / "dangling.json", batch_ref=str(tmp_path / "nope"))
    with pytest.raises(ConfirmatoryReadinessError, match="batch_ref"):
        assert_confirmatory_ready(
            org_specs=[solo], evidence={"capacity_calibration": _pin(dangling)},
            preregistration_ref=str(prereg), **LAUNCH)
    # A batch of ZERO-COST (stub) archives is not live calibration backing.
    _calibration_archive(tmp_path / "stub_batch" / "cell1",
                         model_ref=MODEL, tier=TIER, cost=0.0)
    stubbed = _doc(tmp_path / "stubbed.json", batch_ref=str(tmp_path / "stub_batch"))
    with pytest.raises(ConfirmatoryReadinessError, match="nonzero spend"):
        assert_confirmatory_ready(
            org_specs=[solo], evidence={"capacity_calibration": _pin(stubbed)},
            preregistration_ref=str(prereg), **LAUNCH)
    # 2026-08-27 hardening canaries: authenticity is the ARCHIVE, not the
    # status fields. A hand-typed three-field run_status.json — the exact
    # shape that passed before — now refuses, as does each missing credential.
    bare = tmp_path / "bare_batch" / "cell1"
    bare.mkdir(parents=True)
    (bare / "run_status.json").write_text(json.dumps(
        {"model_ref": MODEL, "difficulty": TIER, "cost_usd": 1.25}))
    with pytest.raises(ConfirmatoryReadinessError, match="archive_valid is not true"):
        assert_confirmatory_ready(
            org_specs=[solo],
            evidence={"capacity_calibration": _pin(_doc(
                tmp_path / "bare.json", batch_ref=str(tmp_path / "bare_batch")))},
            preregistration_ref=str(prereg), **LAUNCH)
    _calibration_archive(tmp_path / "open_batch" / "cell1",
                         model_ref=MODEL, tier=TIER, closed=False)
    with pytest.raises(ConfirmatoryReadinessError, match="run_status.closed"):
        assert_confirmatory_ready(
            org_specs=[solo],
            evidence={"capacity_calibration": _pin(_doc(
                tmp_path / "open.json", batch_ref=str(tmp_path / "open_batch")))},
            preregistration_ref=str(prereg), **LAUNCH)
    cell = _calibration_archive(tmp_path / "unmanifested" / "cell1",
                                model_ref=MODEL, tier=TIER)
    (cell / "manifest.json").unlink()
    with pytest.raises(ConfirmatoryReadinessError, match="no readable manifest.json"):
        assert_confirmatory_ready(
            org_specs=[solo],
            evidence={"capacity_calibration": _pin(_doc(
                tmp_path / "unman.json", batch_ref=str(tmp_path / "unmanifested")))},
            preregistration_ref=str(prereg), **LAUNCH)
    _calibration_archive(tmp_path / "borrowed" / "cell1", model_ref=MODEL,
                         tier=TIER, task_pack="paper_replication")
    with pytest.raises(ConfirmatoryReadinessError, match="task_pack_id"):
        assert_confirmatory_ready(
            org_specs=[solo],
            evidence={"capacity_calibration": _pin(_doc(
                tmp_path / "borrowed.json", batch_ref=str(tmp_path / "borrowed")))},
            preregistration_ref=str(prereg), **LAUNCH)
    _calibration_archive(tmp_path / "crashed" / "cell1", model_ref=MODEL,
                         tier=TIER, terminal="run.failed")
    with pytest.raises(ConfirmatoryReadinessError, match="cannot back"):
        assert_confirmatory_ready(
            org_specs=[solo],
            evidence={"capacity_calibration": _pin(_doc(
                tmp_path / "crashed.json", batch_ref=str(tmp_path / "crashed")))},
            preregistration_ref=str(prereg), **LAUNCH)
    # Evidence must match the launch's pack and COVER every model×tier.
    with pytest.raises(ConfirmatoryReadinessError, match="does not transfer across packs"):
        assert_confirmatory_ready(
            org_specs=[solo], evidence={"capacity_calibration": _pin(ev)},
            preregistration_ref=str(prereg), task_pack="paper_replication",
            model_refs=(MODEL,), tiers=(TIER,))
    with pytest.raises(ConfirmatoryReadinessError, match="COVER"):
        assert_confirmatory_ready(
            org_specs=[solo], evidence={"capacity_calibration": _pin(ev)},
            preregistration_ref=str(prereg), task_pack="budget_execution",
            model_refs=(MODEL, "anthropic/claude-opus-5"), tiers=(TIER,))
    # An empty launch set is a gate error, never a silent match skip.
    with pytest.raises(ConfirmatoryReadinessError, match="cannot determine"):
        assert_confirmatory_ready(
            org_specs=[solo], evidence={"capacity_calibration": _pin(ev)},
            preregistration_ref=str(prereg), task_pack="budget_execution")
    with pytest.raises(ConfirmatoryReadinessError, match="DEFERRED"):
        assert_confirmatory_ready(
            org_specs=[solo, organic],
            evidence={"capacity_calibration": _pin(ev)},
            preregistration_ref=str(prereg), **LAUNCH)
    # Fully ready: FINAL prereg + linked, covering evidence + no deferred arms.
    assert_confirmatory_ready(
        org_specs=[solo], evidence={"capacity_calibration": _pin(ev)},
        preregistration_ref=str(prereg), **LAUNCH)


async def test_confirmatory_run_refuses_injected_fakes(tmp_path) -> None:
    # Probe 2026-08-17: a confirmatory cell must run the real substrate — a
    # FakeContainerBackend or stub adapter_factory would stamp runtime=raw_api
    # on fabricated evidence. Refused at preflight, before any resource exists.
    import hashlib
    import json

    from oaos2.docker.backend import FakeContainerBackend
    from oaos2.experiments.runner import run_org_live
    from oaos2.organizations.presets import single_agent

    prereg = tmp_path / "prereg.md"
    prereg.write_text("# Prereg\nSTATUS: FINAL\n")
    _calibration_archive(tmp_path / "batch" / "cell1",
                         model_ref="anthropic/claude-sonnet-4-6", tier="hard",
                         cost=2.5, task_pack="paper_replication")
    ev = tmp_path / "capacity.json"
    ev.write_text(json.dumps({
        "kind": "capacity_calibration", "task_pack": "paper_replication",
        "tier": "hard", "model_ref": "anthropic/claude-sonnet-4-6",
        "capacity_established": True, "batch_ref": str(tmp_path / "batch"),
                   "setup_sha256s": ["sha256:" + "a" * 64]}))
    evidence = {"capacity_calibration": {
        "path": str(ev), "sha256": hashlib.sha256(ev.read_bytes()).hexdigest()}}

    with pytest.raises(ValueError, match="injected backends"):
        await run_org_live(single_agent(), tmp_path, tier="hard",
                           mode="confirmatory", experiment_id="exp_conf",
                           preregistration_ref=str(prereg),
                           confirmatory_evidence=evidence,
                           backend=FakeContainerBackend(digest="sha256:fake"))


def test_unknown_provider_namespaces_fail_closed() -> None:
    # Audit round 8 P2-6: a typo'd or unprefixed model_ref must refuse, never
    # silently resolve to the calibration provider.
    from oaos2.experiments.runner import _adapter_for

    for bad in ("typo/model", "bare-model-name"):
        with pytest.raises(ValueError, match="provider namespace"):
            _adapter_for(bad, reasoning_kind="none", interleaved_thinking=False)


def test_routing_stage_registry_shape_fails_closed() -> None:
    # Audit round 8 P2-5: a bare-string registry passed membership by
    # SUBSTRING ("port" in "report"); shape is validated now.
    from oaos2.tasks.loader import ManifestError, _routing

    slot = {"id": "s", "routing": {"stage": "port", "office": "economy"}}
    with pytest.raises(ManifestError, match="nonempty list of unique"):
        _routing(slot, "report")  # bare string registry
    with pytest.raises(ManifestError, match="nonempty list of unique"):
        _routing(slot, ["report", "report"])  # duplicates
    with pytest.raises(ManifestError, match="not in the manifest"):
        _routing(slot, ["report", "comment"])  # unknown stage, proper registry
