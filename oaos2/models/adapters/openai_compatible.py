"""Connect OpenAI-compatible providers through the shared Chat Completions adapter.

Subclasses select a base URL, credential variable, and capability declarations.
Removing the first model_ref prefix preserves the provider's remaining model ID,
including slashes. Shared translation and host-side call behavior come from
OpenAIProviderAdapter.

Capability defaults must be checked for the selected model. Cached usage is
recorded if returned, even where cache support is not advertised. Provider tests
apply to exact model references; see docs/mechanism/DEFERRED.md §7 for recorded
checks and scripts/run_provider_parity.py for the comparison procedure."""

from __future__ import annotations

from oaos2.models.adapters.base import ModelBackendCapabilities
from oaos2.models.adapters.openai import OpenAIProviderAdapter

# Open-weight models that reason by default unless told otherwise. Asked for no reasoning (a memory recap), they are
# sent the lowest effort these hosts take: GLM-5.3-Flash on Together spent 182 of 185 recaps' whole output allowance
# reasoning and returned no recap (October 12, 2026), which left its labs evicting old outputs at nearly every turn.
REASONS_BY_DEFAULT = ("glm-", "deepseek-", "qwen3", "kimi-", "gpt-oss", "minimax-")


class _OpenWeightHost(OpenAIProviderAdapter):
    def no_reasoning_extra(self, model: str) -> dict:
        name = model.lower().rsplit("/", 1)[-1]
        return {"reasoning_effort": "low"} if name.startswith(REASONS_BY_DEFAULT) else {}


class TogetherProviderAdapter(_OpenWeightHost):
    provider_id = "together"
    base_url = "https://api.together.xyz/v1"
    api_key_env = "TOGETHER_API_KEY"

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.capabilities = ModelBackendCapabilities(
            reasoning_kind="summary",
            context_window=128_000,       # floor claim; confirm per model
            supports_tools=True,
            provider_seed_support=True,   # Together honours a request seed (best-effort)
            prompt_cache_support=False,   # no cached-token reporting contract
            satisfiable_exposures=frozenset({"reasoning_tokens_to_agent"}),
        )


class OpencodeProviderAdapter(_OpenWeightHost):
    """OpenCode Zen gateway. Only the models Zen serves over the OpenAI
    ``chat/completions`` shape (its open-weight catalog — DeepSeek/Qwen/Kimi/
    GLM class) are reachable here; Zen fronts GPT models via the Responses API
    and Claude via the Messages API, which this adapter deliberately does not
    speak (those providers are wired directly)."""
    provider_id = "opencode"
    base_url = "https://opencode.ai/zen/v1"
    api_key_env = "OPENCODE_API_KEY"

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.capabilities = ModelBackendCapabilities(
            reasoning_kind="summary",
            context_window=128_000,       # floor claim; confirm per model
            supports_tools=True,
            provider_seed_support=False,
            prompt_cache_support=False,
            satisfiable_exposures=frozenset({"reasoning_tokens_to_agent"}),
        )


class OpenRouterProviderAdapter(_OpenWeightHost):
    """OpenRouter. A model reference may pin the serving hosts after ``@`` (October 12, 2026):
    ``openrouter/deepseek/deepseek-v4-flash@deepinfra`` or ``…@deepinfra,fireworks``. Pinned requests go only to those
    hosts, never fall back to others, and require a host that supports every parameter sent (tools included), so a
    run is served the same way throughout and is not routed to a slow or tool-less host (the Together runs of October
    12). Unpinned requests still require full parameter support. Reasoning uses OpenRouter's ``reasoning`` field."""
    provider_id = "openrouter"
    base_url = "https://openrouter.ai/api/v1"
    api_key_env = "OPENROUTER_API_KEY"

    def translate(self, req):
        model, _, hosts = req.model_ref.split("/", 1)[-1].partition("@")
        payload = super().translate(req)
        payload["model"] = model
        # No seed, as the capabilities claim: required parameters exclude every host that does not take one (Z.AI's and
        # Together's GLM-5.3-Flash endpoints, October 13, 2026), and a seed is best-effort where it is taken at all.
        payload.pop("seed", None)
        provider = {"require_parameters": True}
        if hosts:
            provider.update({"only": [h.strip() for h in hosts.split(",") if h.strip()], "allow_fallbacks": False})
        extra = {"provider": provider}
        effort = payload.pop("reasoning_effort", None)
        if effort:
            extra["reasoning"] = {"effort": effort}
        payload["extra_body"] = extra
        return payload

    def no_reasoning_extra(self, model: str) -> dict:
        return super().no_reasoning_extra(model.partition("@")[0])

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.capabilities = ModelBackendCapabilities(
            reasoning_kind="summary",
            context_window=128_000,       # floor claim; confirm per model
            supports_tools=True,
            provider_seed_support=False,  # pass-through varies by upstream; claim nothing
            prompt_cache_support=False,
            satisfiable_exposures=frozenset({"reasoning_tokens_to_agent"}),
        )
