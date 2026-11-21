"""Anthropic (Claude) adapter, using the official SDK."""

from __future__ import annotations

import hashlib
import re
import time
from typing import Any, AsyncIterator

import anthropic
import httpx
from loguru import logger

from app.core.config import settings
from app.services.llm.base import (
    ChatRequest,
    GenerateResult,
    ModelInfo,
    ProviderCredentials,
    StreamOutcome,
    UnsupportedModel,
)
from app.services.llm.common import (
    MODEL_LIST_FAILURE_TTL_SECONDS,
    REFUSAL_TEXT,
    TEST_DETAIL,
    build_messages,
    system_text,
)


class AnthropicProvider:
    id = "anthropic"
    always_available = False

    # Live Claude model lists, cached per credential so one user's list is never served to another.
    _model_cache: dict[str, tuple[float, list[dict[str, str]]]] = {}
    # Whether each Claude model accepts the configured effort level, learned from the Models API.
    # Unknown models are assumed to accept it (the configured, current models all do).
    _effort_ok: dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Model identity
    # ------------------------------------------------------------------

    @staticmethod
    def owns(model: str) -> bool:
        return model.strip().lower().startswith("claude-")

    @staticmethod
    def normalize_model(model: str) -> str:
        """Map legacy dotted IDs (claude-sonnet-4.6) to the API form (claude-sonnet-4-6)."""
        return re.sub(r"(?<=\d)\.(?=\d)", "-", model.strip())

    @staticmethod
    def configured_models() -> list[dict[str, str]]:
        ids = [settings.CLAUDE_SONNET_MODEL, settings.CLAUDE_OPUS_MODEL, settings.CLAUDE_HAIKU_MODEL]
        seen: list[str] = []
        for model_id in ids:
            if model_id and model_id not in seen:
                seen.append(model_id)
        return [{"id": model_id, "name": model_id} for model_id in seen]

    @staticmethod
    def _api_key(credentials: ProviderCredentials | None) -> str:
        return (credentials.api_key if credentials and credentials.api_key else settings.CLAUDE_API_KEY) or ""

    @classmethod
    def server_credentials(cls) -> ProviderCredentials | None:
        if settings.ALLOW_SERVER_PROVIDER_KEYS and settings.CLAUDE_API_KEY:
            return ProviderCredentials(api_key=settings.CLAUDE_API_KEY, source="server")
        return None

    @classmethod
    async def model_catalog(cls, credentials: ProviderCredentials | None = None) -> list[dict[str, str]]:
        """Claude models from the Anthropic Models API when a key is available, else the configured IDs."""
        static = cls.configured_models()
        api_key = cls._api_key(credentials)
        if not api_key:
            return static

        cache_key = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]
        now = time.monotonic()
        cached = AnthropicProvider._model_cache.get(cache_key)
        if cached is not None and cached[0] > now:
            return cached[1]

        try:
            entries: list[dict[str, str]] = []
            effort_ok: dict[str, bool] = {}
            async with cls._anthropic_client(credentials=credentials, timeout=10.0, max_retries=0) as client:
                async for info in client.models.list():
                    if info.id.startswith("claude-"):
                        entries.append({"id": info.id, "name": getattr(info, "display_name", None) or info.id})
                        effort_ok[info.id] = cls._supports_effort(info)
            if not entries:
                raise RuntimeError("Models API returned no Claude models")
            AnthropicProvider._model_cache[cache_key] = (now + settings.LLM_MODEL_LIST_TTL_SECONDS, entries)
            AnthropicProvider._effort_ok = {**AnthropicProvider._effort_ok, **effort_ok}
            return entries
        except Exception as exc:
            logger.warning(
                "Could not list Claude models from the API; using configured IDs: {error_type}",
                error_type=cls.classify_error(exc),
            )
            AnthropicProvider._model_cache[cache_key] = (now + MODEL_LIST_FAILURE_TTL_SECONDS, static)
            return static

    @staticmethod
    def _supports_effort(info: Any) -> bool:
        """True when the model's reported capabilities accept the configured effort level (or say nothing)."""
        effort = getattr(getattr(info, "capabilities", None), "effort", None)
        if effort is None:
            return True
        if not effort.supported:
            return False
        level = getattr(effort, settings.CLAUDE_EFFORT, None)
        return level is None or bool(level.supported)

    @classmethod
    async def allowed_models(cls, credentials: ProviderCredentials | None = None) -> set[str]:
        catalog = await cls.model_catalog(credentials)
        return {entry["id"] for entry in catalog} | {entry["id"] for entry in cls.configured_models()}

    @classmethod
    async def resolve_model(cls, model: str, credentials: ProviderCredentials | None) -> str:
        selected = cls.normalize_model(model)
        allowed = await cls.allowed_models(credentials)
        if selected not in allowed:
            raise UnsupportedModel(f"Unsupported Anthropic model. Allowed: {sorted(allowed)}")
        return selected

    @classmethod
    async def list_models(cls, credentials: ProviderCredentials | None) -> list[ModelInfo]:
        return [ModelInfo(id=entry["id"], name=entry["name"]) for entry in await cls.model_catalog(credentials)]

    # ------------------------------------------------------------------
    # Requests
    # ------------------------------------------------------------------

    @classmethod
    def _anthropic_client(
        cls,
        *,
        credentials: ProviderCredentials | None = None,
        timeout: float | None = None,
        max_retries: int = 2,
    ) -> anthropic.AsyncAnthropic:
        api_key = cls._api_key(credentials)
        if not api_key:
            raise RuntimeError("No Claude API key is configured")
        return anthropic.AsyncAnthropic(
            api_key=api_key,
            timeout=timeout if timeout is not None else settings.ANTHROPIC_REQUEST_TIMEOUT_SECONDS,
            max_retries=max_retries,
        )

    @classmethod
    def _anthropic_request(cls, request: ChatRequest) -> dict[str, Any]:
        # No temperature/top_p, thinking switch or prefill: the current Claude models reject them.
        resolved = cls.normalize_model(request.model)
        body: dict[str, Any] = {
            "model": resolved,
            "max_tokens": settings.CLAUDE_MAX_OUTPUT_TOKENS,
            "system": system_text(request.system_prompt),
            "messages": build_messages(
                history=request.history, user_message=request.user_message, context_lines=request.context_lines
            ),
        }
        # Some older models reject `effort`; the Models API tells us which ones.
        if AnthropicProvider._effort_ok.get(resolved, True):
            body["output_config"] = {"effort": settings.CLAUDE_EFFORT}
        return body

    @staticmethod
    def _anthropic_usage(message: Any) -> dict[str, Any]:
        usage = getattr(message, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        return {
            "input_tokens": input_tokens or None,
            "output_tokens": output_tokens or None,
            "total_tokens": (input_tokens + output_tokens) or None,
        }

    @classmethod
    async def generate(cls, request: ChatRequest, credentials: ProviderCredentials | None = None) -> GenerateResult:
        await cls.model_catalog(credentials)  # learns which models accept `effort`; cached
        body = cls._anthropic_request(request)
        # Streaming keeps long answers from hitting HTTP timeouts; the final message has the same shape.
        async with cls._anthropic_client(credentials=credentials) as client:
            async with client.messages.stream(**body) as stream:
                message = await stream.get_final_message()

        usage = cls._anthropic_usage(message)
        if message.stop_reason == "refusal":
            usage["error_type"] = "provider_refusal"
            usage["refusal_category"] = getattr(getattr(message, "stop_details", None), "category", None)
            return GenerateResult(REFUSAL_TEXT, usage)

        text_parts = [str(block.text).strip() for block in message.content if block.type == "text"]
        text = "\n".join(part for part in text_parts if part).strip()
        if not text:
            raise RuntimeError("Empty Anthropic response")
        if message.stop_reason == "max_tokens":
            usage["truncated"] = True
        return GenerateResult(text, usage)

    @classmethod
    async def stream(
        cls,
        request: ChatRequest,
        credentials: ProviderCredentials | None = None,
        outcome: StreamOutcome | None = None,
    ) -> AsyncIterator[str]:
        await cls.model_catalog(credentials)  # learns which models accept `effort`; cached
        body = cls._anthropic_request(request)
        yielded = False
        async with cls._anthropic_client(credentials=credentials) as client:
            async with client.messages.stream(**body) as stream:
                async for delta in stream.text_stream:
                    if delta:
                        yielded = True
                        yield delta
                message = await stream.get_final_message()

        usage = cls._anthropic_usage(message)
        if outcome is not None:
            outcome.stop_reason = message.stop_reason
            outcome.input_tokens = usage["input_tokens"]
            outcome.output_tokens = usage["output_tokens"]
            outcome.truncated = message.stop_reason == "max_tokens"
        if message.stop_reason == "refusal":
            if outcome is not None:
                outcome.error_type = "provider_refusal"
                outcome.refusal_category = getattr(getattr(message, "stop_details", None), "category", None)
            if not yielded:
                yield REFUSAL_TEXT

    # ------------------------------------------------------------------
    # Health, test, errors
    # ------------------------------------------------------------------

    @classmethod
    async def health(cls, credentials: ProviderCredentials | None) -> dict[str, Any]:
        return {"healthy": bool(cls._api_key(credentials))}

    @classmethod
    async def test_connection(cls, credentials: ProviderCredentials | None) -> dict[str, Any]:
        """Cheap, authenticated check. Never raises and never puts the key or a raw error in the result."""
        try:
            if not cls._api_key(credentials):
                return {"ok": False, "error_type": "not_configured", "detail": "No Claude API key is saved."}
            async with cls._anthropic_client(credentials=credentials, timeout=10.0, max_retries=0) as client:
                await client.models.list(limit=1)
            return {"ok": True, "error_type": None, "detail": "Connected."}
        except Exception as exc:
            error_type = cls.classify_error(exc)
            logger.warning(
                "Provider connection test failed provider=anthropic error_type={error_type}", error_type=error_type
            )
            return {"ok": False, "error_type": error_type, "detail": TEST_DETAIL.get(error_type, TEST_DETAIL["provider_error"])}

    @staticmethod
    def classify_error(exc: Exception) -> str:
        if isinstance(exc, (anthropic.APITimeoutError, httpx.TimeoutException)):
            return "provider_timeout"
        if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
            return "provider_auth_error"
        if isinstance(exc, anthropic.RateLimitError):
            return "provider_rate_limited"
        if isinstance(exc, httpx.HTTPStatusError):
            if exc.response.status_code in (401, 403):
                return "provider_auth_error"
            if exc.response.status_code == 429:
                return "provider_rate_limited"
        if isinstance(exc, (anthropic.APIStatusError, httpx.HTTPStatusError)):
            return "provider_http_error"
        return "provider_error"
