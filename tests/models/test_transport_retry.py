"""The shared call policy (base.invoke_under_policy; consolidation, October 19, 2026) — offline,
with fake SDK clients. A request the provider cannot have processed (a connection that never
opened, a 429) is resent after a wait and released if it never succeeds; one it may have
processed (a timeout, a server error, an unreadable answer, a call past its deadline) is resent
at most three times, each attempt recorded with usage unknown; a broken connection after
sending and any other failure are not resent. The SDKs' own hidden retries are off, and the gateway records every
wait, including those of a call whose last attempt failed (LK1 pilot, 2026-10-04)."""
from __future__ import annotations

import json
import time

import httpx
import pytest

import anthropic
import openai
from oaos2.kernel.run_dir import RunDir
from oaos2.models.adapters.anthropic import AnthropicProviderAdapter
from oaos2.models.adapters.base import ProviderError, RawProviderResponse
from oaos2.models.adapters.openai import OpenAIProviderAdapter
from oaos2.models.adapters.stub import StubProviderAdapter
from oaos2.models.gateway import call_model_gateway
from oaos2.models.raw_store import RawPayloadStore
from oaos2.pricing.ledger import CostLedger
from oaos2.pricing.table import foundation_pricing_table
from oaos2.trace.invariants import load_all_events
from tests.models.test_gateway_and_cost import _req, _spine

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_OPENAI_URL = "https://api.openai.com/v1/chat/completions"


class _Resp:
    def model_dump(self):
        return {"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn", "usage": {}}


class _Client:
    """Fails ``failures`` times with the errors ``make()`` returns, then answers."""

    def __init__(self, failures, make):
        self.calls, self.failures, self.make = 0, failures, make
        self.messages = self       # anthropic: client.messages.create
        self.chat = self           # openai: client.chat.completions.create
        self.completions = self

    def create(self, **_):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.make()
        return _Resp()


def _not_connected(sdk=anthropic, url=_ANTHROPIC_URL):
    def make():
        try:
            raise httpx.ConnectError("not connected")
        except httpx.ConnectError as cause:
            exc = sdk.APIConnectionError(request=httpx.Request("POST", url))
            exc.__cause__ = cause
            return exc
    return make


def _dropped(sdk=anthropic, url=_ANTHROPIC_URL):
    def make():
        exc = sdk.APIConnectionError(request=httpx.Request("POST", url))
        exc.__cause__ = httpx.RemoteProtocolError("peer closed connection")
        return exc
    return make


def _timeout(sdk=anthropic, url=_ANTHROPIC_URL):
    return lambda: sdk.APITimeoutError(request=httpx.Request("POST", url))


def _status(code, sdk=anthropic, url=_ANTHROPIC_URL):
    def make():
        response = httpx.Response(code, request=httpx.Request("POST", url))
        return sdk.APIStatusError(f"Error code: {code}", response=response, body=None)
    return make


def _anthropic(client):
    a = AnthropicProviderAdapter(api_key="unused")
    a._client = client
    a.TRANSPORT_WAITS, a.UNCERTAIN_WAITS = (0, 0, 0), (0, 0, 0)
    return a


def _openai(client):
    a = OpenAIProviderAdapter(api_key="unused")
    a._client = client
    a.TRANSPORT_WAITS, a.UNCERTAIN_WAITS = (0, 0, 0), (0, 0, 0)
    return a


async def test_a_connection_that_never_opened_is_resent_and_each_wait_is_kept() -> None:
    client = _Client(2, _not_connected())
    raw = await _anthropic(client).invoke({"model": "m"})
    assert client.calls == 3 and raw.payload["stop_reason"] == "end_turn"
    assert [r["attempt"] for r in raw.transport_retries] == [1, 2]
    assert all(r["usage"] == "none" and r["waited_s"] == 0 for r in raw.transport_retries)


async def test_an_outage_longer_than_the_waits_fails_the_call_unbilled() -> None:
    client = _Client(99, _not_connected())
    with pytest.raises(ProviderError, match="connection could not open on 4 attempts") as info:
        await _anthropic(client).invoke({"model": "m"})
    assert client.calls == 4 and info.value.not_billed and len(info.value.transport_retries) == 3


async def test_a_timeout_is_resent_at_most_three_times_with_usage_unknown() -> None:
    client = _Client(2, _timeout())
    raw = await _anthropic(client).invoke({"model": "m"})
    assert client.calls == 3 and [r["status"] for r in raw.transport_retries] == ["timeout", "timeout"]
    assert all(r["usage"] == "unknown" for r in raw.transport_retries)
    client = _Client(99, _timeout())
    with pytest.raises(ProviderError, match="usage unknown") as info:
        await _anthropic(client).invoke({"model": "m"})
    assert client.calls == 4 and not info.value.not_billed and len(info.value.transport_retries) == 3


async def test_a_server_error_is_resent_with_usage_unknown_and_a_429_without() -> None:
    client = _Client(1, _status(529))
    raw = await _anthropic(client).invoke({"model": "m"})
    assert client.calls == 2 and raw.transport_retries[0]["status"] == 529
    assert raw.transport_retries[0]["usage"] == "unknown"
    client = _Client(1, _status(429))
    raw = await _anthropic(client).invoke({"model": "m"})
    assert client.calls == 2 and raw.transport_retries[0]["usage"] == "none"


async def test_a_connection_broken_after_sending_is_resent_at_most_three_times_with_usage_unknown() -> None:
    """October 21, 2026 (the PI): three of 26 G5 pilot runs ended on a connection lost after sending.
    It may have been processed, so it is resent like a timeout and each attempt held against the cap."""
    client = _Client(1, _dropped())
    raw = await _anthropic(client).invoke({"model": "m"})
    assert client.calls == 2 and raw.transport_retries[0]["status"] == "connection_lost"
    assert raw.transport_retries[0]["usage"] == "unknown"
    client = _Client(99, _dropped())
    with pytest.raises(ProviderError, match="usage unknown") as info:
        await _anthropic(client).invoke({"model": "m"})
    assert client.calls == 4 and not info.value.not_billed and len(info.value.transport_retries) == 3


async def test_a_rejected_request_fails_once_unbilled() -> None:
    client = _Client(99, _status(400))
    with pytest.raises(ProviderError, match="refused before processing") as info:
        await _anthropic(client).invoke({"model": "m"})
    assert client.calls == 1 and info.value.not_billed


async def test_a_failed_request_is_not_sent_again() -> None:
    client = _Client(99, lambda: ValueError("bad request"))
    with pytest.raises(ProviderError, match="bad request") as info:
        await _anthropic(client).invoke({"model": "m"})
    assert client.calls == 1 and not info.value.not_billed


def _malformed():
    """The PC1 failure (October 20, 2026): the OpenAI SDK's ``response.json()`` raised on an OpenRouter body."""
    return json.JSONDecodeError("Expecting value", "\n" * 68, 374)


def _invalid_body(sdk):
    def make():
        response = httpx.Response(200, request=httpx.Request("POST", _OPENAI_URL))
        return sdk.APIResponseValidationError(response=response, body="<html>", message="unexpected body")
    return make


def _wrapped_malformed():
    try:
        raise _malformed()
    except json.JSONDecodeError as cause:
        exc = RuntimeError("could not read the response")
        exc.__cause__ = cause
        return exc


@pytest.mark.parametrize("adapter, make", [
    (_openai, _malformed),
    (_openai, _invalid_body(openai)),
    (_openai, _wrapped_malformed),
    (_anthropic, _invalid_body(anthropic)),
    (_anthropic, _malformed),
])
async def test_a_malformed_answer_is_resent_with_usage_unknown(adapter, make) -> None:
    client = _Client(1, make)
    raw = await adapter(client).invoke({"model": "m"})
    assert client.calls == 2 and raw.transport_retries[0]["status"] == "malformed"
    assert raw.transport_retries[0]["usage"] == "unknown"


async def test_a_persistently_malformed_answer_fails_after_three_resends_usage_unknown() -> None:
    client = _Client(99, _malformed)
    with pytest.raises(ProviderError, match="unreadable answer on 4 attempts") as info:
        await _openai(client).invoke({"model": "m"})
    assert client.calls == 4 and info.value.not_billed is False
    assert [r["status"] for r in info.value.transport_retries] == ["malformed"] * 3
    assert all(r["usage"] == "unknown" for r in info.value.transport_retries)


class _TextClient(_Client):
    """Answers ``texts`` times with a plain string, as the OpenAI client does for a body
    not labeled as JSON (non-strict validation returns ``response.text``), then answers."""

    def create(self, **_):
        self.calls += 1
        return "<html>gateway error</html>" if self.calls <= self.failures else _Resp()


@pytest.mark.parametrize("adapter", [_openai, _anthropic])
async def test_an_answer_that_is_not_a_response_object_is_resent_as_malformed(adapter) -> None:
    client = _TextClient(1, None)
    raw = await adapter(client).invoke({"model": "m"})
    assert client.calls == 2 and raw.payload["stop_reason"] == "end_turn"
    assert raw.transport_retries[0]["status"] == "malformed"
    assert raw.transport_retries[0]["usage"] == "unknown" and "str" in raw.transport_retries[0]["error"]
    client = _TextClient(99, None)
    with pytest.raises(ProviderError, match="unreadable answer on 4 attempts") as info:
        await adapter(client).invoke({"model": "m"})
    assert client.calls == 4 and info.value.not_billed is False
    assert [r["status"] for r in info.value.transport_retries] == ["malformed"] * 3


@pytest.mark.parametrize("make, calls, billed", [
    (_not_connected(openai, _OPENAI_URL), 4, False),
    (_timeout(openai, _OPENAI_URL), 4, True),
    (_dropped(openai, _OPENAI_URL), 4, True),
    (_status(502, openai, _OPENAI_URL), 4, True),
    (_status(422, openai, _OPENAI_URL), 1, False),
])
async def test_the_openai_family_follows_the_same_policy(make, calls, billed) -> None:
    client = _Client(99, make)
    with pytest.raises(ProviderError) as info:
        await _openai(client).invoke({"model": "m"})
    assert client.calls == calls and info.value.not_billed is (not billed)


async def test_a_call_past_its_deadline_is_abandoned_and_resent(monkeypatch) -> None:
    import oaos2.models.adapters.openai as mod

    class _Slow(_Client):
        def create(self, **_):
            self.calls += 1
            if self.calls == 1:
                time.sleep(0.3)
            return _Resp()

    monkeypatch.setattr(mod, "CALL_DEADLINE_S", 0.05)
    a = _openai(_Slow(0, None))
    dropped = []
    monkeypatch.setattr(a, "_drop_client", lambda: dropped.append(True))
    raw = await a.invoke({"model": "m"})
    assert dropped == [True] and raw.transport_retries[0]["status"] == "deadline"
    assert raw.transport_retries[0]["usage"] == "unknown"


def test_sdk_retries_are_disabled() -> None:
    for adapter in (AnthropicProviderAdapter(api_key="unused"), OpenAIProviderAdapter(api_key="unused")):
        client = adapter._ensure_client()
        try:
            assert client.max_retries == 0
        finally:
            client.close()


class _RetriedStub(StubProviderAdapter):
    async def invoke(self, payload):
        raw = await super().invoke(payload)
        return RawProviderResponse(payload=raw.payload, transport_retries=[
            {"attempt": 1, "error": "APITimeoutError: x", "status": "timeout", "usage": "unknown", "waited_s": 15}])


async def test_the_gateway_records_each_wait_in_the_trace(tmp_path) -> None:
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = await _spine(rd)
    await call_model_gateway(req=_req(), adapter=_RetriedStub(), spine=spine, raw_store=RawPayloadStore(rd.root),
                             ledger=CostLedger(pricing_table=foundation_pricing_table(), cap_usd=1.0), agent_id="a1")
    report = await spine.finalize("completed")
    assert report.ok, report.failures
    retries = [e for e in load_all_events(rd.root) if e["event_class"] == "model.transport_retry"]
    assert len(retries) == 1 and retries[0]["agent_id"] == "a1" and retries[0]["payload"]["waited_s"] == 15
    assert retries[0]["payload"]["usage"] == "unknown"


async def test_the_gateway_keeps_waits_when_the_final_attempt_fails(tmp_path) -> None:
    class _FailingStub(StubProviderAdapter):
        async def invoke(self, payload):
            raise ProviderError("not connected", not_billed=True, transport_retries=[
                {"attempt": 1, "error": "ConnectError", "status": None, "usage": "none", "waited_s": 15}])

    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = await _spine(rd)
    ledger = CostLedger(pricing_table=foundation_pricing_table(), cap_usd=1.0)
    with pytest.raises(ProviderError):
        await call_model_gateway(req=_req(), adapter=_FailingStub(), spine=spine, raw_store=RawPayloadStore(rd.root),
                                 ledger=ledger, agent_id="a1")
    assert ledger.reserved_usd == 0 and not ledger.unsettled_calls
    assert (await spine.finalize("completed")).ok
    retries = [e for e in load_all_events(rd.root) if e["event_class"] == "model.transport_retry"]
    assert len(retries) == 1


async def test_an_uncertain_attempt_is_held_against_the_cap_but_not_spent(tmp_path) -> None:
    """October 19, 2026 (for the PI's review): a resent attempt with usage unknown is held at
    the call's projected cost; admission counts the hold, spending and pressure do not."""
    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = await _spine(rd)
    ledger = CostLedger(pricing_table=foundation_pricing_table(), cap_usd=1.0)
    projected = 0.25  # the stub model is priced at zero; give the call a projected cost
    ledger.project_next_call_usd = lambda req, adapter: projected
    await call_model_gateway(req=_req(), adapter=_RetriedStub(), spine=spine, raw_store=RawPayloadStore(rd.root),
                             ledger=ledger, agent_id="a1")
    assert ledger.uncertain_usd == pytest.approx(projected) and ledger.reserved_usd == 0
    spent = ledger.spent_usd
    assert ledger.pressure_fraction() == pytest.approx(spent / 1.0)
    assert (await spine.finalize("completed")).ok
    retry = [e for e in load_all_events(rd.root) if e["event_class"] == "model.transport_retry"][0]
    assert retry["payload"]["held_usd"] == pytest.approx(projected)
    # a hold that leaves no room for the next projection refuses dispatch
    ledger.hold_uncertain(1.0 - ledger.spent_usd - ledger.uncertain_usd)
    from oaos2.pricing.ledger import CostCapWouldBreach
    with pytest.raises(CostCapWouldBreach):
        ledger.admit(_req(), _RetriedStub())


async def test_an_attempt_that_cannot_have_been_billed_is_not_held(tmp_path) -> None:
    class _NotSentStub(StubProviderAdapter):
        async def invoke(self, payload):
            raw = await super().invoke(payload)
            return RawProviderResponse(payload=raw.payload, transport_retries=[
                {"attempt": 1, "error": "ConnectError", "status": None, "usage": "none", "waited_s": 15}])

    rd = RunDir.create(tmp_path, "e", "p", "run1")
    spine = await _spine(rd)
    ledger = CostLedger(pricing_table=foundation_pricing_table(), cap_usd=1.0)
    await call_model_gateway(req=_req(), adapter=_NotSentStub(), spine=spine, raw_store=RawPayloadStore(rd.root),
                             ledger=ledger, agent_id="a1")
    assert ledger.uncertain_usd == 0
    assert (await spine.finalize("completed")).ok


class _OAIResp:
    def model_dump(self):
        return {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {}}


class _OAIClient:
    """A fake OpenAI SDK client: ``failures`` calls raise ``exc``, then one succeeds."""

    def __init__(self, failures, exc):
        self.calls, self.failures, self.exc = 0, failures, exc
        self.chat = self
        self.completions = self

    def create(self, **_):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.exc
        return _OAIResp()


def _rate_limited(code=None):
    import openai
    resp = httpx.Response(429, request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"))
    return openai.RateLimitError("rate-limited upstream", response=resp,
                                 body={"code": code} if code else None)


def _oai_adapter(client):
    from oaos2.models.adapters.openai_compatible import OpenRouterProviderAdapter
    a = OpenRouterProviderAdapter(api_key="unused")
    a._client = client
    a.TRANSPORT_WAITS = (0, 0, 0)
    return a


async def test_an_openai_compatible_rate_limit_is_waited_out_and_kept() -> None:
    """G5 model check, 2026-10-19: OpenRouter's upstream rate-limited Qwen 3.8 Flash, and one failed
    call ended the run. A rate limit is now sent again after a wait, as a lost connection is."""
    client = _OAIClient(2, _rate_limited())
    raw = await _oai_adapter(client).invoke({"model": "m"})
    assert client.calls == 3 and [r["attempt"] for r in raw.transport_retries] == [1, 2]
    assert all("RateLimitError" in r["error"] for r in raw.transport_retries)
    assert all(r["usage"] == "none" for r in raw.transport_retries)  # a 429 was not processed
    with pytest.raises(ProviderError, match="on attempt 4") as info:
        await _oai_adapter(_OAIClient(99, _rate_limited())).invoke({"model": "m"})
    assert info.value.not_billed


async def test_an_exhausted_quota_is_not_waited_out() -> None:
    import openai
    exc = _rate_limited("insufficient_quota")
    assert getattr(exc, "code", None) == "insufficient_quota"
    client = _OAIClient(99, exc)
    with pytest.raises(ProviderError) as info:
        await _oai_adapter(client).invoke({"model": "m"})
    assert client.calls == 1 and isinstance(exc, openai.RateLimitError) and info.value.not_billed


@pytest.mark.parametrize("kind", ["chat", "responses"])
async def test_a_resend_after_a_deadline_opens_a_new_client(monkeypatch, kind) -> None:
    """PC1 9.2 calibration (October 20, 2026): after a call passed its deadline, _drop_client closed the
    client and the resend reused it, failing with "the client has been closed"; every lab of two runs
    ended. The real _drop_client runs here, and the resend must go to a newly opened client."""
    import oaos2.models.adapters.openai as mod
    from oaos2.models.adapters.openai_responses import OpenAIResponsesProviderAdapter

    made = []

    class _Fresh:
        def __init__(self):
            self.calls, self.closed = 0, False
            self.chat = self.completions = self.responses = self
            made.append(self)

        def create(self, **_):
            if self.closed:
                raise RuntimeError("Cannot send a request, as the client has been closed.")
            self.calls += 1
            if len(made) == 1:
                time.sleep(0.3)  # the first client's call outlives its deadline
            return _Resp()

        def close(self):
            self.closed = True

    monkeypatch.setattr(mod, "CALL_DEADLINE_S", 0.05)
    if kind == "responses":
        import oaos2.models.adapters.openai_responses as rmod
        monkeypatch.setattr(rmod, "CALL_DEADLINE_S", 0.05)
    a = OpenAIProviderAdapter(api_key="k") if kind == "chat" else OpenAIResponsesProviderAdapter(api_key="k")
    a.UNCERTAIN_WAITS = (0, 0, 0)
    monkeypatch.setattr(a, "_ensure_client", lambda: a._client or setattr(a, "_client", _Fresh()) or a._client)
    raw = await a.invoke({"model": "m"})
    assert len(made) == 2 and made[0].closed and not made[1].closed
    assert raw.transport_retries[0]["status"] == "deadline"
