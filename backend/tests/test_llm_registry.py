from __future__ import annotations

import pytest

from app.services.llm import PROVIDER_IDS, get_provider, provider_for_model
from app.services.llm_service import LLMService


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("claude-sonnet-5-5", "anthropic"),
        ("Claude-Opus-5-5", "anthropic"),
        ("gpt-5.5", "openai"),
        ("GPT-5.5", "openai"),
        ("gpt-5.4-mini", "openai"),
        ("o3", "openai"),
        ("o4-mini", "openai"),
        ("chatgpt-4o-latest", "openai"),
        # A tag means an Ollama model, even when the name starts like an OpenAI one.
        ("gpt-oss:20b", "ollama"),
        ("gpt-oss:120b", "ollama"),
        ("llama3.2:3b-instruct-q4_K_M", "ollama"),
        ("gemma3:4b", "ollama"),
        ("qwen2.5:14b", "ollama"),
        ("omega:latest", "ollama"),
        ("mistral", "ollama"),
        # Documented limit: an Ollama name with no tag that looks like an OpenAI id is routed to OpenAI.
        ("gpt-oss", "openai"),
    ],
)
def test_models_are_routed_to_the_right_provider(model, expected):
    assert provider_for_model(model) == expected
    assert LLMService.provider_for(model) == expected


def test_every_provider_id_has_an_adapter_with_the_full_interface():
    assert PROVIDER_IDS == ("anthropic", "openai", "ollama_cloud", "ollama")
    for provider_id in PROVIDER_IDS:
        adapter = get_provider(provider_id)
        assert adapter.id == provider_id
        for method in (
            "owns", "normalize_model", "resolve_model", "generate", "stream", "list_models",
            "health", "test_connection", "classify_error", "server_credentials",
        ):
            assert callable(getattr(adapter, method)), f"{provider_id} lacks {method}"
        assert isinstance(adapter.always_available, bool) and isinstance(adapter.accepts_base_url, bool)
        assert adapter.label


def test_unknown_provider_has_no_adapter():
    assert get_provider("mistral") is None


def test_only_the_local_ollama_accepts_a_base_url_and_is_always_available():
    assert [p for p in PROVIDER_IDS if get_provider(p).accepts_base_url] == ["ollama"]
    assert [p for p in PROVIDER_IDS if get_provider(p).always_available] == ["ollama"]


@pytest.mark.asyncio
async def test_resolve_model_goes_through_the_owning_provider():
    assert await LLMService.resolve_model("llama3.2:3b ") == "llama3.2:3b"
    assert await LLMService.resolve_model("claude-sonnet-5.5") == "claude-sonnet-5-5"


def test_the_reasoning_effort_setting_accepts_only_known_levels(monkeypatch):
    from pydantic import ValidationError

    from app.core.config import Settings

    assert Settings(OPENAI_REASONING_EFFORT=" LOW ").OPENAI_REASONING_EFFORT == "low"
    assert Settings(OPENAI_REASONING_EFFORT="").OPENAI_REASONING_EFFORT == ""
    with pytest.raises(ValidationError, match="OPENAI_REASONING_EFFORT must be empty or one of"):
        Settings(OPENAI_REASONING_EFFORT="turbo")
