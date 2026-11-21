"""Ollama adapter: a local server, or Ollama Cloud when the saved credentials carry an API key."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

import httpx
from loguru import logger

from app.core.config import settings
from app.services.llm.base import (
    ChatRequest,
    GenerateResult,
    ModelInfo,
    ProviderCredentials,
    StreamOutcome,
)
from app.services.llm.common import TEST_DETAIL, build_messages, system_text

# Ollama retries cover a server that is still starting or briefly overloaded, nothing else.
OLLAMA_MAX_ATTEMPTS = 2
OLLAMA_RETRY_DELAY_SECONDS = 0.5


class OllamaProvider:
    id = "ollama"
    always_available = True  # the server's OLLAMA_URL is always there
    accepts_base_url = True

    @staticmethod
    def owns(model: str) -> bool:
        # Ollama is where every model name that no other provider claims ends up.
        return True

    @staticmethod
    def normalize_model(model: str) -> str:
        return model.strip()

    @classmethod
    async def resolve_model(cls, model: str, credentials: ProviderCredentials | None) -> str:
        return cls.normalize_model(model)

    @staticmethod
    def server_credentials() -> ProviderCredentials | None:
        return None

    # ------------------------------------------------------------------
    # HTTP plumbing
    # ------------------------------------------------------------------

    @staticmethod
    def _ollama_timeout() -> httpx.Timeout:
        return httpx.Timeout(
            connect=settings.OLLAMA_CONNECT_TIMEOUT_SECONDS,
            read=settings.OLLAMA_READ_TIMEOUT_SECONDS,
            write=10.0,
            pool=5.0,
        )

    @classmethod
    def _ollama_client(cls, credentials: ProviderCredentials | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=cls._ollama_timeout())

    @staticmethod
    def _ollama_base_url(credentials: ProviderCredentials | None) -> str:
        return ((credentials.base_url if credentials and credentials.base_url else settings.OLLAMA_URL) or "").rstrip("/")

    @staticmethod
    def _ollama_headers(credentials: ProviderCredentials | None) -> dict[str, str]:
        """Ollama Cloud (https://ollama.com/api) authenticates with a Bearer API key; a local Ollama needs none."""
        if credentials and credentials.api_key:
            return {"Authorization": f"Bearer {credentials.api_key}"}
        return {}

    @staticmethod
    def _ollama_probe_timeout() -> httpx.Timeout:
        return httpx.Timeout(connect=settings.OLLAMA_CONNECT_TIMEOUT_SECONDS, read=10.0, write=5.0, pool=5.0)

    @staticmethod
    def _ollama_payload(request: ChatRequest, *, stream: bool) -> dict[str, Any]:
        messages = build_messages(
            history=request.history, user_message=request.user_message, context_lines=request.context_lines
        )
        return {
            "model": request.model,
            "stream": stream,
            "messages": [{"role": "system", "content": system_text(request.system_prompt)}, *messages],
        }

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    @classmethod
    async def generate(cls, request: ChatRequest, credentials: ProviderCredentials | None = None) -> GenerateResult:
        payload = cls._ollama_payload(request, stream=False)
        url = f"{cls._ollama_base_url(credentials)}/api/chat"
        headers = cls._ollama_headers(credentials)
        data: dict[str, Any] = {}
        for attempt in range(1, OLLAMA_MAX_ATTEMPTS + 1):
            try:
                async with cls._ollama_client(credentials) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                break
            except (httpx.ConnectError, httpx.ConnectTimeout):
                if attempt == OLLAMA_MAX_ATTEMPTS:
                    raise
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500 or attempt == OLLAMA_MAX_ATTEMPTS:
                    raise
            await asyncio.sleep(OLLAMA_RETRY_DELAY_SECONDS)

        message = data.get("message", {})
        text = str(message.get("content", "")).strip()
        if not text:
            raise RuntimeError("Empty Ollama response")
        prompt_tokens = int(data.get("prompt_eval_count") or 0)
        completion_tokens = int(data.get("eval_count") or 0)
        return GenerateResult(
            text,
            {
                "input_tokens": prompt_tokens or None,
                "output_tokens": completion_tokens or None,
                "total_tokens": (prompt_tokens + completion_tokens) or None,
            },
        )

    @classmethod
    async def stream(
        cls,
        request: ChatRequest,
        credentials: ProviderCredentials | None = None,
        outcome: StreamOutcome | None = None,
    ) -> AsyncIterator[str]:
        payload = cls._ollama_payload(request, stream=True)
        url = f"{cls._ollama_base_url(credentials)}/api/chat"
        headers = cls._ollama_headers(credentials)
        async with cls._ollama_client(credentials) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    delta = str((chunk.get("message") or {}).get("content", ""))
                    if delta:
                        yield delta
                    if chunk.get("done") and outcome is not None:
                        outcome.stop_reason = str(chunk.get("done_reason") or "stop")
                        outcome.input_tokens = int(chunk.get("prompt_eval_count") or 0) or None
                        outcome.output_tokens = int(chunk.get("eval_count") or 0) or None

    # ------------------------------------------------------------------
    # Models, health, test, errors
    # ------------------------------------------------------------------

    @classmethod
    async def list_models(cls, credentials: ProviderCredentials | None) -> list[ModelInfo]:
        models: list[ModelInfo] = []
        try:
            async with httpx.AsyncClient(timeout=cls._ollama_probe_timeout()) as client:
                response = await client.get(
                    f"{cls._ollama_base_url(credentials)}/api/tags", headers=cls._ollama_headers(credentials)
                )
                response.raise_for_status()
                payload = response.json()
                for model in payload.get("models", []) or []:
                    name = model.get("name")
                    if name:
                        models.append(ModelInfo(id=name, name=name))
        except Exception as exc:
            logger.warning("Unable to list Ollama models: {error_type}", error_type=cls.classify_error(exc))
        return models

    @classmethod
    async def health(cls, credentials: ProviderCredentials | None) -> dict[str, Any]:
        healthy = False
        try:
            async with httpx.AsyncClient(timeout=cls._ollama_probe_timeout()) as client:
                response = await client.get(
                    f"{cls._ollama_base_url(credentials)}/api/tags", headers=cls._ollama_headers(credentials)
                )
                healthy = response.status_code == 200
        except Exception as exc:
            logger.debug("Ollama health probe failed: {error_type}", error_type=cls.classify_error(exc))
        return {"healthy": healthy}

    @classmethod
    async def test_connection(cls, credentials: ProviderCredentials | None) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=cls._ollama_probe_timeout()) as client:
                response = await client.get(
                    f"{cls._ollama_base_url(credentials)}/api/tags", headers=cls._ollama_headers(credentials)
                )
                response.raise_for_status()
            return {"ok": True, "error_type": None, "detail": "Connected."}
        except Exception as exc:
            error_type = cls.classify_error(exc)
            logger.warning(
                "Provider connection test failed provider=ollama error_type={error_type}", error_type=error_type
            )
            return {"ok": False, "error_type": error_type, "detail": TEST_DETAIL.get(error_type, TEST_DETAIL["provider_error"])}

    @staticmethod
    def classify_error(exc: Exception) -> str:
        if isinstance(exc, httpx.TimeoutException):
            return "provider_timeout"
        if isinstance(exc, httpx.HTTPStatusError):
            if exc.response.status_code in (401, 403):
                return "provider_auth_error"
            if exc.response.status_code == 429:
                return "provider_rate_limited"
            return "provider_http_error"
        return "provider_error"
