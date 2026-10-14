"""LLM provider integration for chat responses."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Iterable

import anthropic
import httpx
from loguru import logger

from app.core.config import settings

DEFAULT_SYSTEM_PROMPT = "You are a concise assistant. Use provided context when relevant."
REFUSAL_TEXT = "The model declined to answer this request."
NO_CONTEXT_TEXT = "I could not find relevant context in your uploaded documents."

# Ollama retries cover a server that is still starting or briefly overloaded, nothing else.
OLLAMA_MAX_ATTEMPTS = 2
OLLAMA_RETRY_DELAY_SECONDS = 0.5
# A failed model listing is remembered briefly so a bad key does not hit the API on every request.
MODEL_LIST_FAILURE_TTL_SECONDS = 30.0


@dataclass
class StreamOutcome:
    """Filled in by `stream_chat_reply` so the caller can store real usage and the end state."""

    stop_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error_type: str | None = None
    refusal_category: str | None = None
    truncated: bool = False


@dataclass(frozen=True)
class ProviderCredentials:
    """What to use for one provider on one request. `repr` never shows the key."""

    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = None
    source: str = "server"  # "user" (this user's saved credentials) or "server" (environment settings)
    owner: str | None = None  # user id, for logs only

    def fingerprint(self) -> str:
        """Short, non-reversible id used to key caches and circuit breakers. "server" for server-wide settings."""
        if self.source == "server" and not self.api_key and not self.base_url:
            return "server"
        digest = hashlib.sha256(f"{self.api_key or ''}|{self.base_url or ''}".encode("utf-8")).hexdigest()
        return digest[:12]


def _breaker_key(provider: str, credentials: ProviderCredentials | None) -> str:
    """Circuit state is per credential; the server-wide credential keeps the plain provider name."""
    if credentials is None or credentials.source == "server":
        return provider
    return f"{provider}:{credentials.fingerprint()}"


class LLMService:
    _failure_count: dict[str, int] = {"ollama": 0, "anthropic": 0}
    _circuit_open_until: dict[str, datetime | None] = {"ollama": None, "anthropic": None}
    # Live Claude model lists, cached per credential so one user's list is never served to another.
    _model_cache: dict[str, tuple[float, list[dict[str, str]]]] = {}
    # Whether each Claude model accepts the configured effort level, learned from the Models API.
    # Unknown models are assumed to accept it (the configured, current models all do).
    _effort_ok: dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Model identity
    # ------------------------------------------------------------------

    @staticmethod
    def is_anthropic_model(model: str) -> bool:
        normalized = model.strip().lower()
        return normalized.startswith("claude-")

    @classmethod
    def provider_for(cls, model: str) -> str:
        return "anthropic" if cls.is_anthropic_model(model) else "ollama"

    @staticmethod
    def normalize_claude_model(model: str) -> str:
        """Map legacy dotted IDs (claude-sonnet-4.6) to the API form (claude-sonnet-4-6)."""
        return re.sub(r"(?<=\d)\.(?=\d)", "-", model.strip())

    @staticmethod
    def configured_claude_models() -> list[dict[str, str]]:
        ids = [settings.CLAUDE_SONNET_MODEL, settings.CLAUDE_OPUS_MODEL, settings.CLAUDE_HAIKU_MODEL]
        seen: list[str] = []
        for model_id in ids:
            if model_id and model_id not in seen:
                seen.append(model_id)
        return [{"id": model_id, "name": model_id} for model_id in seen]

    @staticmethod
    def _claude_key(credentials: ProviderCredentials | None) -> str:
        return (credentials.api_key if credentials and credentials.api_key else settings.CLAUDE_API_KEY) or ""

    @classmethod
    async def claude_model_catalog(cls, credentials: ProviderCredentials | None = None) -> list[dict[str, str]]:
        """Claude models from the Anthropic Models API when a key is available, else the configured IDs."""
        static = cls.configured_claude_models()
        api_key = cls._claude_key(credentials)
        if not api_key:
            return static

        cache_key = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]
        now = time.monotonic()
        cached = cls._model_cache.get(cache_key)
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
            cls._model_cache[cache_key] = (now + settings.LLM_MODEL_LIST_TTL_SECONDS, entries)
            cls._effort_ok = {**cls._effort_ok, **effort_ok}
            return entries
        except Exception as exc:
            logger.warning(
                "Could not list Claude models from the API; using configured IDs: {error_type}",
                error_type=cls._error_type(exc),
            )
            cls._model_cache[cache_key] = (now + MODEL_LIST_FAILURE_TTL_SECONDS, static)
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
    async def allowed_claude_models(cls, credentials: ProviderCredentials | None = None) -> set[str]:
        catalog = await cls.claude_model_catalog(credentials)
        return {entry["id"] for entry in catalog} | {entry["id"] for entry in cls.configured_claude_models()}

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
        """Turn stored messages into chat turns for the model.

        Skips empty rows and assistant replies that were provider fallbacks or refusals (they carry an
        `error_type`), keeps the newest `max_messages`, drops the oldest until the text fits `max_chars`,
        and makes sure the list starts with a user turn.
        """
        limit = settings.LLM_HISTORY_MESSAGES if max_messages is None else max_messages
        char_budget = settings.LLM_HISTORY_MAX_CHARS if max_chars is None else max_chars

        usable: list[dict[str, str]] = []
        for row in rows:
            role = getattr(row, "role", None)
            content = (getattr(row, "content", "") or "").strip()
            if role not in ("user", "assistant") or not content:
                continue
            metadata = getattr(row, "metadata_json", None) or {}
            if role == "assistant" and metadata.get("error_type"):
                continue
            usable.append({"role": role, "content": content})

        usable = usable[-limit:] if limit > 0 else []
        while usable and sum(len(turn["content"]) for turn in usable) > char_budget:
            usable.pop(0)
        while usable and usable[0]["role"] != "user":
            usable.pop(0)
        return usable

    @staticmethod
    def _build_prompt(*, user_message: str, context_lines: list[str]) -> str:
        if context_lines:
            return (
                "Question:\n"
                f"{user_message}\n\n"
                "Relevant document context:\n"
                + "\n".join(context_lines[:6])
                + "\n\nAnswer based on the context when possible. If context is insufficient, say so."
            )
        return f"Question:\n{user_message}\n\nProvide a concise direct answer."

    @classmethod
    def _build_messages(
        cls,
        *,
        history: list[dict[str, str]] | None,
        user_message: str,
        context_lines: list[str],
    ) -> list[dict[str, str]]:
        prompt = cls._build_prompt(user_message=user_message, context_lines=context_lines)
        return [*(history or []), {"role": "user", "content": prompt}]

    @staticmethod
    def _system_text(system_prompt: str | None) -> str:
        return (system_prompt or "").strip() or DEFAULT_SYSTEM_PROMPT

    @staticmethod
    def _fallback_content(context_lines: list[str]) -> str:
        if context_lines:
            return "I found relevant context in your documents:\n" + "\n".join(context_lines[:3])
        return NO_CONTEXT_TEXT

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
        provider = cls.provider_for(model)
        if cls._is_circuit_open(provider, credentials):
            logger.warning("LLM circuit open provider={provider}; using fallback response", provider=provider)
            content = cls._fallback_content(context_lines)
            metadata = {
                "provider": provider,
                "model": model,
                "error_type": "provider_circuit_open",
                "token_estimate": max(int(len(content.split()) * 1.3), 1),
                "total_tokens": max(int(len(content.split()) * 1.3), 1),
                "latency_ms": int((time.perf_counter() - started_at) * 1000),
            }
            return content, metadata

        usage: dict[str, Any] = {}
        try:
            if provider == "anthropic":
                content, usage = await cls._generate_with_anthropic(
                    model=model,
                    user_message=user_message,
                    context_lines=context_lines,
                    history=history,
                    system_prompt=system_prompt,
                    credentials=credentials,
                )
            else:
                content, usage = await cls._generate_with_ollama(
                    model=model,
                    user_message=user_message,
                    context_lines=context_lines,
                    history=history,
                    system_prompt=system_prompt,
                    credentials=credentials,
                )
            cls._record_success(provider, credentials)
        except Exception as exc:
            cls._record_failure(provider, credentials)
            error_type = cls._error_type(exc)
            logger.warning(
                "LLM generation failed provider={provider} model={model} credential={credential} error_type={error_type} request_id={request_id}: {error}",
                provider=provider,
                model=model,
                credential=credentials.source if credentials else "server",
                error_type=error_type,
                request_id=getattr(exc, "request_id", None),
                error=str(exc),
            )
            content = cls._fallback_content(context_lines)
            usage = {"error_type": error_type}

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        token_estimate = max(int(len(content.split()) * 1.3), 1)
        metadata = {
            "provider": provider,
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
        provider = cls.provider_for(model)
        outcome = outcome if outcome is not None else StreamOutcome()
        stream = cls._stream_with_anthropic if provider == "anthropic" else cls._stream_with_ollama
        try:
            async for part in stream(
                model=model,
                user_message=user_message,
                context_lines=context_lines,
                history=history,
                system_prompt=system_prompt,
                outcome=outcome,
                credentials=credentials,
            ):
                yield part
        except Exception as exc:
            cls._record_failure(provider, credentials)
            outcome.error_type = cls._error_type(exc)
            raise
        cls._record_success(provider, credentials)

    # ------------------------------------------------------------------
    # Ollama
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

    @classmethod
    def _ollama_payload(
        cls,
        *,
        model: str,
        stream: bool,
        user_message: str,
        context_lines: list[str],
        history: list[dict[str, str]] | None,
        system_prompt: str | None,
    ) -> dict[str, Any]:
        messages = cls._build_messages(history=history, user_message=user_message, context_lines=context_lines)
        return {
            "model": model,
            "stream": stream,
            "messages": [{"role": "system", "content": cls._system_text(system_prompt)}, *messages],
        }

    @classmethod
    async def _generate_with_ollama(
        cls,
        *,
        model: str,
        user_message: str,
        context_lines: list[str],
        history: list[dict[str, str]] | None = None,
        system_prompt: str | None = None,
        credentials: ProviderCredentials | None = None,
    ) -> tuple[str, dict[str, Any]]:
        payload = cls._ollama_payload(
            model=model,
            stream=False,
            user_message=user_message,
            context_lines=context_lines,
            history=history,
            system_prompt=system_prompt,
        )
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
        return text, {
            "input_tokens": prompt_tokens or None,
            "output_tokens": completion_tokens or None,
            "total_tokens": (prompt_tokens + completion_tokens) or None,
        }

    @classmethod
    async def _stream_with_ollama(
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
        payload = cls._ollama_payload(
            model=model,
            stream=True,
            user_message=user_message,
            context_lines=context_lines,
            history=history,
            system_prompt=system_prompt,
        )
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
    # Anthropic (official SDK)
    # ------------------------------------------------------------------

    @classmethod
    def _anthropic_client(
        cls,
        *,
        credentials: ProviderCredentials | None = None,
        timeout: float | None = None,
        max_retries: int = 2,
    ) -> anthropic.AsyncAnthropic:
        api_key = cls._claude_key(credentials)
        if not api_key:
            raise RuntimeError("No Claude API key is configured")
        return anthropic.AsyncAnthropic(
            api_key=api_key,
            timeout=timeout if timeout is not None else settings.ANTHROPIC_REQUEST_TIMEOUT_SECONDS,
            max_retries=max_retries,
        )

    @classmethod
    def _anthropic_request(
        cls,
        *,
        model: str,
        user_message: str,
        context_lines: list[str],
        history: list[dict[str, str]] | None,
        system_prompt: str | None,
    ) -> dict[str, Any]:
        # No temperature/top_p, thinking switch or prefill: the current Claude models reject them.
        resolved = cls.normalize_claude_model(model)
        request: dict[str, Any] = {
            "model": resolved,
            "max_tokens": settings.CLAUDE_MAX_OUTPUT_TOKENS,
            "system": cls._system_text(system_prompt),
            "messages": cls._build_messages(history=history, user_message=user_message, context_lines=context_lines),
        }
        # Some older models reject `effort`; the Models API tells us which ones.
        if cls._effort_ok.get(resolved, True):
            request["output_config"] = {"effort": settings.CLAUDE_EFFORT}
        return request

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
    async def _generate_with_anthropic(
        cls,
        *,
        model: str,
        user_message: str,
        context_lines: list[str],
        history: list[dict[str, str]] | None = None,
        system_prompt: str | None = None,
        credentials: ProviderCredentials | None = None,
    ) -> tuple[str, dict[str, Any]]:
        await cls.claude_model_catalog(credentials)  # learns which models accept `effort`; cached
        request = cls._anthropic_request(
            model=model,
            user_message=user_message,
            context_lines=context_lines,
            history=history,
            system_prompt=system_prompt,
        )
        # Streaming keeps long answers from hitting HTTP timeouts; the final message has the same shape.
        async with cls._anthropic_client(credentials=credentials) as client:
            async with client.messages.stream(**request) as stream:
                message = await stream.get_final_message()

        usage = cls._anthropic_usage(message)
        if message.stop_reason == "refusal":
            usage["error_type"] = "provider_refusal"
            usage["refusal_category"] = getattr(getattr(message, "stop_details", None), "category", None)
            return REFUSAL_TEXT, usage

        text_parts = [str(block.text).strip() for block in message.content if block.type == "text"]
        text = "\n".join(part for part in text_parts if part).strip()
        if not text:
            raise RuntimeError("Empty Anthropic response")
        if message.stop_reason == "max_tokens":
            usage["truncated"] = True
        return text, usage

    @classmethod
    async def _stream_with_anthropic(
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
        await cls.claude_model_catalog(credentials)  # learns which models accept `effort`; cached
        request = cls._anthropic_request(
            model=model,
            user_message=user_message,
            context_lines=context_lines,
            history=history,
            system_prompt=system_prompt,
        )
        yielded = False
        async with cls._anthropic_client(credentials=credentials) as client:
            async with client.messages.stream(**request) as stream:
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
    # Health and model listing
    # ------------------------------------------------------------------

    @classmethod
    async def provider_health(
        cls,
        *,
        ollama: ProviderCredentials | None = None,
        anthropic_credentials: ProviderCredentials | None = None,
    ) -> dict[str, Any]:
        ollama_ok = False
        try:
            async with httpx.AsyncClient(timeout=cls._ollama_probe_timeout()) as client:
                response = await client.get(
                    f"{cls._ollama_base_url(ollama)}/api/tags", headers=cls._ollama_headers(ollama)
                )
                ollama_ok = response.status_code == 200
        except Exception as exc:
            logger.debug("Ollama health probe failed: {error_type}", error_type=cls._error_type(exc))
            ollama_ok = False
        anthropic_ok = bool(cls._claude_key(anthropic_credentials))
        return {
            "ollama": {"healthy": ollama_ok, "circuit_open": cls._is_circuit_open("ollama", ollama)},
            "anthropic": {
                "healthy": anthropic_ok,
                "circuit_open": cls._is_circuit_open("anthropic", anthropic_credentials),
            },
        }

    @classmethod
    async def list_models(
        cls,
        *,
        ollama: ProviderCredentials | None = None,
        anthropic_credentials: ProviderCredentials | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        ollama_models: list[dict[str, Any]] = []
        try:
            async with httpx.AsyncClient(timeout=cls._ollama_probe_timeout()) as client:
                response = await client.get(
                    f"{cls._ollama_base_url(ollama)}/api/tags", headers=cls._ollama_headers(ollama)
                )
                response.raise_for_status()
                payload = response.json()
                for model in payload.get("models", []) or []:
                    name = model.get("name")
                    if name:
                        ollama_models.append({"id": name, "name": name, "provider": "ollama"})
        except Exception as exc:
            logger.warning("Unable to list Ollama models: {error_type}", error_type=cls._error_type(exc))
        anthropic_models = [
            {"id": entry["id"], "name": entry["name"], "provider": "anthropic"}
            for entry in await cls.claude_model_catalog(anthropic_credentials)
        ]
        return {"ollama": ollama_models, "anthropic": anthropic_models}

    _TEST_DETAIL = {
        "provider_auth_error": "The provider rejected the key.",
        "provider_rate_limited": "The provider is rate limiting this key.",
        "provider_timeout": "The provider did not answer in time.",
        "provider_http_error": "The provider returned an error.",
        "provider_error": "Could not reach the provider.",
    }

    @classmethod
    async def test_connection(cls, provider: str, credentials: ProviderCredentials | None) -> dict[str, Any]:
        """Cheap, authenticated check of a provider. Never raises and never puts the key or a raw error in the result."""
        try:
            if provider == "anthropic":
                if not cls._claude_key(credentials):
                    return {"ok": False, "error_type": "not_configured", "detail": "No Claude API key is saved."}
                async with cls._anthropic_client(credentials=credentials, timeout=10.0, max_retries=0) as client:
                    await client.models.list(limit=1)
                return {"ok": True, "error_type": None, "detail": "Connected."}
            if provider == "ollama":
                async with httpx.AsyncClient(timeout=cls._ollama_probe_timeout()) as client:
                    response = await client.get(
                        f"{cls._ollama_base_url(credentials)}/api/tags", headers=cls._ollama_headers(credentials)
                    )
                    response.raise_for_status()
                return {"ok": True, "error_type": None, "detail": "Connected."}
            return {"ok": False, "error_type": "provider_not_supported", "detail": "This provider is not supported yet."}
        except Exception as exc:
            error_type = cls._error_type(exc)
            logger.warning("Provider connection test failed provider={provider} error_type={error_type}", provider=provider, error_type=error_type)
            return {"ok": False, "error_type": error_type, "detail": cls._TEST_DETAIL.get(error_type, cls._TEST_DETAIL["provider_error"])}

    # ------------------------------------------------------------------
    # Errors and circuit breaker
    # ------------------------------------------------------------------

    @staticmethod
    def _error_type(exc: Exception) -> str:
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
