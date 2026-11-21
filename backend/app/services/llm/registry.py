"""Finds the provider for a model id and hands out adapters by id."""

from __future__ import annotations

from app.services.llm.anthropic_provider import AnthropicProvider
from app.services.llm.base import LLMProvider
from app.services.llm.ollama_provider import OllamaProvider
from app.services.llm.openai_provider import OpenAIProvider

# Display order, and the only place provider ids are listed.
_PROVIDERS: dict[str, LLMProvider] = {
    "anthropic": AnthropicProvider(),
    "openai": OpenAIProvider(),
    "ollama": OllamaProvider(),
}
PROVIDER_IDS: tuple[str, ...] = tuple(_PROVIDERS)


def get_provider(provider_id: str) -> LLMProvider | None:
    return _PROVIDERS.get(provider_id)


def provider_for_model(model: str) -> str:
    """Which provider runs this model id. Ollama takes every name no other adapter claims."""
    normalized = model.strip().lower()
    for provider_id, provider in _PROVIDERS.items():
        if provider_id != "ollama" and provider.owns(normalized):
            return provider_id
    return "ollama"
