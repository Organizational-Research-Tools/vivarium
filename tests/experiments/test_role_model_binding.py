"""Per-role model binding (Study C1h trigger): ``Role.model_ref`` is CONSUMED.

The runner binds each role to ``role.model_ref or <run model_ref>``, stamps the
effective map on every run (homogeneous included), certifies the realized
binding against the declared one from ``model.invoked``, demands capacity
evidence for the UNION of run-level and role-level refs, and the archive rows
keep the full model list beside the run-level primary. Offline only: stub
adapters + FakeContainerBackend — no Docker, no spend.
"""

from __future__ import annotations

import csv
import json
from types import SimpleNamespace

import pytest

from oaos2.archive import run_record, run_row, runs_to_csv
from oaos2.experiments.runner import (
    _adapter_from_factory,
    _launch_model_refs,
    _role_model_refs,
    run_org_live,
)
from oaos2.organizations.confound_check import ConfoundViolation
from oaos2.organizations.presets import pipeline
from oaos2.organizations.spec import OrganizationSpec, Role
from oaos2.trace.invariants import load_all_events
from tests.experiments.test_multi_agent_live import _FAKE_DIGEST, _HAVE_FAKE, _SubmitStubAdapter

pytestmark = pytest.mark.skipif(not _HAVE_FAKE, reason="FakeContainerBackend unavailable")

RUN_REF = "stub/deterministic"
X_REF = "openai/gpt-5"  # priced rows exist; the stub adapter never reaches a provider
S_REF = "anthropic/claude-sonnet-4-6"


def _two_role_spec(a_ref=None, b_ref=None) -> OrganizationSpec:
    return OrganizationSpec(preset_id="dyad", roles=[
        Role(role_id="office_b", attention="all", plays=["b"], specialized=True, model_ref=b_ref),
        Role(role_id="office_a", attention="all", plays=["a"], specialized=True, model_ref=a_ref),
    ])


# --- resolution rule + seams (pure) ---------------------------------------- #

def test_effective_ref_is_override_else_inheritance() -> None:
    refs = _role_model_refs(_two_role_spec(b_ref=X_REF), RUN_REF)
    assert refs == {"office_a": RUN_REF, "office_b": X_REF}
    assert list(refs) == sorted(refs)  # a pin: sorted keys, whatever the YAML order
    assert _role_model_refs(_two_role_spec(), RUN_REF) == {"office_a": RUN_REF, "office_b": RUN_REF}


def test_launch_refs_are_the_union_of_run_level_and_role_level() -> None:
    hetero = _two_role_spec(a_ref=S_REF, b_ref=X_REF)
    homo = _two_role_spec()
    assert _launch_model_refs((S_REF,), [hetero, homo]) == (S_REF, X_REF)
    assert _launch_model_refs((RUN_REF,), [hetero]) == (S_REF, X_REF, RUN_REF)
    assert _launch_model_refs((RUN_REF,), [homo]) == (RUN_REF,)


def test_adapter_factory_seam_passes_model_ref_only_when_declared() -> None:
    seen: list = []
    assert _adapter_from_factory(lambda: "bare", X_REF) == "bare"  # legacy factories untouched
    assert _adapter_from_factory(lambda model_ref: seen.append(model_ref) or "kw", X_REF) == "kw"
    assert _adapter_from_factory(lambda **kw: kw["model_ref"], X_REF) == X_REF

    class _Cls:
        def __init__(self, model_ref: str) -> None:
            self.model_ref = model_ref

    assert _adapter_from_factory(_Cls, S_REF).model_ref == S_REF
    assert _adapter_from_factory(_SubmitStubAdapter, S_REF).provider_id == "submit_stub"
    assert seen == [X_REF]


# --- live path (fake backend + stubs) --------------------------------------- #

class _RefStub(_SubmitStubAdapter):
    """A per-role stub that remembers which effective ref it was bound to and
    mimics that provider's reasoning SURFACE (what a mixed org realizes natively)."""

    bound: list = []
    SURFACE = {X_REF: "summary", S_REF: "thinking", RUN_REF: "none"}

    def __init__(self, model_ref: str) -> None:
        from dataclasses import replace
        super().__init__()
        self.model_ref = model_ref
        self.capabilities = replace(self.capabilities, reasoning_kind=self.SURFACE[model_ref])
        _RefStub.bound.append(model_ref)


async def _run(org, tmp_path, factory=_SubmitStubAdapter, reasoning_kind="none", **kw):
    from oaos2.docker.backend import FakeContainerBackend
    return await run_org_live(
        org, tmp_path, tier="hard", model_ref=RUN_REF, experiment_id="exp_c1h",
        reasoning_kind=reasoning_kind, cap_usd=5.0, max_model_calls=10,
        backend=FakeContainerBackend(digest=_FAKE_DIGEST), adapter_factory=factory, **kw)


def _pins(r) -> tuple[dict, dict, dict]:
    manifest = json.loads((r.run_dir / "manifest.json").read_text())
    status = json.loads((r.run_dir / "run_status.json").read_text())
    resolved = json.loads((r.run_dir / "config" / "resolved.json").read_text())
    return manifest["extensions"], status, resolved


async def test_homogeneous_run_is_stamped_too(tmp_path) -> None:
    r = await _run(pipeline(), tmp_path)
    assert r.closed and r.archive_valid
    expected = {"builder": RUN_REF, "reader": RUN_REF, "reviewer": RUN_REF}
    ext, status, resolved = _pins(r)
    assert ext["role_model_refs"] == expected and ext["model_heterogeneous"] is False
    assert ext["model_ref"] == RUN_REF  # run-level ref unchanged
    assert resolved["role_model_refs"] == expected and resolved["model_heterogeneous"] is False
    assert status["role_model_refs"] == expected and status["model_ref"] == RUN_REF
    assert r.role_model_refs == expected
    # Per-role realized partition of the ONE shared ledger (zero-priced stub). Keys
    # are the roles that actually invoked a model (the stub pipeline closes before
    # the reviewer ever calls), never padded with silent roles.
    invoked = {e["agent_id"] for e in load_all_events(r.run_dir)
               if e["event_class"] == "model.invoked"}
    assert {"reader", "builder"} <= invoked <= set(expected)
    assert set(status["cost_by_role"]) == invoked == set(status["output_tokens_by_role"])
    assert all(v == 0.0 for v in status["cost_by_role"].values())
    assert all(v > 0 for v in status["output_tokens_by_role"].values())
    # reasoning_kind="none" requested → realized "none" for every role, in manifest + status
    assert ext["realized_reasoning_kind"] == {r: "none" for r in expected}
    assert status["realized_reasoning_kind"] == ext["realized_reasoning_kind"]


async def test_heterogeneous_run_binds_certifies_and_partitions(tmp_path) -> None:
    org = pipeline()
    by_id = {role.role_id: role for role in org.roles}
    by_id["reader"].model_ref = S_REF
    by_id["builder"].model_ref = X_REF  # the reviewer inherits the run-level (stub) ref
    _RefStub.bound.clear()
    # ONE neutral "thinking" request; each provider realizes it on its own surface.
    r = await _run(org, tmp_path, factory=lambda model_ref: _RefStub(model_ref),
                   reasoning_kind="thinking")
    assert r.closed and r.archive_valid
    declared = {"builder": X_REF, "reader": S_REF, "reviewer": RUN_REF}
    assert sorted(_RefStub.bound) == sorted(declared.values())  # one stub per role, per ref
    ext, status, resolved = _pins(r)
    assert ext["role_model_refs"] == declared and ext["model_heterogeneous"] is True
    # Recorded per role, NOT equalized, and NOT the echoed request kind: the
    # summary-only provider is recorded as "summary", the no-reasoning stub as "none".
    assert ext["realized_reasoning_kind"] == {"builder": "summary", "reader": "thinking",
                                              "reviewer": "none"}
    assert status["realized_reasoning_kind"] == ext["realized_reasoning_kind"]
    assert not r.exposure_confounded  # nothing exposed to the agent → no confound stamp
    assert resolved["model_heterogeneous"] is True
    assert status["role_model_refs"] == declared and r.role_model_refs == declared
    assert ext["model_ref"] == RUN_REF and status["model_ref"] == RUN_REF
    # run_id keeps the single run-level ref (naming.py untouched): no role ref leaks in.
    assert "stub-deterministic" in r.run_dir.name and "openai" not in r.run_dir.name

    # The certificate's ground truth: every model.invoked carries the role's declared
    # ref (the stub pipeline closes before the reviewer calls, so it is absent).
    invoked: dict = {}
    for e in load_all_events(r.run_dir):
        if e["event_class"] == "model.invoked":
            invoked.setdefault(e["agent_id"], set()).add(e["payload"]["model_ref"])
    assert {"reader", "builder"} <= set(invoked)
    assert invoked == {k: {declared[k]} for k in invoked}
    invoked_refs = sorted({ref for refs in invoked.values() for ref in refs})

    # Per-role cost is separable from the spine: both priced roles cost, and the
    # partition sums to the ONE shared ledger.
    cost = status["cost_by_role"]
    assert set(cost) == set(invoked) and cost["reader"] > 0 and cost["builder"] > 0
    assert abs(sum(cost.values()) - r.cost_usd) < 1e-6
    assert set(status["output_tokens_by_role"]) == set(invoked)

    # Archive rows: run-level primary kept (from the manifest pin — the run-level ref
    # here never invoked at all), full invoked list + map preserved, deterministic.
    row = run_row(r.run_dir)
    assert row["model_ref"] == RUN_REF  # NOT whichever role happened to invoke first
    assert row["model_refs"] == invoked_refs == [S_REF, X_REF]
    assert row["role_model_refs"] == declared
    rec = run_record(r.run_dir)
    assert rec["model_ref"] == RUN_REF and rec["model_refs"] == invoked_refs
    assert rec["role_model_refs"] == declared
    csv_path = runs_to_csv([r.run_dir], tmp_path / "ds.csv")
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert json.loads(rows[0]["role_model_refs"]) == declared
    assert json.loads(rows[0]["model_refs"]) == invoked_refs
    assert rows[0]["model_ref"] == RUN_REF


async def test_certificate_mismatch_is_an_apparatus_fault(tmp_path, monkeypatch) -> None:
    """The runner routes a realized-vs-declared mismatch through the session: the
    cell raises ConfoundViolation and its spine ends 'failed', never 'completed'."""
    from importlib import import_module
    cc = import_module("oaos2.organizations.confound_check")  # the package attr is the function

    def _mismatch(events, declared):
        raise ConfoundViolation("role model binding mismatch (apparatus fault): forced")

    monkeypatch.setattr(cc, "certify_role_model_refs", _mismatch)
    with pytest.raises(ConfoundViolation, match="apparatus fault"):
        await _run(pipeline(), tmp_path)
    run_dirs = [p for p in (tmp_path / "exp_c1h").rglob("trace") if p.is_dir()]
    assert len(run_dirs) == 1
    classes = [e["event_class"] for e in load_all_events(run_dirs[0].parent)]
    assert "run.failed" in classes and "run.completed" not in classes
    assert not (run_dirs[0].parent / "run_status.json").exists()


# --- confirmatory readiness coverage ---------------------------------------- #

async def test_readiness_requires_evidence_for_every_role_level_ref(tmp_path, monkeypatch) -> None:
    """A confirmatory sweep launching a heterogeneous preset must hold capacity
    evidence for the role-level ref too — refused BEFORE any cell exists."""
    import hashlib

    from oaos2.experiments import runner as runner_mod
    from oaos2.experiments.confirmatory import ConfirmatoryReadinessError
    from oaos2.experiments.design import ExperimentDesign
    from oaos2.experiments.runner import run_sweep
    from tests.experiments.test_run_session import _calibration_archive

    prereg = tmp_path / "prereg.md"
    prereg.write_text("# Prereg\nSTATUS: FINAL\n")
    _calibration_archive(tmp_path / "batch" / "cell1", model_ref=S_REF, tier="hard",
                         task_pack="paper_replication")
    ev = tmp_path / "capacity.json"
    ev.write_text(json.dumps({
        "kind": "capacity_calibration", "task_pack": "paper_replication", "tier": "hard",
        "model_ref": S_REF, "capacity_established": True,
        "batch_ref": str(tmp_path / "batch")}))
    evidence = {"capacity_calibration": {
        "path": str(ev), "sha256": hashlib.sha256(ev.read_bytes()).hexdigest()}}
    hetero = _two_role_spec(a_ref=S_REF, b_ref=X_REF)
    hetero.preset_id = "dyad_hSX"
    monkeypatch.setattr(runner_mod, "_resolve_org", lambda pid: hetero)
    design = ExperimentDesign(
        name="c1h_readiness", task_pack="paper_replication", mode="confirmatory",
        factors={"org_preset": ["dyad_hSX"], "difficulty": ["hard"], "model": [S_REF]},
        preregistration_ref=str(prereg), confirmatory_evidence=evidence)
    with pytest.raises(ConfirmatoryReadinessError, match=r"openai/gpt-5.*hard") as excinfo:
        await run_sweep(design, tmp_path / "runs", execution="live", replications=1)
    assert "does not COVER the launch" in str(excinfo.value)
    assert not (tmp_path / "runs").exists()  # refused pre-launch: no cell, no archive

    # The per-cell backstop (a lone run_org_live cell) computes the same union.
    with pytest.raises(ConfirmatoryReadinessError, match="openai/gpt-5"):
        await run_org_live(hetero, tmp_path / "lone", tier="hard", model_ref=S_REF,
                           mode="confirmatory", preregistration_ref=str(prereg),
                           confirmatory_evidence=evidence, task_pack="paper_replication")


def test_readiness_backstop_sees_the_union_not_only_the_run_level_ref() -> None:
    # Pure composition check the two launch paths rely on: what will actually run.
    orgs = [SimpleNamespace(roles=[SimpleNamespace(model_ref=X_REF),
                                   SimpleNamespace(model_ref=None)])]
    assert _launch_model_refs((S_REF,), orgs) == (S_REF, X_REF)


def test_batch_linkage_backs_a_role_bound_model_only_when_that_role_spent() -> None:
    """C1h readiness: a gpt-5 office inside a Sonnet-factor calibration run backs
    gpt-5 evidence iff that role spent; an idle declared role does not; the
    run-level ref still backs on its own; pre-slice archives fall back to spend."""
    from oaos2.experiments.confirmatory import _status_backs_model
    het = {"model_ref": S_REF, "cost_usd": 1.0,
           "role_model_refs": {"office_a": S_REF, "office_b": X_REF},
           "cost_by_role": {"office_a": 0.6, "office_b": 0.4}}
    assert _status_backs_model(het, X_REF) and _status_backs_model(het, S_REF)
    idle = {**het, "cost_by_role": {"office_a": 1.0, "office_b": 0.0}}
    assert not _status_backs_model(idle, X_REF)
    assert not _status_backs_model(het, "anthropic/claude-haiku-4-5")
    legacy = {"model_ref": S_REF, "cost_usd": 1.0, "role_model_refs": {"r": X_REF}}
    assert _status_backs_model(legacy, X_REF)  # no partition: fall back to run spend
    assert not _status_backs_model({"model_ref": S_REF, "cost_usd": 1.0}, X_REF)
