"""Ollama Cloud: the same wire format as a local Ollama, at a fixed address with an API key.

The address is a constant, never read from saved settings, so a user's key can only ever be sent to
ollama.com. Hosted model names have no `-cloud` suffix.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, AsyncIterator

from app.core.config import settings
from app.services.llm.base import (
    ChatRequest,
    GenerateResult,
    ModelInfo,
    ProviderCredentials,
    StreamOutcome,
    UnsupportedModel,
)
from app.services.llm.common import MODEL_LIST_FAILURE_TTL_SECONDS
from app.services.llm.ollama_provider import OllamaProvider

OLLAMA_CLOUD_URL = "https://ollama.com"


class OllamaCloudProvider(OllamaProvider):
    id = "ollama_cloud"
    label = "Ollama Cloud"
    always_available = False
    accepts_base_url = False

    # Live model lists, cached per credential so one user's list is never served to another.
    _model_cache: dict[str, tuple[float, list[ModelInfo]]] = {}

    @staticmethod
    def owns(model: str) -> bool:
        # Names are shared with a local Ollama, so a cloud model is chosen by provider, never inferred.
        return False

    @staticmethod
    def _has_key(credentials: ProviderCredentials | None) -> bool:
        return bool(credentials and credentials.api_key)

    @staticmethod
    def _ollama_base_url(credentials: ProviderCredentials | None) -> str:
        return OLLAMA_CLOUD_URL  # a saved base URL, if any row has one, is ignored on purpose

    @classmethod
    def _require_key(cls, credentials: ProviderCredentials | None) -> None:
        if not cls._has_key(credentials):
            raise RuntimeError("No Ollama Cloud API key is configured")

    @classmethod
    async def resolve_model(cls, model: str, credentials: ProviderCredentials | None) -> str:
        selected = cls.normalize_model(model)
        if not cls._has_key(credentials):
            raise UnsupportedModel("No Ollama Cloud API key is saved. Add one in Settings to use Ollama Cloud models.")
        listed = {entry.id for entry in await cls.list_models(credentials)}
        # An empty list means the listing failed or the account has none; the chat call will report the real problem.
        if listed and selected not in listed:
            raise UnsupportedModel(f"Unsupported Ollama Cloud model. Allowed: {sorted(listed)}")
        return selected

    @classmethod
    async def generate(cls, request: ChatRequest, credentials: ProviderCredentials | None = None) -> GenerateResult:
        cls._require_key(credentials)
        return await super().generate(request, credentials)

    @classmethod
    async def stream(
        cls,
        request: ChatRequest,
        credentials: ProviderCredentials | None = None,
        outcome: StreamOutcome | None = None,
    ) -> AsyncIterator[str]:
        cls._require_key(credentials)
        async for part in super().stream(request, credentials, outcome):
            yield part

    @classmethod
    async def list_models(cls, credentials: ProviderCredentials | None) -> list[ModelInfo]:
        if not cls._has_key(credentials):
            return []
        cache_key = hashlib.sha256((credentials.api_key or "").encode("utf-8")).hexdigest()[:12]
        now = time.monotonic()
        cached = OllamaCloudProvider._model_cache.get(cache_key)
        if cached is not None and cached[0] > now:
            return cached[1]
        models = await super().list_models(credentials)
        # `super().list_models` logs and returns [] on failure; a failure is remembered only briefly.
        ttl = settings.LLM_MODEL_LIST_TTL_SECONDS if models else MODEL_LIST_FAILURE_TTL_SECONDS
        OllamaCloudProvider._model_cache[cache_key] = (now + ttl, models)
        return models

    @classmethod
    async def health(cls, credentials: ProviderCredentials | None) -> dict[str, Any]:
        if not cls._has_key(credentials):
            return {"healthy": False}
        return await super().health(credentials)

    @classmethod
    async def test_connection(cls, credentials: ProviderCredentials | None) -> dict[str, Any]:
        if not cls._has_key(credentials):
            return {"ok": False, "error_type": "not_configured", "detail": "No Ollama Cloud API key is saved."}
        return await super().test_connection(credentials)
