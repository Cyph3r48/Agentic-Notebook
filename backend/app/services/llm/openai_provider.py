"""OpenAI adapter, using the Responses API with streaming.

Privacy: every request sends `store=False`. The API default is to keep the response for at least 30 days, which
a privacy-first app must not leave to chance. No sampling parameters, `previous_response_id`, `user` or
`metadata` are sent.
"""

from __future__ import annotations

import hashlib
import re
import time
from typing import Any, AsyncIterator

import openai
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

# models.list() carries no capability flags, so chat-capable models are recognised by id.
_CHAT_ID = re.compile(r"^(gpt-|o\d|chatgpt-)")
_NOT_CHAT = ("embedding", "whisper", "tts", "transcribe", "audio", "realtime", "image", "moderation", "search", "dall-e")


class OpenAIStreamError(RuntimeError):
    """The stream reported a failure. The message holds only the error code, never provider text."""

    def __init__(self, code: str | None):
        self.code = code
        super().__init__(f"OpenAI response failed ({code or 'unknown'})")


class OpenAIProvider:
    id = "openai"
    always_available = False
    accepts_base_url = False

    # Live model lists, cached per credential so one user's list is never served to another.
    _model_cache: dict[str, tuple[float, list[dict[str, str]]]] = {}

    # ------------------------------------------------------------------
    # Model identity
    # ------------------------------------------------------------------

    @staticmethod
    def is_chat_model(model_id: str) -> bool:
        lowered = model_id.strip().lower()
        return bool(_CHAT_ID.match(lowered)) and not any(part in lowered for part in _NOT_CHAT)

    @staticmethod
    def owns(model: str) -> bool:
        lowered = model.strip().lower()
        # A tag (`gpt-oss:20b`) means an Ollama model: OpenAI ids never contain a colon.
        return ":" not in lowered and bool(_CHAT_ID.match(lowered))

    @staticmethod
    def normalize_model(model: str) -> str:
        return model.strip()

    @staticmethod
    def _api_key(credentials: ProviderCredentials | None) -> str:
        # Only what the caller resolved: the server-wide key reaches here through `server_credentials`,
        # so ALLOW_SERVER_PROVIDER_KEYS is honoured.
        return (credentials.api_key if credentials and credentials.api_key else "") or ""

    @staticmethod
    def server_credentials() -> ProviderCredentials | None:
        if settings.ALLOW_SERVER_PROVIDER_KEYS and settings.OPENAI_API_KEY:
            return ProviderCredentials(api_key=settings.OPENAI_API_KEY, source="server")
        return None

    @staticmethod
    def _configured_models() -> list[dict[str, str]]:
        model_id = settings.OPENAI_DEFAULT_MODEL
        return [{"id": model_id, "name": model_id}] if model_id else []

    @classmethod
    async def model_catalog(cls, credentials: ProviderCredentials | None = None) -> list[dict[str, str]]:
        """Chat models the key can use, newest first. Empty without a key; the default model if listing fails."""
        api_key = cls._api_key(credentials)
        if not api_key:
            return []

        cache_key = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]
        now = time.monotonic()
        cached = OpenAIProvider._model_cache.get(cache_key)
        if cached is not None and cached[0] > now:
            return cached[1]

        try:
            found: list[tuple[int, str]] = []
            async with cls._openai_client(credentials=credentials, timeout=10.0, max_retries=0) as client:
                async for info in client.models.list():
                    if cls.is_chat_model(info.id):
                        found.append((int(getattr(info, "created", 0) or 0), info.id))
            if not found:
                raise RuntimeError("Models API returned no chat models")
            entries = [{"id": model_id, "name": model_id} for _, model_id in sorted(found, reverse=True)]
            OpenAIProvider._model_cache[cache_key] = (now + settings.LLM_MODEL_LIST_TTL_SECONDS, entries)
            return entries
        except Exception as exc:
            logger.warning(
                "Could not list OpenAI models from the API; using the configured default: {error_type}",
                error_type=cls.classify_error(exc),
            )
            static = cls._configured_models()
            OpenAIProvider._model_cache[cache_key] = (now + MODEL_LIST_FAILURE_TTL_SECONDS, static)
            return static

    @classmethod
    async def resolve_model(cls, model: str, credentials: ProviderCredentials | None) -> str:
        selected = cls.normalize_model(model)
        if not cls._api_key(credentials):
            raise UnsupportedModel("No OpenAI API key is saved. Add one in Settings to use OpenAI models.")
        allowed = {entry["id"] for entry in await cls.model_catalog(credentials)}
        allowed |= {entry["id"] for entry in cls._configured_models()}
        if selected not in allowed:
            raise UnsupportedModel(f"Unsupported OpenAI model. Allowed: {sorted(allowed)}")
        return selected

    @classmethod
    async def list_models(cls, credentials: ProviderCredentials | None) -> list[ModelInfo]:
        return [ModelInfo(id=entry["id"], name=entry["name"]) for entry in await cls.model_catalog(credentials)]

    # ------------------------------------------------------------------
    # Requests
    # ------------------------------------------------------------------

    @classmethod
    def _openai_client(
        cls,
        *,
        credentials: ProviderCredentials | None = None,
        timeout: float | None = None,
        max_retries: int = 2,
    ) -> openai.AsyncOpenAI:
        api_key = cls._api_key(credentials)
        if not api_key:
            raise RuntimeError("No OpenAI API key is configured")
        return openai.AsyncOpenAI(
            api_key=api_key,
            timeout=timeout if timeout is not None else settings.OPENAI_REQUEST_TIMEOUT_SECONDS,
            max_retries=max_retries,
        )

    @staticmethod
    def _request_body(request: ChatRequest) -> dict[str, Any]:
        messages = build_messages(
            history=request.history, user_message=request.user_message, context_lines=request.context_lines
        )
        body: dict[str, Any] = {
            "model": request.model.strip(),
            "instructions": system_text(request.system_prompt),
            "input": [{"role": turn["role"], "content": turn["content"]} for turn in messages],
            "max_output_tokens": settings.OPENAI_MAX_OUTPUT_TOKENS,
            "store": False,  # the API default keeps responses for at least 30 days
            "stream": True,
        }
        if settings.OPENAI_REASONING_EFFORT:
            body["reasoning"] = {"effort": settings.OPENAI_REASONING_EFFORT}
        return body

    @classmethod
    async def stream(
        cls,
        request: ChatRequest,
        credentials: ProviderCredentials | None = None,
        outcome: StreamOutcome | None = None,
    ) -> AsyncIterator[str]:
        body = cls._request_body(request)
        yielded = False
        refusal = False
        final = None
        async with cls._openai_client(credentials=credentials) as client:
            events = await client.responses.create(**body)
            async for event in events:
                kind = getattr(event, "type", None)
                if kind == "response.output_text.delta":
                    delta = getattr(event, "delta", "") or ""
                    if delta:
                        yielded = True
                        yield delta
                elif kind == "response.refusal.delta":
                    refusal = True
                elif kind in ("response.completed", "response.incomplete"):
                    final = event.response
                elif kind == "response.failed":
                    error = getattr(event.response, "error", None)
                    raise OpenAIStreamError(getattr(error, "code", None))
                elif kind == "error":
                    raise OpenAIStreamError(getattr(event, "code", None))

        if final is None:
            raise RuntimeError("OpenAI stream ended without a final event")

        usage = getattr(final, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        reason = getattr(getattr(final, "incomplete_details", None), "reason", None)
        if outcome is not None:
            outcome.stop_reason = reason or getattr(final, "status", None)
            outcome.input_tokens = input_tokens or None
            outcome.output_tokens = output_tokens or None
            outcome.truncated = reason == "max_output_tokens"
        if refusal or reason == "content_filter":
            if outcome is not None:
                outcome.error_type = "provider_refusal"
                outcome.refusal_category = "content_filter" if reason == "content_filter" else None
            if not yielded:
                yield REFUSAL_TEXT

    @classmethod
    async def generate(cls, request: ChatRequest, credentials: ProviderCredentials | None = None) -> GenerateResult:
        # Same path as streaming: long answers do not hit HTTP timeouts and there is one code path to test.
        outcome = StreamOutcome()
        parts: list[str] = []
        async for delta in cls.stream(request, credentials, outcome):
            parts.append(delta)

        usage: dict[str, Any] = {
            "input_tokens": outcome.input_tokens,
            "output_tokens": outcome.output_tokens,
            "total_tokens": ((outcome.input_tokens or 0) + (outcome.output_tokens or 0)) or None,
        }
        if outcome.error_type == "provider_refusal":
            usage["error_type"] = "provider_refusal"
            usage["refusal_category"] = outcome.refusal_category
            return GenerateResult(REFUSAL_TEXT, usage)
        text = "".join(parts).strip()
        if not text:
            raise RuntimeError("Empty OpenAI response")
        if outcome.truncated:
            usage["truncated"] = True
        return GenerateResult(text, usage)

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
                return {"ok": False, "error_type": "not_configured", "detail": "No OpenAI API key is saved."}
            async with cls._openai_client(credentials=credentials, timeout=10.0, max_retries=0) as client:
                await client.models.list()
            return {"ok": True, "error_type": None, "detail": "Connected."}
        except Exception as exc:
            error_type = cls.classify_error(exc)
            logger.warning(
                "Provider connection test failed provider=openai error_type={error_type}", error_type=error_type
            )
            return {"ok": False, "error_type": error_type, "detail": TEST_DETAIL.get(error_type, TEST_DETAIL["provider_error"])}

    @staticmethod
    def classify_error(exc: Exception) -> str:
        if isinstance(exc, OpenAIStreamError):
            if exc.code == "insufficient_quota":
                return "provider_quota_exceeded"
            if exc.code == "rate_limit_exceeded":
                return "provider_rate_limited"
            return "provider_error"
        # APITimeoutError subclasses APIConnectionError, so it must be checked first.
        if isinstance(exc, openai.APITimeoutError):
            return "provider_timeout"
        if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
            return "provider_auth_error"
        if isinstance(exc, openai.RateLimitError):
            # A 429 with this code means the account is out of credit, not that it is going too fast.
            if getattr(exc, "code", None) == "insufficient_quota":
                return "provider_quota_exceeded"
            return "provider_rate_limited"
        if isinstance(exc, openai.APIStatusError):
            return "provider_http_error"
        return "provider_error"
