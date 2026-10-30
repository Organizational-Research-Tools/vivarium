"""A request the provider refuses with a client error is released, not held unresolved (October 10, 2026).

In a Claude Haiku 4.5 run of PC1's supplier form one lab's prompt passed the provider's 200,000-token
limit; the 400 response left the shared ledger unresolved and every other lab stopped on its next call.
No network."""
import httpx
import pytest

from oaos2.models.adapters.anthropic import AnthropicProviderAdapter
from oaos2.models.adapters.base import ProviderError
from oaos2.models.adapters.stub import StubProviderAdapter
from oaos2.models.gateway import call_model_gateway
from oaos2.models.raw_store import RawPayloadStore
from oaos2.models.types import ModelRequest, SamplingParams
from oaos2.pricing.ledger import CostLedger
from oaos2.pricing.table import foundation_pricing_table
from oaos2.trace.invariants import load_all_events
from oaos2.trace.spine import RunSpine


class _Failing(StubProviderAdapter):
    def __init__(self, exc):
        super().__init__()
        self.exc = exc

    async def invoke(self, payload):
        raise self.exc


@pytest.mark.parametrize("not_billed", [True, False])
async def test_a_refused_request_is_released_and_others_continue(tmp_path, not_billed):
    spine = RunSpine(tmp_path, "r")
    await spine.start()
    ledger = CostLedger(foundation_pricing_table(), cap_output_tokens=5000)
    req = ModelRequest("too_long", "stub/deterministic", [], sampling=SamplingParams(max_output_tokens=100))
    with pytest.raises(ProviderError):
        await call_model_gateway(req=req, adapter=_Failing(ProviderError("prompt is too long", not_billed=not_billed)),
                                 ledger=ledger, spine=spine, raw_store=RawPayloadStore(tmp_path))
    later = ModelRequest("later", "stub/deterministic", [])
    if not_billed:
        assert not ledger._reservations and not ledger.unsettled_calls
        ledger.admit(later, StubProviderAdapter())  # another agent's next call goes ahead
    else:
        assert ledger.unsettled_calls  # unknown usage stays fail-closed
        with pytest.raises(RuntimeError, match="unresolved"):
            ledger.admit(later, StubProviderAdapter())
    await spine.finalize("failed")
    failed = next(e for e in load_all_events(tmp_path) if e["event_class"] == "model.invocation_failed")
    assert failed["payload"]["usage_status"] == ("none" if not_billed else "unknown")  # T1's value since October 10
    assert failed["payload"]["reservation_retained"] is (not not_billed)


@pytest.mark.parametrize("status,billed", [(400, False), (413, False), (429, False), (408, True), (409, True),
                                         (500, True), (529, True)])
async def test_the_adapter_marks_client_errors_as_not_billed(monkeypatch, status, billed):
    import anthropic

    cls = {400: anthropic.BadRequestError, 429: anthropic.RateLimitError,
           500: anthropic.InternalServerError}.get(status, anthropic.APIStatusError)
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    exc = cls("refused", response=response, body=None)

    class _Messages:
        def create(self, **_):
            raise exc

    class _Client:
        messages = _Messages()

    adapter = AnthropicProviderAdapter(api_key="unused")
    adapter.TRANSPORT_WAITS = adapter.UNCERTAIN_WAITS = ()  # 429 and server errors are resent after waits; none here
    monkeypatch.setattr(adapter, "_ensure_client", lambda: _Client())
    with pytest.raises(ProviderError) as info:
        await adapter.invoke({})
    assert info.value.not_billed is (not billed)
