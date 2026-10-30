"""Register provider adapters for the common model-call interface.

Real adapters translate a request, make one provider call, and normalize the
reply. Credentials remain on the host; the platform retains control of tools
and subsequent turns. StubProviderAdapter simulates calls without network or
spending. Register new provider namespaces here, not in the agent loop."""

from typing import Callable

from oaos2.models.adapters.base import (
    ModelBackendCapabilities,
    ProviderAdapter,
    ProviderError,
    RawProviderResponse,
)
from oaos2.models.adapters.stub import StubProviderAdapter

# ---------------------------------------------------------------------------
# Open provider registry (model_ref namespace → adapter class).  THE one place
# a live backend is dispatched from: the runner resolves through here, so a new
# provider is an adapter module + one registration — never a runner edit.
# Factories are lazy so registering a namespace does not import its SDK; the
# import happens only when that provider is actually resolved for a live run.
# ---------------------------------------------------------------------------

_PROVIDER_FACTORIES: dict[str, Callable[[], type]] = {}


def register_provider_adapter(namespace: str, load: Callable[[], type]) -> None:
    """Register a lazy adapter factory under its model_ref namespace.

    Idempotent for the same factory; refuses a CONFLICTING re-registration —
    two plugins may not fight over one namespace (the coordination-registry
    rule, applied to providers)."""
    if not namespace:
        raise ValueError("provider namespace must be non-empty")
    existing = _PROVIDER_FACTORIES.get(namespace)
    if existing is not None and existing is not load:
        raise ValueError(f"provider namespace {namespace!r} is already registered")
    _PROVIDER_FACTORIES[namespace] = load


def registered_provider_namespaces() -> frozenset[str]:
    return frozenset(_PROVIDER_FACTORIES)


def resolve_provider_adapter(namespace: str, *, model_ref: str = "") -> type:
    """Resolve a namespace to its adapter class — FAILS CLOSED on unknown."""
    load = _PROVIDER_FACTORIES.get(namespace)
    if load is None:
        raise ValueError(
            f"unknown provider namespace {namespace!r} in model_ref "
            f"{model_ref or namespace!r} (registered: {sorted(_PROVIDER_FACTORIES)})")
    return load()


def _load_anthropic() -> type:
    from oaos2.models.adapters.anthropic import AnthropicProviderAdapter
    return AnthropicProviderAdapter


def _load_openai() -> type:
    from oaos2.models.adapters.openai import OpenAIProviderAdapter
    return OpenAIProviderAdapter


def _load_openai_responses() -> type:
    from oaos2.models.adapters.openai_responses import OpenAIResponsesProviderAdapter
    return OpenAIResponsesProviderAdapter


def _load_together() -> type:
    from oaos2.models.adapters.openai_compatible import TogetherProviderAdapter
    return TogetherProviderAdapter


def _load_openrouter() -> type:
    from oaos2.models.adapters.openai_compatible import OpenRouterProviderAdapter
    return OpenRouterProviderAdapter


def _load_opencode() -> type:
    from oaos2.models.adapters.openai_compatible import OpencodeProviderAdapter
    return OpencodeProviderAdapter


def _load_stub() -> type:
    return StubProviderAdapter


register_provider_adapter("anthropic", _load_anthropic)
register_provider_adapter("openai", _load_openai)
register_provider_adapter("openai_responses", _load_openai_responses)  # reasoning summaries; tools with reasoning
register_provider_adapter("together", _load_together)
register_provider_adapter("openrouter", _load_openrouter)
register_provider_adapter("opencode", _load_opencode)
register_provider_adapter("stub", _load_stub)  # zero-cost; lets harnesses resolve uniformly

__all__ = [
    "ModelBackendCapabilities",
    "ProviderAdapter",
    "ProviderError",
    "RawProviderResponse",
    "StubProviderAdapter",
    "register_provider_adapter",
    "registered_provider_namespaces",
    "resolve_provider_adapter",
]
