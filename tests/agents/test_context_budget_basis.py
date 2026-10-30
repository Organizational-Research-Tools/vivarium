"""The context budget in reported tokens (PC1 x6, October 15, 2026). The x5 audit found the local estimator counting
OpenAI's encrypted reasoning as text, so the same nominal budget gave models very different real contexts. With
`context_budget_basis: reported` the threshold is the budget in the provider's reported input tokens, converted to
estimator units by the agent's own ratio on its latest call. Scripted laboratories and a fake sandbox; no model."""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

from oaos2.agents.model_agent import effective_context_budget, reported_per_estimated
from oaos2.docker.backend import FakeContainerBackend
from oaos2.experiments.runner import run_org_live
from oaos2.models.adapters.base import estimate_input_tokens_chars
from oaos2.models.types import NeutralBlock, NeutralMessage, TokenSplit
from oaos2.organizations.loader import load_org_spec
from oaos2.trace.invariants import load_all_events
from tests.tasks.test_materials_lab_pack import _ReactiveStub, _tool
from tests.scripted_stub import _FAKE_DIGEST


def _req(chars):
    return SimpleNamespace(messages=[NeutralMessage("user", [NeutralBlock(kind="text", text="x" * chars)])], tools=[])


def test_the_ratio_is_reported_over_estimated_and_bounded_and_absent_without_a_count():
    req = _req(30_000)
    est = estimate_input_tokens_chars(req.messages, [])
    ok = SimpleNamespace(stop_reason="tool_use", usage=TokenSplit(input=est // 4, cache_read=est // 4,
                                                                  input_uncached_equiv=est // 2))
    assert reported_per_estimated(ok, req) == pytest.approx(0.5, abs=0.01)
    no_equiv = SimpleNamespace(stop_reason="tool_use", usage=TokenSplit(input=est // 4, cache_read=est // 4))
    assert reported_per_estimated(no_equiv, req) == pytest.approx(0.5, abs=0.01)
    assert reported_per_estimated(SimpleNamespace(stop_reason="tool_use", usage=TokenSplit(input=1)), req) == 0.05
    assert reported_per_estimated(SimpleNamespace(stop_reason="tool_use", usage=TokenSplit(input=est * 9)), req) == 2.0
    assert reported_per_estimated(SimpleNamespace(stop_reason="refusal", usage=TokenSplit(input=est)), req) is None
    assert reported_per_estimated(SimpleNamespace(stop_reason="tool_use", usage=TokenSplit(input=0)), req) is None
    assert effective_context_budget(60_000, None) == 60_000
    assert effective_context_budget(60_000, 0.25) == 240_000 and effective_context_budget(60_000, 0.6) == 100_000


def test_the_x6_presets_are_x5_with_the_budget_in_reported_tokens():
    for suffix in ("", "_cooperative"):
        x5, x6 = load_org_spec(f"pc1_supplier_g_xmodel5{suffix}"), load_org_spec(f"pc1_supplier_g_xmodel6{suffix}")
        assert x6.live_coordination["context_budget_basis"] == "reported"
        assert "context_budget_basis" not in x5.live_coordination
        assert {r.context_budget_tokens for r in x6.roles} == {60_000}
        assert {r.context_budget_tokens for r in x5.roles} == {100_000}
        strip = lambda lc: {k: v for k, v in lc.items() if k not in ("context_budget_basis", "instrument_version", "restricted")}
        assert strip(x5.live_coordination) == strip(x6.live_coordination)
        r5, r6 = dict(x5.live_coordination["restricted"]), dict(x6.live_coordination["restricted"])
        assert r6.pop("before") == "an earlier record" and r5.pop("before").startswith("measured before")
        assert r5 == r6  # the scope sentence (legacy_text) unchanged
        assert [dataclasses.replace(r, context_budget_tokens=0) for r in x5.roles] == \
               [dataclasses.replace(r, context_budget_tokens=0) for r in x6.roles]


class _Reporting(_ReactiveStub):
    """Reports a quarter of the local estimate as its input, as gpt-5-mini's calls did on x5."""

    async def invoke(self, payload):
        raw = await super().invoke(payload)
        raw.payload["input_tokens"] = int(estimate_input_tokens_chars(payload.messages, list(payload.tools)) * 0.25)
        return raw


async def _run(tmp_path, basis, budget):
    org = load_org_spec("pc1_supplier_g_xmodel6")
    lc = {**org.live_coordination, "context_budget_basis": basis, "spec_revisions": [], "reminder_minutes": [],
          "bounds": {"wait_s": 3, "drain_s": 2, "assessment_s": 2, "observation_s": 0.3, "participant_deadline_s": 8}}
    roles = [dataclasses.replace(r, tools=[*r.tools, "retire"], context_budget_tokens=budget) for r in org.roles]
    org = dataclasses.replace(org, live_coordination=lc, roles=roles, tools=[*org.tools, "retire"])
    script = [lambda res: _tool("lab_info", "x") if len(res) < 6 else _tool("retire", "x")]
    order = iter([_Reporting(script) for _ in org.roles])
    result = await run_org_live(org, tmp_path, tier="main", model_ref="stub/deterministic", experiment_id="exp_cb",
                                task_pack="materials_lab", reasoning_kind="none", cap_usd=5.0, max_model_calls=80,
                                backend=FakeContainerBackend(digest=_FAKE_DIGEST), adapter_factory=lambda: next(order))
    return [e for e in load_all_events(result.run_dir) if e["event_class"] == "context.compaction"]


@pytest.mark.asyncio
async def test_a_reported_budget_compacts_at_the_reported_size_and_records_the_conversion(tmp_path):
    est = await _run(tmp_path / "e", "estimate", 5_000)
    rep = await _run(tmp_path / "r", "reported", 5_000)
    assert est and all("budget_basis" not in e["payload"] for e in est)
    assert all(e["payload"]["tokens_before"] > 5_000 for e in est)
    # A quarter reported: 5,000 reported tokens are about 20,000 in estimator units, so compaction waits until the context
    # passes that size, and each compaction records the ratio and the threshold it used. (Counts are not compared: since
    # the consolidation, October 19, 2026, a compaction that cannot reach the budget is not retried until the context grows,
    # so each lab compacts about once on either basis.)
    assert rep
    for e in rep:
        p = e["payload"]
        assert p["budget_basis"] == "reported" and p["reported_per_estimated"] == pytest.approx(0.25, abs=0.02)
        assert p["budget_estimator_units"] == int(5_000 / p["reported_per_estimated"])
        assert p["tokens_before"] > p["budget_estimator_units"]
        assert p["tokens_before"] > p["budget_estimator_units"]
