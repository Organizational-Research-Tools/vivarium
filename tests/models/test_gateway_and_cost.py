"""M3 gateway + cost core tests, incl. the cost viability gate (DESIGN §22)."""

from __future__ import annotations

import pytest

from oaos2.kernel.manifest import Manifest
from oaos2.kernel.run_dir import RunDir
from oaos2.models.adapters.stub import MODEL_REF, StubProviderAdapter
from oaos2.models.adapters.base import ProviderError
from oaos2.models.exposure import ExposureUnsatisfiable, ModelExposureContract
from oaos2.models.gateway import call_model_gateway
from oaos2.models.raw_store import RawPayloadStore
from oaos2.models.types import (
    ModelRequest,
    NeutralBlock,
    NeutralMessage,
    SamplingParams,
    ToolSpec,
)
from oaos2.pricing.attribution import SuperClass, super_class_for
from oaos2.pricing.ledger import CostCapWouldBreach, CostLedger, TokenCapWouldBreach
from oaos2.pricing.table import foundation_pricing_table
from oaos2.trace.invariants import load_all_events
from oaos2.trace.spine import RunSpine
from oaos2.ulid import new_ulid


def _req(model_ref=MODEL_REF, tools=None, messages=None, max_out=256):
    return ModelRequest(
        call_id=new_ulid(),
        model_ref=model_ref,
        messages=messages or [NeutralMessage(role="user", blocks=[NeutralBlock(kind="text", text="hello")])],
        tools=tools or [],
        sampling=SamplingParams(max_output_tokens=max_out),
    )


async def _spine(rd) -> RunSpine:
    s = RunSpine(rd.root, run_id="run1")
    await s.start()
    return s


async def test_cost_gate_empty_run_under_one_cent(tmp_path) -> None:
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = await _spine(rd)
    ledger = CostLedger(pricing_table=foundation_pricing_table(), cap_usd=0.01)
    store = RawPayloadStore(rd.root)
    adapter = StubProviderAdapter()

    for _ in range(5):
        await call_model_gateway(
            req=_req(), adapter=adapter, ledger=ledger, spine=spine, raw_store=store,
            agent_id="a1",
        )
    report = await spine.finalize("completed")
    assert report.ok, report.failures
    # Stub is priced at zero → a domain-empty run is well under $0.01 (the gate).
    assert ledger.spent_usd < 0.01
    events = load_all_events(rd.root)
    classes = {e["event_class"] for e in events}
    assert {"model.invoked", "model.responded", "cost.recorded"} <= classes
    # Every call captures its REQUEST (the exact context the model saw) in raw/, so the
    # conversation is fully reconstructable — not just the responses (DESIGN §17.1).
    invoked = [e for e in events if e["event_class"] == "model.invoked"]
    assert invoked and all(e["payload"].get("raw_provider_request_ref") for e in invoked)
    ref = invoked[0]["payload"]["raw_provider_request_ref"]
    captured = store.get(ref)
    assert "request" in captured and "messages" in captured["request"]


async def test_pricing_hash_in_manifest(tmp_path) -> None:
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    table = foundation_pricing_table()
    m = Manifest(
        run_id="run1", experiment_id="e", task_pack_id="p",
        pricing_table_version=table.version,
    )
    m.extensions["pricing_table_hash"] = table.hash()
    m.write(rd.manifest_path)
    again = Manifest.read(rd.manifest_path)
    assert again.pricing_table_version == table.version  # round-trips whatever table is pinned
    assert again.extensions["pricing_table_hash"] == table.hash()


async def test_pre_dispatch_cap_refuses_no_mid_thought_kill(tmp_path) -> None:
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = await _spine(rd)
    # Use a priced model and a tiny cap so the projection breaches before the call.
    ledger = CostLedger(pricing_table=foundation_pricing_table(), cap_usd=1e-9)
    store = RawPayloadStore(rd.root)
    adapter = StubProviderAdapter()
    with pytest.raises(CostCapWouldBreach):
        await call_model_gateway(
            req=_req(model_ref="anthropic/claude-opus-4-8", max_out=4096),
            adapter=adapter, ledger=ledger, spine=spine, raw_store=store, agent_id="a1",
        )
    await spine.finalize("completed")
    classes = {e["event_class"] for e in load_all_events(rd.root)}
    assert "cost.cap_blocked_dispatch" in classes
    assert "model.invoked" not in classes  # refused BEFORE dispatch — no mid-thought kill


async def test_shared_output_token_cap_refuses_before_dispatch(tmp_path) -> None:
    rd = RunDir.create(tmp_path, "e", "p", "run_tokens")
    spine = RunSpine(rd.root, run_id="run_tokens")
    await spine.start()
    ledger = CostLedger(pricing_table=foundation_pricing_table(), cap_usd=1.0,
                        cap_output_tokens=100)
    with pytest.raises(TokenCapWouldBreach):
        await call_model_gateway(
            req=_req(max_out=101), adapter=StubProviderAdapter(), ledger=ledger,
            spine=spine, raw_store=RawPayloadStore(rd.root), agent_id="a1")
    await spine.finalize("completed")
    blocked = [e for e in load_all_events(rd.root)
               if e["event_class"] == "cost.cap_blocked_dispatch"]
    assert blocked[0]["payload"]["cap_output_tokens"] == 100
    assert not [e for e in load_all_events(rd.root) if e["event_class"] == "model.invoked"]


def test_estimate_tokens_never_undercounts() -> None:
    adapter = StubProviderAdapter()
    # Across a corpus of requests, estimate >= the adapter's reported actual input.
    import asyncio

    for n in range(1, 40):
        msgs = [NeutralMessage(role="user", blocks=[NeutralBlock(kind="text", text="x" * n * 7)])]
        tools = [ToolSpec(name="search", description="d" * n, parameters_schema={"a": n})]
        est = adapter.estimate_tokens(msgs, tools)
        raw = asyncio.run(
            adapter.invoke(ModelRequest(call_id=new_ulid(), model_ref=MODEL_REF, messages=msgs, tools=tools))
        )
        actual_input = raw.payload["input_tokens"]
        assert est >= actual_input, (est, actual_input, n)


async def test_multi_turn_tool_round_trip(tmp_path) -> None:
    # Turn 1: stub calls the tool. Turn 2 (tool result echoed back): stub closes.
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = await _spine(rd)
    ledger = CostLedger(pricing_table=foundation_pricing_table())
    store = RawPayloadStore(rd.root)
    adapter = StubProviderAdapter()
    tool = ToolSpec(name="search", description="search the corpus", parameters_schema={})

    r1 = await call_model_gateway(
        req=_req(tools=[tool]), adapter=adapter, ledger=ledger, spine=spine, raw_store=store, agent_id="a1"
    )
    assert r1.stop_reason == "tool_use"
    tool_block = next(b for b in r1.content_blocks if b.kind == "tool_use")

    # Build turn 2 with the tool result echoed back.
    msgs = [
        NeutralMessage(role="user", blocks=[NeutralBlock(kind="text", text="hello")]),
        NeutralMessage(role="assistant", blocks=r1.content_blocks),
        NeutralMessage(role="tool", blocks=[NeutralBlock(kind="tool_result", tool_call_id=tool_block.tool_call_id, text="42")]),
    ]
    r2 = await call_model_gateway(
        req=_req(tools=[tool], messages=msgs), adapter=adapter, ledger=ledger, spine=spine, raw_store=store, agent_id="a1"
    )
    assert r2.stop_reason == "end_turn"
    await spine.finalize("completed")


async def test_exposure_exact_match_refusal(tmp_path) -> None:
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = await _spine(rd)
    ledger = CostLedger(pricing_table=foundation_pricing_table())
    store = RawPayloadStore(rd.root)
    adapter = StubProviderAdapter()  # satisfiable_exposures = {} (LCD)
    # Confirmatory: requesting an unsatisfiable exposure refuses the cell.
    with pytest.raises(ExposureUnsatisfiable):
        await call_model_gateway(
            req=_req(), adapter=adapter, ledger=ledger, spine=spine, raw_store=store,
            exposure_contract=ModelExposureContract(thinking_trace_to_agent=True),
            confirmatory=True, agent_id="a1",
        )
    # pilot/calibration: runs but is stamped exposure_confounded.
    resp = await call_model_gateway(
        req=_req(), adapter=adapter, ledger=ledger, spine=spine, raw_store=store,
        exposure_contract=ModelExposureContract(thinking_trace_to_agent=True),
        confirmatory=False, agent_id="a1",
    )
    assert resp.realized_exposure.exposure_confounded
    assert not resp.realized_exposure.thinking_trace_to_agent  # cannot fabricate it
    await spine.finalize("completed")


async def test_tool_result_visibility_is_enforced_not_assumed(tmp_path) -> None:
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = await _spine(rd)
    ledger = CostLedger(pricing_table=foundation_pricing_table())
    store = RawPayloadStore(rd.root)
    adapter = StubProviderAdapter()  # supports only tool_result_visibility="full"
    # Confirmatory: a "redacted" contract the adapter can't produce is REFUSED,
    # not silently passed through as if satisfied (M3 §2.1).
    with pytest.raises(ExposureUnsatisfiable):
        await call_model_gateway(
            req=_req(), adapter=adapter, ledger=ledger, spine=spine, raw_store=store,
            exposure_contract=ModelExposureContract(tool_result_visibility="redacted"),
            confirmatory=True, agent_id="a1",
        )
    # pilot: runs but realized visibility falls back to "full" + stamped confounded.
    resp = await call_model_gateway(
        req=_req(), adapter=adapter, ledger=ledger, spine=spine, raw_store=store,
        exposure_contract=ModelExposureContract(tool_result_visibility="redacted"),
        confirmatory=False, agent_id="a1",
    )
    assert resp.realized_exposure.exposure_confounded
    assert resp.realized_exposure.tool_result_visibility == "full"
    # latency_ms is now a populated observable (DESIGN §10.2), not a dead 0.
    assert resp.latency_ms >= 0
    await spine.finalize("completed")


def test_activity_class_super_class_mapping() -> None:
    assert super_class_for("work_modeling") == SuperClass.WORK.value
    assert super_class_for("retry_after_validation") == SuperClass.OVERHEAD.value
    assert super_class_for("compaction") == SuperClass.OVERHEAD.value


async def test_raw_payload_dedup(tmp_path) -> None:
    store = RawPayloadStore(tmp_path)
    ref1 = store.put({"a": 1, "b": 2})
    ref2 = store.put({"b": 2, "a": 1})  # same content, different key order
    assert ref1 == ref2  # content-addressed dedup
    assert store.get(ref1) == {"a": 1, "b": 2}


def test_token_reserve_blocks_nonfinal_and_admits_final():
    """Settlement reserve (2026-07-17): non-final work is admitted only against
    (cap - reserve); the final scored commitment draws on the full pool."""
    from oaos2.pricing.ledger import CostLedger, TokenCapWouldBreach
    from oaos2.pricing.table import foundation_pricing_table
    from oaos2.models.types import (BlockKind, CachePolicy, ModelRequest, NeutralBlock,
                                    NeutralMessage, ReasoningRequest, SamplingParams)
    import pytest as _pytest

    class _Adapter:
        def estimate_tokens(self, messages, tools):
            return 10

    req = ModelRequest(
        call_id="c1", model_ref="anthropic/claude-haiku-4-5",
        messages=[NeutralMessage("user", [NeutralBlock(kind=BlockKind.TEXT.value, text="x")])],
        tools=[], sampling=SamplingParams(max_output_tokens=8000),
        reasoning=ReasoningRequest(kind="none"), cache=CachePolicy(breakpoints=[]))
    ledger = CostLedger(pricing_table=foundation_pricing_table(), cap_usd=100.0,
                        cap_output_tokens=110_000, final_reserve_tokens=20_000,
                        spent_output_tokens=85_000)
    # 85k spent + 8k projected = 93k > (110k - 20k): NON-final work is refused...
    with _pytest.raises(TokenCapWouldBreach):
        ledger.admit(req, _Adapter())
    # ...while the SAME call under the final binding draws on the full pool.
    assert ledger.admit(req, _Adapter(), reserve_exempt=True) > 0
    ledger.release(req.call_id)
    # And the reserve never admits past the full cap either.
    ledger.spent_output_tokens = 105_000
    with _pytest.raises(TokenCapWouldBreach):
        ledger.admit(req, _Adapter(), reserve_exempt=True)


def test_concurrent_admissions_reserve_the_shared_cap():
    """Two siblings cannot both admit against the same unspent token balance."""
    class _Adapter:
        def estimate_tokens(self, messages, tools):
            return 10

    ledger = CostLedger(pricing_table=foundation_pricing_table(), cap_usd=100.0,
                        cap_output_tokens=110_000, final_reserve_tokens=20_000,
                        spent_output_tokens=85_000)
    first = _req(model_ref="anthropic/claude-haiku-4-5", max_out=4096)
    second = _req(model_ref="anthropic/claude-haiku-4-5", max_out=4096)
    assert ledger.admit(first, _Adapter()) > 0
    assert ledger.reserved_output_tokens == 4096
    with pytest.raises(TokenCapWouldBreach) as caught:
        ledger.admit(second, _Adapter())
    assert caught.value.spent_tokens == 89_096  # spent + the sibling's in-flight reserve
    assert ledger.release(first.call_id)
    assert ledger.admit(second, _Adapter()) > 0
    ledger.release(second.call_id)


async def test_transport_failure_keeps_unknown_usage_reserved(tmp_path) -> None:
    class _FailingAdapter(StubProviderAdapter):
        async def invoke(self, payload):
            raise ProviderError("synthetic transport failure")

    rd = RunDir.create(tmp_path, "e", "p", "failed_reservation")
    spine = RunSpine(rd.root, run_id="failed_reservation")
    await spine.start()
    ledger = CostLedger(pricing_table=foundation_pricing_table(), cap_usd=1.0,
                        cap_output_tokens=256)
    with pytest.raises(ProviderError):
        await call_model_gateway(
            req=_req(max_out=128), adapter=_FailingAdapter(), ledger=ledger,
            spine=spine, raw_store=RawPayloadStore(rd.root), agent_id="a1")
    assert ledger.reserved_output_tokens == 128
    assert ledger._reservations and ledger.unsettled_calls
    with pytest.raises(RuntimeError, match="unresolved"):
        await call_model_gateway(
            req=_req(max_out=256), adapter=StubProviderAdapter(), ledger=ledger,
            spine=spine, raw_store=RawPayloadStore(rd.root), agent_id="a1")
    await spine.finalize("failed")


async def test_a_rejected_request_releases_its_reservation(tmp_path) -> None:
    """October 10, 2026: a request the provider rejects before processing is not billed.
    Retaining its reservation as unresolved stopped every agent of a G4 check. Since October 19
    the adapter says so (ProviderError.not_billed); a 4xx on the cause alone does not."""
    class _Rejected(Exception):
        status_code = 400

    class _RejectingAdapter(StubProviderAdapter):
        async def invoke(self, payload):
            raise ProviderError("anthropic messages.create failed: Error code: 400",
                                not_billed=True) from _Rejected()

    rd = RunDir.create(tmp_path, "e", "p", "rejected_request")
    spine = RunSpine(rd.root, run_id="rejected_request")
    await spine.start()
    ledger = CostLedger(pricing_table=foundation_pricing_table(), cap_usd=1.0, cap_output_tokens=256)
    with pytest.raises(ProviderError):
        await call_model_gateway(
            req=_req(max_out=128), adapter=_RejectingAdapter(), ledger=ledger,
            spine=spine, raw_store=RawPayloadStore(rd.root), agent_id="a1")
    assert not ledger._reservations and not ledger.unsettled_calls and ledger.reserved_output_tokens == 0
    resp = await call_model_gateway(   # the next call is admitted
        req=_req(max_out=128), adapter=StubProviderAdapter(), ledger=ledger,
        spine=spine, raw_store=RawPayloadStore(rd.root), agent_id="a1")
    assert resp is not None
    failed = [e for e in load_all_events(rd.root) if e["event_class"] == "model.invocation_failed"]
    assert failed and failed[0]["payload"]["usage_status"] == "none" and failed[0]["payload"]["provider_status"] == 400
    await spine.finalize("completed")


async def test_a_4xx_cause_alone_keeps_the_reservation(tmp_path) -> None:
    """October 19, 2026: a failure the adapter did not mark unbilled (here a 408 on the cause)
    leaves usage unknown, so the reservation is retained and dispatch stops."""
    class _Timeout(Exception):
        status_code = 408

    class _TimingOutAdapter(StubProviderAdapter):
        async def invoke(self, payload):
            raise ProviderError("request timeout") from _Timeout()

    rd = RunDir.create(tmp_path, "e", "p", "timeout_408")
    spine = RunSpine(rd.root, run_id="timeout_408")
    await spine.start()
    ledger = CostLedger(pricing_table=foundation_pricing_table(), cap_usd=1.0, cap_output_tokens=256)
    with pytest.raises(ProviderError):
        await call_model_gateway(
            req=_req(max_out=128), adapter=_TimingOutAdapter(), ledger=ledger,
            spine=spine, raw_store=RawPayloadStore(rd.root), agent_id="a1")
    assert ledger.unsettled_calls and ledger._reservations
    await spine.finalize("failed")
    failed = [e for e in load_all_events(rd.root) if e["event_class"] == "model.invocation_failed"]
    assert failed and failed[0]["payload"]["usage_status"] == "unknown"
