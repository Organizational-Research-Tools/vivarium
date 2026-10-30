"""No network: settle late usage and retain uncertainty instead of treating it as zero."""
import asyncio
import threading

import pytest

from oaos2.models.adapters.anthropic import AnthropicProviderAdapter
from oaos2.models.adapters.base import RawProviderResponse, ProviderError
from oaos2.models.adapters.stub import StubProviderAdapter
from oaos2.models.gateway import call_model_gateway
from oaos2.models.raw_store import RawPayloadStore
from oaos2.models.types import ModelRequest, SamplingParams, CachePolicy
from oaos2.pricing.attribution import attribute_cost
from oaos2.pricing.ledger import CostLedger, validate_spending_cap
from oaos2.pricing.table import foundation_pricing_table
from oaos2.trace.invariants import load_all_events
from oaos2.trace.spine import RunSpine


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 0, True])
def test_live_cap_requires_positive_finite_number(value):
    with pytest.raises(ValueError):
        validate_spending_cap(value)


@pytest.mark.parametrize("short,long", [(1000, 0), (0, 1000), (400, 600)])
def test_cache_lifetime_prices_and_uncached_equivalent(short, long):
    req = ModelRequest("cache", "anthropic/claude-haiku-4-5", [],
                       cache=CachePolicy(ttl_overrides={"system": "1h"}))
    raw = RawProviderResponse({"content": [], "stop_reason": "end_turn", "usage": {
        "input_tokens": 10, "output_tokens": 0, "cache_read_input_tokens": 50,
        "cache_creation_input_tokens": short + long,
        "cache_creation": {"ephemeral_5m_input_tokens": short,
                           "ephemeral_1h_input_tokens": long}}})
    response = AnthropicProviderAdapter(api_key="unused").normalize(raw, req, "raw")
    cost = attribute_cost(response, foundation_pricing_table(), "work_modeling")
    assert cost.cost_usd == pytest.approx((10 + 5 + short * 1.25 + long * 2) / 1e6)
    assert cost.cost_if_no_cache_usd == pytest.approx((10 + 50 + short + long) / 1e6)
    assert response.usage.as_dict()["cache_write_by_ttl"] == {"5m": short, "1h": long}


def test_missing_cache_duration_is_not_silently_priced_as_short():
    req = ModelRequest("cache", "anthropic/claude-haiku-4-5", [],
                       cache=CachePolicy(ttl_overrides={"system": "1h"}))
    raw = RawProviderResponse({"usage": {"cache_creation_input_tokens": 100}})
    with pytest.raises(ProviderError, match="lifetime"):
        AnthropicProviderAdapter(api_key="unused").normalize(raw, req, "raw")


@pytest.mark.parametrize("settles", [True, False])
async def test_cancelled_thread_request_settles_or_keeps_liability(tmp_path, settles):
    started, finish = threading.Event(), threading.Event()

    class DelayedAdapter(StubProviderAdapter):
        async def invoke(self, payload):
            def wait():
                started.set()
                finish.wait(2)
            await asyncio.to_thread(wait)
            raw = await super().invoke(payload)
            raw.payload["output_tokens"] = 100
            return raw

    spine = RunSpine(tmp_path, "r")
    await spine.start()
    ledger = CostLedger(foundation_pricing_table(), cap_output_tokens=100)
    req = ModelRequest("cancel", "stub/deterministic", [],
                       sampling=SamplingParams(max_output_tokens=100))
    task = asyncio.create_task(call_model_gateway(
        req=req, adapter=DelayedAdapter(), ledger=ledger, spine=spine,
        raw_store=RawPayloadStore(tmp_path), cancellation_grace_s=0.1))
    while not started.is_set():
        await asyncio.sleep(0.001)
    task.cancel()
    await asyncio.sleep(0.01)
    assert ledger.reserved_output_tokens == 100
    if settles:
        finish.set()
    try:
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        if settles:
            assert ledger.spent_output_tokens == 100
            assert not ledger._reservations and not ledger.unsettled_calls
        else:
            assert ledger.spent_output_tokens == 0
            assert ledger.reserved_output_tokens == 100 and ledger.unsettled_calls
            with pytest.raises(RuntimeError, match="unresolved"):
                ledger.admit(ModelRequest("later", "stub/deterministic", []), StubProviderAdapter())
        await spine.finalize("failed")
        events = load_all_events(tmp_path)
        if settles:
            response = next(e for e in events if e["event_class"] == "model.responded")
            assert response["payload"]["usage"]["output"] == 100
        else:
            failed = next(e for e in events if e["event_class"] == "model.invocation_failed")
            assert failed["payload"]["usage_status"] == "unknown"
    finally:
        finish.set()


async def test_adapter_cancellation_cleanup_cannot_extend_grace_or_write_late(tmp_path):
    started, release = asyncio.Event(), asyncio.Event()

    class ResistantAdapter(StubProviderAdapter):
        async def invoke(self, payload):
            started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
            return await super().invoke(payload)

    spine = RunSpine(tmp_path, "r")
    await spine.start()
    ledger = CostLedger(foundation_pricing_table())
    task = asyncio.create_task(call_model_gateway(
        req=ModelRequest("resistant", "stub/deterministic", []),
        adapter=ResistantAdapter(), ledger=ledger, spine=spine,
        raw_store=RawPayloadStore(tmp_path), cancellation_grace_s=0.01))
    await started.wait()
    task.cancel()
    try:
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 0.5)
        assert ledger.unsettled_calls
        await spine.finalize("failed")
        trace = (tmp_path / "trace/events.jsonl").read_bytes()
        release.set()
        await asyncio.sleep(0.01)
        assert (tmp_path / "trace/events.jsonl").read_bytes() == trace
        assert not ledger.records
    finally:
        release.set()


async def test_unusable_returned_response_stays_linked_to_failed_call(tmp_path):
    class InvalidUsageAdapter(StubProviderAdapter):
        def normalize(self, raw, req, raw_ref):
            raise ValueError("invalid reported usage")

    spine = RunSpine(tmp_path, "r")
    await spine.start()
    ledger = CostLedger(foundation_pricing_table())
    store = RawPayloadStore(tmp_path)
    with pytest.raises(ValueError, match="invalid reported usage"):
        await call_model_gateway(req=ModelRequest("invalid", "stub/deterministic", []),
                                 adapter=InvalidUsageAdapter(), ledger=ledger,
                                 spine=spine, raw_store=store)
    assert ledger.unsettled_calls
    await spine.finalize("failed")
    failure = next(e for e in load_all_events(tmp_path) if e["event_class"] == "model.invocation_failed")
    assert store.get(failure["payload"]["raw_provider_response_ref"])["output_tokens"] > 0
