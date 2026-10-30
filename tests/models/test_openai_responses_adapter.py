"""The OpenAI Responses adapter (namespace ``openai_responses``, October 12, 2026): reasoning summaries recorded as
summaries, encrypted reasoning echoed back, tools with reasoning, and the accounting rules of the Anthropic adapter.
Offline; no network."""

from __future__ import annotations

import asyncio

import pytest

from oaos2.models.adapters import resolve_provider_adapter
from oaos2.models.adapters.base import ProviderError, RawProviderResponse
from oaos2.models.adapters.openai_responses import OpenAIResponsesProviderAdapter
from oaos2.models.types import (BlockKind, ModelRequest, NeutralBlock, NeutralMessage, ReasoningRequest,
                                SamplingParams, ToolSpec)


def _req(reasoning="thinking", budget=8000):
    reasoned = NeutralBlock(kind=BlockKind.THINKING.value, text="I'll measure it.",
                            provider_opaque={"type": "reasoning", "id": "rs_1", "summary": [{"type": "summary_text",
                                             "text": "I'll measure it."}], "encrypted_content": "ENC"})
    return ModelRequest(
        call_id="c1", model_ref="openai_responses/gpt-5-mini",
        messages=[NeutralMessage("system", [NeutralBlock(kind="text", text="You run a lab.")]),
                  NeutralMessage("user", [NeutralBlock(kind="text", text="Measure p_1.")]),
                  NeutralMessage("assistant", [reasoned, NeutralBlock(kind="text", text="Measuring."),
                                               NeutralBlock(kind="tool_use", tool_name="measure", tool_call_id="call_1",
                                                            arguments={"prototype_id": "p_1"})]),
                  NeutralMessage("tool", [NeutralBlock(kind="tool_result", tool_call_id="call_1", text="80.1")])],
        tools=[ToolSpec(name="measure", description="Measure.", parameters_schema={"properties": {"prototype_id": {"type": "string"}}})],
        sampling=SamplingParams(max_output_tokens=2000, temperature=1.0),
        reasoning=ReasoningRequest(kind=reasoning, budget_tokens=budget))


def test_the_namespace_resolves_and_the_chat_completions_path_is_untouched():
    assert resolve_provider_adapter("openai_responses") is OpenAIResponsesProviderAdapter
    from oaos2.models.adapters.openai import OpenAIProviderAdapter
    assert resolve_provider_adapter("openai") is OpenAIProviderAdapter


def test_translate_puts_the_system_text_in_instructions_and_echoes_the_encrypted_reasoning():
    p = OpenAIResponsesProviderAdapter().translate(_req())
    assert p["model"] == "gpt-5-mini" and p["store"] is False and p["instructions"] == "You run a lab."
    assert p["reasoning"] == {"effort": "medium", "summary": "auto"} and p["include"] == ["reasoning.encrypted_content"]
    assert "temperature" not in p and p["max_output_tokens"] == 2000
    kinds = [i.get("type") or i.get("role") for i in p["input"]]
    assert kinds == ["user", "reasoning", "assistant", "function_call", "function_call_output"]
    assert p["input"][1]["encrypted_content"] == "ENC" and p["input"][3]["call_id"] == "call_1"
    assert p["input"][4] == {"type": "function_call_output", "call_id": "call_1", "output": "80.1"}
    assert p["tools"] == [{"type": "function", "name": "measure", "description": "Measure.", "strict": False,
                           "parameters": {"type": "object", "properties": {"prototype_id": {"type": "string"}}}}]
    low = OpenAIResponsesProviderAdapter().translate(_req(budget=1000))
    assert low["reasoning"]["effort"] == "low"
    plain = OpenAIResponsesProviderAdapter().translate(_req(reasoning="none"))  # a memory recap
    assert "reasoning" not in plain and "temperature" not in plain  # reasoning models reject a temperature (400)


def _payload(output, status="completed", incomplete=None, cached=300):
    return {"status": status, "incomplete_details": {"reason": incomplete} if incomplete else None, "output": output,
            "usage": {"input_tokens": 1000, "input_tokens_details": {"cached_tokens": cached}, "output_tokens": 120,
                      "output_tokens_details": {"reasoning_tokens": 80}}}


def test_normalize_records_the_summary_as_a_summary_and_maps_tools_stops_and_usage():
    a = OpenAIResponsesProviderAdapter(expose_thinking=True)
    out = [{"type": "reasoning", "id": "rs_2", "summary": [{"type": "summary_text", "text": "Check the rule."}],
            "encrypted_content": "ENC2"},
           {"type": "function_call", "call_id": "call_2", "name": "measure", "arguments": "{\"prototype_id\": \"p_2\"}"}]
    r = a.normalize(RawProviderResponse(payload=_payload(out)), _req(), raw_ref="raw/x")
    assert r.stop_reason == "tool_use"
    think, tool = r.content_blocks
    assert think.kind == "thinking" and think.text == "Check the rule." and think.provider_opaque["is_summary"] is True
    assert think.provider_opaque["encrypted_content"] == "ENC2"
    assert (tool.tool_name, tool.tool_call_id, tool.arguments) == ("measure", "call_2", {"prototype_id": "p_2"})
    assert (r.usage.input, r.usage.cache_read, r.usage.input_uncached_equiv, r.usage.output, r.usage.reasoning) == \
        (700, 300, 1000, 120, 80)
    hidden = OpenAIResponsesProviderAdapter(expose_thinking=False).normalize(
        RawProviderResponse(payload=_payload(out)), _req(), raw_ref="raw/x")
    assert hidden.content_blocks[0].text == ""
    text = [{"type": "message", "content": [{"type": "output_text", "text": "Done."}]}]
    assert a.normalize(RawProviderResponse(payload=_payload(text)), _req(), "r").stop_reason == "end_turn"
    assert a.normalize(RawProviderResponse(payload=_payload([], status="incomplete", incomplete="max_output_tokens")),
                       _req(), "r").stop_reason == "max_tokens"
    refused = [{"type": "message", "content": [{"type": "refusal", "refusal": "No."}]}]
    assert a.normalize(RawProviderResponse(payload=_payload(refused)), _req(), "r").stop_reason == "refusal"


class _Client:
    def __init__(self, exc):
        self.responses = self
        self.exc = exc

    def create(self, **kw):
        raise self.exc


def _status_error(status):
    import httpx
    import openai
    req = httpx.Request("POST", "https://api.openai.com/v1/responses")
    return openai.APIStatusError("x", response=httpx.Response(status, request=req), body=None)


@pytest.mark.parametrize("status,billed", [(400, False), (429, False), (402, False), (501, True), (408, True)])
def test_a_rejection_is_not_billed_and_anything_else_leaves_usage_unknown(status, billed):
    a = OpenAIResponsesProviderAdapter(api_key="k")
    a.TRANSPORT_WAITS = a.UNCERTAIN_WAITS = ()  # a 429 is resent after waits; none here
    a._client = _Client(_status_error(status))
    with pytest.raises(ProviderError) as e:
        asyncio.run(a.invoke({"model": "gpt-5-mini"}))
    assert e.value.not_billed is (not billed)


def test_a_connection_that_never_opened_is_retried_freely_and_a_lost_one_under_the_cap():
    import httpx
    import openai
    a = OpenAIResponsesProviderAdapter(api_key="k")
    a.TRANSPORT_WAITS = (0, 0)
    req = httpx.Request("POST", "https://api.openai.com/v1/responses")
    never = openai.APIConnectionError(request=req)
    never.__cause__ = httpx.ConnectError("refused")
    a._client = _Client(never)
    with pytest.raises(ProviderError) as e:
        asyncio.run(a.invoke({}))
    assert e.value.not_billed is True and len(e.value.transport_retries) == 2
    # a connection lost after sending may have been processed: resent under the cap, usage unknown
    # (the PI, October 21, 2026), and still not marked unbilled when every resend fails
    lost = openai.APIConnectionError(request=req)
    lost.__cause__ = httpx.ReadTimeout("lost")
    a._client = _Client(lost)
    a.UNCERTAIN_WAITS = (0, 0, 0)
    with pytest.raises(ProviderError) as e:
        asyncio.run(a.invoke({}))
    assert e.value.not_billed is False
    assert [r["status"] for r in e.value.transport_retries] == ["connection_lost"] * 3
    assert all(r["usage"] == "unknown" for r in e.value.transport_retries)


class _Flaky:
    """Fails with the given exceptions in turn, then answers."""

    def __init__(self, *excs):
        self.responses = self
        self.chat = self
        self.completions = self
        self.excs = list(excs)
        self.calls = 0

    def create(self, **kw):
        self.calls += 1
        if self.excs:
            raise self.excs.pop(0)
        return type("R", (), {"model_dump": lambda self: {"output": [], "status": "completed"}})()


def _unavailable():
    import httpx
    import openai
    req = httpx.Request("POST", "https://api.openai.com/v1/responses")
    return openai.APIStatusError("Unable to verify model access", response=httpx.Response(503, request=req), body=None)


def test_a_503_is_retried_in_the_call_and_each_attempt_is_recorded():
    a = OpenAIResponsesProviderAdapter(api_key="k")
    a.UNCERTAIN_WAITS = (0, 0, 0)
    a._client = _Flaky(_unavailable(), _unavailable())
    raw = asyncio.run(a.invoke({}))
    assert a._client.calls == 3
    assert [r["status"] for r in raw.transport_retries] == [503, 503]
    assert all(r["usage"] == "unknown" for r in raw.transport_retries)


def test_a_503_that_persists_stops_with_usage_unknown():
    a = OpenAIResponsesProviderAdapter(api_key="k")
    a.UNCERTAIN_WAITS = (0, 0, 0)
    a._client = _Flaky(*[_unavailable() for _ in range(4)])
    with pytest.raises(ProviderError) as e:
        asyncio.run(a.invoke({}))
    assert e.value.not_billed is False and len(e.value.transport_retries) == 3 and a._client.calls == 4


@pytest.mark.parametrize("status,billed,calls", [(429, False, 6), (400, False, 1), (501, True, 1)])
def test_chat_completions_follow_the_same_rules_without_sdk_retries(status, billed, calls, monkeypatch):
    """A 429 was not processed: since the consolidation (October 19, 2026) it is resent after the
    transport waits, unbilled, as T1's 7905467 asked; it still fails unbilled when the waits run out."""
    from oaos2.models.adapters.openai import OpenAIProviderAdapter
    from oaos2.models.adapters.openai_compatible import OpenRouterProviderAdapter
    for cls in (OpenAIProviderAdapter, OpenRouterProviderAdapter):
        a = cls(api_key="k")
        a.TRANSPORT_WAITS = (0, 0, 0, 0, 0)
        a._client = _Flaky(*[_status_error(status) for _ in range(6)])
        with pytest.raises(ProviderError) as e:
            asyncio.run(a.invoke({"model": "m"}))
        assert e.value.not_billed is (not billed) and a._client.calls == calls
    a = OpenAIProviderAdapter(api_key="k")
    a.UNCERTAIN_WAITS = (0,)
    a._client = _Flaky(_unavailable())
    assert asyncio.run(a.invoke({})).transport_retries[0]["status"] == 503
    import openai
    made = {}
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: made.update(kw) or object())
    OpenRouterProviderAdapter(api_key="k")._ensure_client()
    assert made["max_retries"] == 0  # the SDK's silent resends are off


def _timeout():
    import httpx
    import openai
    return openai.APITimeoutError(request=httpx.Request("POST", "https://api.openai.com/v1/responses"))


def test_a_timeout_is_retried_under_the_reservation_with_usage_unknown():
    a = OpenAIResponsesProviderAdapter(api_key="k")
    a.UNCERTAIN_WAITS = (0, 0, 0)
    a._client = _Flaky(_timeout(), _timeout())
    raw = asyncio.run(a.invoke({}))
    assert a._client.calls == 3 and [r["status"] for r in raw.transport_retries] == ["timeout", "timeout"]
    assert all(r["usage"] == "unknown" for r in raw.transport_retries)
    a._client = _Flaky(*[_timeout() for _ in range(4)])
    with pytest.raises(ProviderError) as e:
        asyncio.run(a.invoke({}))
    assert e.value.not_billed is False and len(e.value.transport_retries) == 3


def test_clients_wait_five_minutes_not_the_sdks_ten(monkeypatch):
    import openai
    from oaos2.models.adapters.openai import OpenAIProviderAdapter
    made = []
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: made.append(kw) or object())
    OpenAIResponsesProviderAdapter(api_key="k")._ensure_client()
    OpenAIProviderAdapter(api_key="k")._ensure_client()
    assert [m["timeout"] for m in made] == [300.0, 300.0] and all(m["max_retries"] == 0 for m in made)


@pytest.mark.parametrize("status", [502, 520, 500])
def test_gateway_errors_are_retried_like_a_503(status):
    from oaos2.models.adapters.openai import OpenAIProviderAdapter
    a = OpenAIProviderAdapter(api_key="k")
    a.UNCERTAIN_WAITS = (0, 0, 0)
    a._client = _Flaky(_status_error(status))
    raw = asyncio.run(a.invoke({}))
    assert a._client.calls == 2 and raw.transport_retries[0]["status"] == status
    assert raw.transport_retries[0]["usage"] == "unknown"


def _flagged(status=400):
    import httpx
    import openai
    req = httpx.Request("POST", "https://api.openai.com/v1/responses")
    return openai.APIStatusError(
        "Error code: 400 - Invalid prompt: your prompt was flagged as potentially violating our usage policy.",
        response=httpx.Response(status, request=req), body=None)


def test_a_prompt_the_provider_flags_comes_back_as_a_refusal_not_an_error():
    a = OpenAIResponsesProviderAdapter(api_key="k")
    a._client = _Flaky(_flagged())
    raw = asyncio.run(a.invoke({}))
    assert raw.payload["refused_prompt"] is True and "flagged" in raw.payload["provider_message"]
    r = a.normalize(raw, _req(), "r")
    assert r.stop_reason == "refusal" and r.content_blocks == [] and (r.usage.input, r.usage.output) == (0, 0)
    from oaos2.models.adapters.openai import OpenAIProviderAdapter
    from oaos2.models.adapters.openai_compatible import OpenRouterProviderAdapter
    for cls in (OpenAIProviderAdapter, OpenRouterProviderAdapter):
        c = cls(api_key="k")
        c._client = _Flaky(_flagged(403))
        raw = asyncio.run(c.invoke({}))
        assert c.normalize(raw, _req(), "r").stop_reason == "refusal"


def test_an_ordinary_bad_request_is_still_an_error():
    a = OpenAIResponsesProviderAdapter(api_key="k")
    a._client = _Flaky(_status_error(400))
    with pytest.raises(ProviderError) as e:
        asyncio.run(a.invoke({}))
    assert e.value.not_billed is True


def test_a_call_still_open_at_its_deadline_is_abandoned_closed_and_retried_like_a_timeout():
    """October 16, 2026: a Kimi call through OpenRouter ran 57.5 minutes, the per-read timeout never firing."""
    import time

    from oaos2.models.adapters.base import invoke_under_policy
    from oaos2.models.adapters.openai import OpenAIProviderAdapter

    class _Resp:
        def model_dump(self):
            return {"ok": True}

    calls, closed = [], []

    def create():
        calls.append(1)
        if len(calls) == 1:
            time.sleep(0.5)  # the runaway call
        return _Resp()

    a = OpenAIProviderAdapter(api_key="k")
    raw = asyncio.run(invoke_under_policy(create, a._classify, "x", transport_waits=(), uncertain_waits=(0,),
                                          deadline_s=0.1, on_deadline=lambda: closed.append(1)))
    assert raw.payload == {"ok": True} and len(calls) == 2 and closed == [1]
    assert raw.transport_retries[0]["status"] == "deadline" and raw.transport_retries[0]["usage"] == "unknown"

    def always_slow():
        time.sleep(0.3)
        return _Resp()
    with pytest.raises(ProviderError) as e:
        asyncio.run(invoke_under_policy(always_slow, a._classify, "x", transport_waits=(), uncertain_waits=(0,),
                                        deadline_s=0.05))
    assert e.value.not_billed is False and [r["status"] for r in e.value.transport_retries] == ["deadline"]


def test_both_adapters_close_their_client_on_a_deadline():
    from oaos2.models.adapters.openai import OpenAIProviderAdapter
    for cls in (OpenAIProviderAdapter, OpenAIResponsesProviderAdapter):
        a = cls(api_key="k")
        closed = []
        a._client = type("C", (), {"close": lambda self: closed.append(1)})()
        a._drop_client()
        assert a._client is None and closed == [1]
        a._drop_client()  # nothing open: no error


def test_tool_choice_is_sent_only_when_set():
    """G5, October 19: gpt-5-mini through this adapter ended most turns with a status report; ``tool_choice``
    "required" makes each call that offers tools call one. Unset, nothing is sent."""
    a = OpenAIResponsesProviderAdapter()
    assert "tool_choice" not in a.translate(_req())
    a.tool_choice = "required"
    assert a.translate(_req())["tool_choice"] == "required"


def test_inbox_as_tool_result_sends_later_user_messages_as_read_notes_results():
    """G5, October 19: gpt-5-mini answered incoming notes as if a person had written. With the option, each user
    message after the first reaches the model as a ``read_notes`` result; off, the request is unchanged."""
    req = _req()
    req.messages.append(NeutralMessage("user", [NeutralBlock(kind="text", text="# New messages\n[note 4 from water_team] done")]))
    a = OpenAIResponsesProviderAdapter()
    off = a.translate(req)["input"]
    assert off[-1] == {"role": "user", "content": "# New messages\n[note 4 from water_team] done"}
    a.inbox_as_tool_result = True
    on = a.translate(req)["input"]
    assert on[0] == off[0] and on[0]["role"] == "user"            # the first user message stays one
    assert on[:-2] == off[:-1]
    call, out = on[-2], on[-1]
    assert call["type"] == "function_call" and call["name"] == "read_notes"
    assert out == {"type": "function_call_output", "call_id": call["call_id"],
                   "output": "# New messages\n[note 4 from water_team] done"}
