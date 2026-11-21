"""LLM entry point for chat replies.

`LLMService` keeps one public API (generate, stream, list models, health, test) and hands the work to the
provider adapters in `app.services.llm`. It owns the parts that are the same for every provider: the circuit
breaker, the document-excerpt fallback and the reply metadata.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Iterable

import httpx  # noqa: F401  (tests patch httpx.AsyncClient through this module)
from loguru import logger

from app.services.llm import common
from app.services.llm.base import ChatRequest, ProviderCredentials, StreamOutcome, UnsupportedModel
from app.services.llm.common import DEFAULT_SYSTEM_PROMPT, NO_CONTEXT_TEXT, REFUSAL_TEXT
from app.services.llm.registry import PROVIDER_IDS, get_provider, provider_for_model

__all__ = [
    "DEFAULT_SYSTEM_PROMPT",
    "LLMService",
    "NO_CONTEXT_TEXT",
    "PROVIDER_IDS",
    "ProviderCredentials",
    "REFUSAL_TEXT",
    "StreamOutcome",
    "UnsupportedModel",
]


def _breaker_key(provider: str, credentials: ProviderCredentials | None) -> str:
    """Circuit state is per credential; the server-wide credential keeps the plain provider name."""
    if credentials is None or credentials.source == "server":
        return provider
    return f"{provider}:{credentials.fingerprint()}"


class LLMService:
    _failure_count: dict[str, int] = {provider_id: 0 for provider_id in PROVIDER_IDS}
    _circuit_open_until: dict[str, datetime | None] = {provider_id: None for provider_id in PROVIDER_IDS}

    # ------------------------------------------------------------------
    # Model identity
    # ------------------------------------------------------------------

    @staticmethod
    def provider_for(model: str) -> str:
        return provider_for_model(model)

    @classmethod
    async def resolve_model(cls, model: str, credentials: ProviderCredentials | None = None) -> str:
        """The model id to store for a conversation. Raises UnsupportedModel with a message safe to show."""
        provider = get_provider(cls.provider_for(model))
        return await provider.resolve_model(model, credentials)

    # ------------------------------------------------------------------
    # Prompt and history
    # ------------------------------------------------------------------

    @staticmethod
    def history_from_messages(
        rows: Iterable[Any],
        *,
        max_messages: int | None = None,
        max_chars: int | None = None,
    ) -> list[dict[str, str]]:
        return common.history_from_messages(rows, max_messages=max_messages, max_chars=max_chars)

    # ------------------------------------------------------------------
    # Public generation API
    # ------------------------------------------------------------------

    @classmethod
    async def generate_chat_reply(
        cls,
        *,
        model: str,
        user_message: str,
        context_lines: list[str],
        history: list[dict[str, str]] | None = None,
        system_prompt: str | None = None,
        credentials: ProviderCredentials | None = None,
    ) -> tuple[str, dict[str, Any]]:
        started_at = time.perf_counter()
        provider_id = cls.provider_for(model)
        provider = get_provider(provider_id)
        if cls._is_circuit_open(provider_id, credentials):
            logger.warning("LLM circuit open provider={provider}; using fallback response", provider=provider_id)
            content = common.fallback_content(context_lines)
            metadata = {
                "provider": provider_id,
                "model": model,
                "error_type": "provider_circuit_open",
                "token_estimate": max(int(len(content.split()) * 1.3), 1),
                "total_tokens": max(int(len(content.split()) * 1.3), 1),
                "latency_ms": int((time.perf_counter() - started_at) * 1000),
            }
            return content, metadata

        usage: dict[str, Any] = {}
        try:
            result = await provider.generate(
                ChatRequest(
                    model=model,
                    user_message=user_message,
                    context_lines=context_lines,
                    history=history,
                    system_prompt=system_prompt,
                ),
                credentials,
            )
            content, usage = result.text, result.usage
            cls._record_success(provider_id, credentials)
        except Exception as exc:
            cls._record_failure(provider_id, credentials)
            error_type = provider.classify_error(exc)
            logger.warning(
                "LLM generation failed provider={provider} model={model} credential={credential} error_type={error_type} request_id={request_id}: {error}",
                provider=provider_id,
                model=model,
                credential=credentials.source if credentials else "server",
                error_type=error_type,
                request_id=getattr(exc, "request_id", None),
                error=str(exc),
            )
            content = common.fallback_content(context_lines)
            usage = {"error_type": error_type}

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        token_estimate = max(int(len(content.split()) * 1.3), 1)
        metadata = {
            "provider": provider_id,
            "model": model,
            "latency_ms": latency_ms,
            "token_estimate": token_estimate,
            **usage,
        }
        if "total_tokens" not in metadata or metadata["total_tokens"] is None:
            metadata["total_tokens"] = token_estimate
        return content, metadata

    @classmethod
    async def stream_chat_reply(
        cls,
        *,
        model: str,
        user_message: str,
        context_lines: list[str],
        history: list[dict[str, str]] | None = None,
        system_prompt: str | None = None,
        outcome: StreamOutcome | None = None,
        credentials: ProviderCredentials | None = None,
    ) -> AsyncIterator[str]:
        provider_id = cls.provider_for(model)
        provider = get_provider(provider_id)
        outcome = outcome if outcome is not None else StreamOutcome()
        try:
            async for part in provider.stream(
                ChatRequest(
                    model=model,
                    user_message=user_message,
                    context_lines=context_lines,
                    history=history,
                    system_prompt=system_prompt,
                ),
                credentials,
                outcome,
            ):
                yield part
        except Exception as exc:
            cls._record_failure(provider_id, credentials)
            outcome.error_type = provider.classify_error(exc)
            raise
        cls._record_success(provider_id, credentials)

    # ------------------------------------------------------------------
    # Health, model listing and connection test
    # ------------------------------------------------------------------

    @classmethod
    async def provider_health(
        cls, credentials_by_provider: dict[str, ProviderCredentials | None] | None = None
    ) -> dict[str, Any]:
        credentials_by_provider = credentials_by_provider or {}
        report: dict[str, Any] = {}
        for provider_id in PROVIDER_IDS:
            credentials = credentials_by_provider.get(provider_id)
            state = await get_provider(provider_id).health(credentials)
            report[provider_id] = {**state, "circuit_open": cls._is_circuit_open(provider_id, credentials)}
        return report

    @classmethod
    async def list_models(
        cls, credentials_by_provider: dict[str, ProviderCredentials | None] | None = None
    ) -> dict[str, list[dict[str, Any]]]:
        credentials_by_provider = credentials_by_provider or {}
        listing: dict[str, list[dict[str, Any]]] = {}
        for provider_id in PROVIDER_IDS:
            models = await get_provider(provider_id).list_models(credentials_by_provider.get(provider_id))
            listing[provider_id] = [{"id": m.id, "name": m.name, "provider": provider_id} for m in models]
        return listing

    @classmethod
    async def test_connection(cls, provider: str, credentials: ProviderCredentials | None) -> dict[str, Any]:
        """Cheap, authenticated check of a provider. Never raises and never puts the key or a raw error in the result."""
        adapter = get_provider(provider)
        if adapter is None:
            return {"ok": False, "error_type": "provider_not_supported", "detail": "This provider is not supported yet."}
        return await adapter.test_connection(credentials)

    # ------------------------------------------------------------------
    # Circuit breaker (per provider and credential)
    # ------------------------------------------------------------------

    @classmethod
    def _record_failure(cls, provider: str, credentials: ProviderCredentials | None = None) -> None:
        key = _breaker_key(provider, credentials)
        cls._failure_count[key] = cls._failure_count.get(key, 0) + 1
        if cls._failure_count[key] >= 3:
            cls._circuit_open_until[key] = datetime.now(tz=timezone.utc) + timedelta(seconds=30)

    @classmethod
    def _record_success(cls, provider: str, credentials: ProviderCredentials | None = None) -> None:
        key = _breaker_key(provider, credentials)
        cls._failure_count[key] = 0
        cls._circuit_open_until[key] = None

    @classmethod
    def _is_circuit_open(cls, provider: str, credentials: ProviderCredentials | None = None) -> bool:
        key = _breaker_key(provider, credentials)
        opened_until = cls._circuit_open_until.get(key)
        if opened_until is None:
            return False
        if datetime.now(tz=timezone.utc) >= opened_until:
            cls._circuit_open_until[key] = None
            return False
        return True
