"""Make one checked model call and record its response and cost.

Resolve requested model information against adapter capabilities, reserve the
projected budget, invoke the adapter, retain its payload, normalize the response,
and record usage and events. Release reservations only before dispatch; retain
uncertain usage and refuse further calls until it can be settled. Credentials are managed by adapters on the host. This function does
not choose subsequent turns or execute the model's requested tools."""

from __future__ import annotations

import asyncio
import time

from oaos2.models.adapters.base import ProviderAdapter
from oaos2.models.exposure import ModelExposureContract, resolve_exposure
from oaos2.models.raw_store import RawPayloadStore
from oaos2.models.types import ModelRequest, ModelResponse
from oaos2.pricing.attribution import attribute_cost
from oaos2.pricing.ledger import CostCapWouldBreach, CostLedger, TokenCapWouldBreach
from oaos2.trace.spine import RunSpine


_pending_settlements: set[asyncio.Task] = set()


def _settlement_done(task: asyncio.Task) -> None:
    _pending_settlements.discard(task)
    if not task.cancelled():
        task.exception()  # observe failures from a request abandoned after its grace period


def _serialize_request(req: ModelRequest) -> dict:
    """A JSON-able, adapter-neutral view of the exact context this call saw.

    Captures the full conversation (every block, incl. thinking/tool blocks), the
    tool specs, sampling, reasoning and cache policy — enough to reconstruct the
    turn. Provider-specific rendering (e.g. Anthropic ``cache_control``) is a pure
    function of this + the cache fingerprint, so this is the canonical record.
    """
    return {
        "call_id": req.call_id,
        "model_ref": req.model_ref,
        "messages": [
            {
                "role": m.role,
                "blocks": [
                    {
                        "kind": b.kind,
                        "text": b.text,
                        "tool_name": b.tool_name,
                        "tool_call_id": b.tool_call_id,
                        "arguments": b.arguments,
                        "provider_opaque": b.provider_opaque,
                    }
                    for b in m.blocks
                ],
            }
            for m in req.messages
        ],
        "tools": [
            {"name": t.name, "description": t.description, "parameters_schema": t.parameters_schema}
            for t in req.tools
        ],
        "sampling": {
            "temperature": req.sampling.temperature,
            "top_p": req.sampling.top_p,
            "max_output_tokens": req.sampling.max_output_tokens,
            "stop": req.sampling.stop,
            "platform_seed": req.sampling.platform_seed,
        },
        "reasoning": {"kind": req.reasoning.kind, "budget_tokens": req.reasoning.budget_tokens},
        "cache": {"breakpoints": req.cache.breakpoints,
                  "ttl_overrides": req.cache.ttl_overrides,
                  "fingerprint": req.cache.fingerprint()},
    }


def _hold_retry(ledger: CostLedger, retry: dict, projected_usd: float) -> dict:
    """Hold a resent attempt's possible cost on the ledger and return its trace payload.

    An attempt with usage "unknown" may have been billed; it is held at the call's projected
    cost (``CostLedger.hold_uncertain``) and the amount is recorded as ``held_usd``, so the
    archive can total what the ledger held (October 19, 2026, for the PI's review)."""
    payload = dict(retry)
    if payload.get("usage") == "unknown":
        ledger.hold_uncertain(projected_usd)
        payload["held_usd"] = projected_usd
    return payload


async def call_model_gateway(
    *,
    req: ModelRequest,
    adapter: ProviderAdapter,
    ledger: CostLedger,
    spine: RunSpine,
    raw_store: RawPayloadStore,
    activity_class: str = "work_modeling",
    exposure_contract: ModelExposureContract | None = None,
    confirmatory: bool = True,
    agent_id: str | None = None,
    caused_by: str | None = None,
    reserve_exempt: bool = False,  # current binding IS the final scored commitment
    closing_call: bool = False,  # a call after the work period, drawing on the ledger's closing reserve
    cancellation_grace_s: float = 5.0,  # bounded settlement before propagating cancellation
    on_admitted=None,  # fires AFTER ledger.admit succeeds, before adapter.invoke:
                       # the authoritative call-count admission point (audit round 8
                       # P1-1) — a cost-cap-rejected dispatch charges nothing.
) -> ModelResponse:
    """Execute one provider call end-to-end; emit model.invoked/responded/cost.recorded."""
    contract = exposure_contract or ModelExposureContract()
    resolution = resolve_exposure(contract, adapter, confirmatory=confirmatory, model_ref=req.model_ref)  # may raise

    # Cost-free preparation FIRST (probe 2026-08-17): request capture and
    # translation can fail without a reservation or capacity charge existing —
    # previously a raw-store failure produced a charged call with zero
    # provider invocations.
    # Capture the REQUEST (the exact context the model saw this call) verbatim in
    # raw/, content-addressed — so the conversation is fully reconstructable, not only
    # the responses (DESIGN §17.1 PromptEnvelope/AgentView intent).
    request_ref = raw_store.put({"request": _serialize_request(req)})
    provider_req = adapter.translate(req)

    # PRE-DISPATCH CAP — the backstop (M5 also checks at the action layer, §3.2).
    try:
        projected = ledger.admit(req, adapter, reserve_exempt=reserve_exempt, closing_call=closing_call)
    except (CostCapWouldBreach, TokenCapWouldBreach) as breach:
        payload = ({"projected_output_tokens": breach.projected_tokens,
                    "cap_output_tokens": breach.cap_tokens}
                   if isinstance(breach, TokenCapWouldBreach) else
                   {"projected_usd": breach.projected_usd, "cap_usd": breach.cap_usd})
        await spine.emit_event(
            "cost.cap_blocked_dispatch",
            agent_id=agent_id,
            model_call_id=req.call_id,
            caused_by=caused_by,
            payload=payload,
        )
        raise

    dispatched = False
    invoked = None
    completion = None
    abandoned = False
    provider_response_ref = None
    try:
        invoked = await spine.emit_event(
            "model.invoked", agent_id=agent_id, model_call_id=req.call_id,
            caused_by=caused_by,
            payload={"model_ref": req.model_ref, "projected_usd": projected,
                     "activity_class": activity_class, "raw_provider_request_ref": request_ref},
        )
        if on_admitted is not None:
            on_admitted()
        call_started = time.monotonic()

        async def receive_and_settle():
            nonlocal provider_response_ref
            raw = await adapter.invoke(provider_req)
            if abandoned:
                # The run has already recorded unknown usage and may have closed.
                # A cancellation-resistant adapter must not append late events.
                return None
            for retry in getattr(raw, "transport_retries", None) or []:
                # an attempt the adapter resent (2026-10-04, 2026-10-19): apparatus, not conduct;
                # usage "unknown" marks one that may have been billed
                await spine.emit_event("model.transport_retry", agent_id=agent_id, model_call_id=req.call_id,
                                       caused_by=invoked, payload=_hold_retry(ledger, retry, projected))
            raw_ref = raw_store.put(raw.payload)
            provider_response_ref = raw_ref
            resp = adapter.normalize(raw, req, raw_ref)
            resp.realized_exposure = resolution.realized
            # Provider round-trip latency is a preserved observable (DESIGN §10.2): the
            # gateway measures it (the adapter can't see the full dispatch boundary).
            if not resp.latency_ms:
                resp.latency_ms = int((time.monotonic() - call_started) * 1000)

            record = attribute_cost(resp, ledger.pricing_table, activity_class)
            resp.cost_usd = record.cost_usd
            ledger.apply(record, call_id=req.call_id)

            await spine.emit_event(
                "cost.recorded",
                agent_id=agent_id,
                model_call_id=req.call_id,
                caused_by=invoked,
                payload=record.as_dict(),
            )
            resp.response_event_id = await spine.emit_event(
                "model.responded",
                agent_id=agent_id,
                model_call_id=req.call_id,
                caused_by=invoked,
                payload={
                    "stop_reason": resp.stop_reason,
                    "realized_exposure": resp.realized_exposure.as_dict(),
                    "raw_provider_response_ref": resp.raw_provider_response_ref,
                    "cost_usd": resp.cost_usd,
                    "usage": resp.usage.as_dict(),
                    "latency_ms": resp.latency_ms,
                    "realized_reasoning": {
                        "kind": resp.realized_reasoning.kind,
                        "requested_budget": resp.realized_reasoning.requested_budget,
                        "realized_tokens": resp.realized_reasoning.realized_tokens,
                    },
                },
            )
            return resp

        dispatched = True
        completion = asyncio.create_task(receive_and_settle())
        _pending_settlements.add(completion)
        completion.add_done_callback(_settlement_done)
        try:
            return await asyncio.shield(completion)
        except asyncio.CancelledError:
            # Cancellation of the caller does not prove that a remote request
            # stopped. Allow a short settlement window while keeping its budget.
            try:
                await asyncio.wait_for(asyncio.shield(completion), cancellation_grace_s)
            except BaseException:
                if not completion.done():
                    abandoned = True
                    completion.cancel()
            raise
    except BaseException as exc:
        # Keep the waits completed before a final attempt failed. The reservation handling
        # below must still run if recording a retry fails.
        for retry in getattr(exc, "transport_retries", None) or []:
            payload = _hold_retry(ledger, retry, projected)
            try:
                await spine.emit_event("model.transport_retry", agent_id=agent_id, model_call_id=req.call_id,
                                       caused_by=invoked, payload=payload)
            except Exception:
                pass
        status = getattr(getattr(exc, "__cause__", None), "status_code", None)
        if dispatched and req.call_id in ledger._reservations and getattr(exc, "not_billed", False):
            # The adapter established that nothing was processed (ProviderError.not_billed: a
            # connection that never opened, or a refusal before processing), so the reservation
            # is released. Retaining it stopped every agent of a G4 check (October 10, 2026):
            # one invalid request left the ledger "unresolved" and all further dispatch was
            # refused. Until October 19 any 4xx found on the cause released it; the adapters
            # now decide, so a 408 or 409 no longer counts as unbilled.
            ledger.release(req.call_id)
            try:
                await spine.emit_event(
                    "model.invocation_failed", agent_id=agent_id,
                    model_call_id=req.call_id, caused_by=invoked,
                    payload={"error": str(exc) or type(exc).__name__, "usage_status": "none",
                             "provider_status": status, "reservation_retained": False})
            except Exception:
                pass
            raise
        if dispatched and req.call_id in ledger._reservations:
            reason = type(exc).__name__
            ledger.mark_unsettled(req.call_id, reason)
            # Use the existing failure event vocabulary. Unknown usage is not zero.
            try:
                await spine.emit_event(
                    "model.invocation_failed", agent_id=agent_id,
                    model_call_id=req.call_id, caused_by=invoked,
                    payload={"error": str(exc) or reason, "usage_status": "unknown",
                             "reservation_retained": True,
                             **({"raw_provider_response_ref": provider_response_ref}
                                if provider_response_ref is not None else {})},
                )
            except Exception:
                # A trace failure must not erase the outstanding liability.
                pass
        raise
    finally:
        if not dispatched:
            ledger.release(req.call_id)
