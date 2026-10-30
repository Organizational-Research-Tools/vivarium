"""OpenAI-compatible endpoint adapters (together/openrouter) — offline canaries."""

from __future__ import annotations

import pytest

from oaos2.models.adapters import registered_provider_namespaces, resolve_provider_adapter
from oaos2.models.adapters.base import ProviderError
from oaos2.models.adapters.openai import OpenAIProviderAdapter, _load_api_key
from oaos2.models.types import ModelRequest, NeutralBlock, NeutralMessage, SamplingParams
from oaos2.ulid import new_ulid


def _req(model_ref: str) -> ModelRequest:
    return ModelRequest(
        call_id=new_ulid(), model_ref=model_ref,
        messages=[NeutralMessage("user", [NeutralBlock(kind="text", text="hi")])],
        tools=[], sampling=SamplingParams(max_output_tokens=16),
    )


def test_namespaces_registered_and_resolve() -> None:
    names = registered_provider_namespaces()
    assert {"anthropic", "openai", "together", "openrouter", "stub"} <= names
    together = resolve_provider_adapter("together")
    openrouter = resolve_provider_adapter("openrouter")
    assert issubclass(together, OpenAIProviderAdapter)
    assert issubclass(openrouter, OpenAIProviderAdapter)
    assert together.base_url == "https://api.together.xyz/v1"
    assert openrouter.base_url == "https://openrouter.ai/api/v1"
    assert together.api_key_env == "TOGETHER_API_KEY"
    assert openrouter.api_key_env == "OPENROUTER_API_KEY"


def test_translate_strips_namespace_and_keeps_multislash_model_ids() -> None:
    together = resolve_provider_adapter("together")()
    payload = together.translate(_req("together/meta-llama/Llama-3.3-70B-Instruct-Turbo"))
    assert payload["model"] == "meta-llama/Llama-3.3-70B-Instruct-Turbo"
    openrouter = resolve_provider_adapter("openrouter")()
    assert openrouter.translate(_req("openrouter/openai/gpt-5"))["model"] == "openai/gpt-5"


def test_missing_key_error_names_the_right_variable(monkeypatch) -> None:
    monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
    try:  # keep the host .env out of the probe — hermetic either way
        import dotenv
        monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    except ImportError:
        pass
    with pytest.raises(ProviderError, match="TOGETHER_API_KEY"):
        _load_api_key("TOGETHER_API_KEY")


def test_conservative_capability_claims() -> None:
    together = resolve_provider_adapter("together")()
    openrouter = resolve_provider_adapter("openrouter")()
    for a in (together, openrouter):
        assert a.capabilities.prompt_cache_support is False
        assert a.capabilities.context_window == 128_000
    assert together.capabilities.provider_seed_support is True
    assert openrouter.capabilities.provider_seed_support is False
