"""Runner support for models whose reasoning is set by an effort level (2026-10-03).

Claude Sonnet 5.5 refuses a thinking budget; it takes an effort level instead. The
runner sends each role's model the settings it accepts, refuses unusable ones before
anything is staged, records what each role was sent, and prices the run on a table that
has the model, while every setup without such a model keeps its fingerprint and pricing
identity. Offline only: stub adapters and the fake container backend, no spend.
"""

from __future__ import annotations

import json

import pytest

from oaos2.experiments.runner import (
    _adapter_for,
    _pricing_table_for,
    _research_setup_sha,
    _role_reasoning,
    run_org_live,
)
from oaos2.organizations.loader import load_org_spec
from oaos2.organizations.presets import pipeline
from oaos2.pricing.table import foundation_pricing_table
from tests.experiments.test_multi_agent_live import _FAKE_DIGEST, _HAVE_FAKE, _SubmitStubAdapter

E_REF = "anthropic/claude-sonnet-5-5"
S_REF = "anthropic/claude-sonnet-4-6"
RUN_REF = "stub/deterministic"


# --- per-role settings (pure) ----------------------------------------------- #

def test_effort_model_gets_effort_and_no_budget_budget_model_keeps_its_budget() -> None:
    refs = {"a": E_REF, "b": S_REF, "c": RUN_REF}
    got = _role_reasoning(refs, reasoning_kind="thinking", reasoning_budget=8000, effort="high")
    assert got == {
        "a": {"effort": "high", "reasoning_budget": None, "sampling": "provider_default"},
        "b": {"reasoning_budget": 8000},
        "c": {"reasoning_budget": 8000},
    }
    assert _role_reasoning({"b": S_REF}, reasoning_kind="none", reasoning_budget=8000,
                           effort=None) == {"b": {"reasoning_budget": None}}


@pytest.mark.parametrize("effort, match", [
    (None, "set effort explicitly"),
    ("xhigh", "high or below"),
    ("max", "high or below"),
    ("extreme", "effort must be one of"),
])
def test_unusable_effort_settings_are_refused(effort, match) -> None:
    with pytest.raises(ValueError, match=match):
        _role_reasoning({"a": E_REF}, reasoning_kind="thinking", reasoning_budget=8000, effort=effort)


def test_budget_models_ignore_effort() -> None:
    assert _role_reasoning({"b": S_REF}, reasoning_kind="thinking", reasoning_budget=8000,
                           effort="low") == {"b": {"reasoning_budget": 8000}}


def test_adapter_receives_the_effort() -> None:
    assert _adapter_for(E_REF, reasoning_kind="thinking", interleaved_thinking=True,
                        effort="medium").effort == "medium"


# --- pricing identity -------------------------------------------------------- #

def test_pricing_table_changes_only_when_a_model_needs_it() -> None:
    foundation = foundation_pricing_table()
    for refs in ([S_REF], [S_REF, "openai/gpt-5"], [RUN_REF], [RUN_REF, S_REF]):
        assert _pricing_table_for(refs).hash() == foundation.hash()
    newer = _pricing_table_for([S_REF, E_REF])
    assert newer.version != foundation.version
    assert E_REF in newer.rows and newer.rows[S_REF] == foundation.rows[S_REF]


# --- fingerprint ------------------------------------------------------------- #

def test_fingerprint_tracks_effort_only_where_a_role_takes_it(monkeypatch) -> None:
    from oaos2.tasks.loader import load_task_pack
    monkeypatch.setattr("oaos2.experiments.runner._source_state", lambda: {})
    pack = load_task_pack("budget_execution", profile="budget_vertical_v14_clocked")
    org = load_org_spec("budget_execution_summary_clocked")
    kw = dict(tier="unprogrammable", context_budget=None, cap_usd=8.0, cap_output_tokens=None,
              final_reserve_tokens=0, parity_basis="usd")
    budget_model = _research_setup_sha(pack, org, model_ref=S_REF, **kw)
    assert budget_model == _research_setup_sha(pack, org, model_ref=S_REF, effort="high", **kw)
    high = _research_setup_sha(pack, org, model_ref=E_REF, effort="high", **kw)
    assert high != _research_setup_sha(pack, org, model_ref=E_REF, effort="medium", **kw)
    assert high != budget_model


# --- live path (fake backend + stubs) --------------------------------------- #

class _RecordingStub(_SubmitStubAdapter):
    """Remembers the reasoning budget each request carried, by model."""

    seen: list = []

    def __init__(self, model_ref: str) -> None:
        super().__init__()
        self.model_ref = model_ref

    async def invoke(self, payload):
        if payload.reasoning.kind != "none" or payload.tools:
            _RecordingStub.seen.append((payload.model_ref, payload.reasoning.budget_tokens))
        return await super().invoke(payload)


async def test_live_refusal_happens_before_any_run_resource(tmp_path) -> None:
    root = tmp_path / "runs"
    with pytest.raises(ValueError, match="set effort explicitly"):
        await run_org_live(load_org_spec("single_agent"), root, tier="hard", model_ref=E_REF)
    with pytest.raises(ValueError, match="high or below"):
        await run_org_live(load_org_spec("single_agent"), root, tier="hard", model_ref=E_REF,
                           effort="xhigh")
    assert not root.exists()


@pytest.mark.skipif(not _HAVE_FAKE, reason="FakeContainerBackend unavailable")
async def test_mixed_run_sends_each_role_its_own_settings_and_records_them(tmp_path) -> None:
    from oaos2.docker.backend import FakeContainerBackend
    org = pipeline()
    by_id = {role.role_id: role for role in org.roles}
    by_id["reader"].model_ref = E_REF
    by_id["builder"].model_ref = S_REF
    _RecordingStub.seen.clear()
    r = await run_org_live(
        org, tmp_path, tier="hard", model_ref=RUN_REF, experiment_id="exp_effort",
        reasoning_kind="thinking", reasoning_budget=8000, effort="high", cap_usd=5.0,
        max_model_calls=10, backend=FakeContainerBackend(digest=_FAKE_DIGEST),
        adapter_factory=lambda model_ref: _RecordingStub(model_ref))
    assert r.closed and r.archive_valid
    budgets = {}
    for ref, budget in _RecordingStub.seen:
        budgets.setdefault(ref, set()).add(budget)
    assert budgets[E_REF] == {None} and budgets[S_REF] == {8000}

    manifest = json.loads((r.run_dir / "manifest.json").read_text())
    resolved = json.loads((r.run_dir / "config" / "resolved.json").read_text())
    ext = manifest["extensions"]
    assert ext["effort"] == "high"
    assert ext["role_reasoning"]["reader"] == {"effort": "high", "reasoning_budget": None,
                                               "sampling": "provider_default"}
    assert ext["role_reasoning"]["builder"] == {"reasoning_budget": 8000}
    assert resolved["role_reasoning"] == ext["role_reasoning"]
    assert manifest["pricing_table_version"] != foundation_pricing_table().version


@pytest.mark.skipif(not _HAVE_FAKE, reason="FakeContainerBackend unavailable")
async def test_run_without_effort_models_records_as_before(tmp_path) -> None:
    from oaos2.docker.backend import FakeContainerBackend
    r = await run_org_live(
        pipeline(), tmp_path, tier="hard", model_ref=RUN_REF, experiment_id="exp_effort",
        reasoning_kind="none", effort="high", cap_usd=5.0, max_model_calls=10,
        backend=FakeContainerBackend(digest=_FAKE_DIGEST), adapter_factory=_SubmitStubAdapter)
    manifest = json.loads((r.run_dir / "manifest.json").read_text())
    resolved = json.loads((r.run_dir / "config" / "resolved.json").read_text())
    assert "effort" not in manifest["extensions"] and "role_reasoning" not in manifest["extensions"]
    assert "effort" not in resolved
    assert manifest["pricing_table_version"] == foundation_pricing_table().version
