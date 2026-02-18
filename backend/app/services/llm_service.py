"""LLM provider integration for chat responses."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

import httpx
from loguru import logger

from app.core.config import settings


class LLMService:
    _failure_count: dict[str, int] = {"ollama": 0, "anthropic": 0}
    _circuit_open_until: dict[str, datetime | None] = {"ollama": None, "anthropic": None}

    @staticmethod
    def is_anthropic_model(model: str) -> bool:
        normalized = model.strip().lower()
        return normalized.startswith("claude-")

    @classmethod
    async def generate_chat_reply(
        cls,
        *,
        model: str,
        user_message: str,
        context_lines: list[str],
    ) -> tuple[str, dict[str, Any]]:
        started_at = time.perf_counter()
        provider = "anthropic" if cls.is_anthropic_model(model) else "ollama"
        if cls._is_circuit_open(provider):
            logger.warning("LLM circuit open provider={provider}; using fallback response", provider=provider)
            if context_lines:
                content = "I found relevant context in your documents:\n" + "\n".join(context_lines[:3])
            else:
                content = "I could not find relevant context in your uploaded documents."
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
            last_error: Exception | None = None
            for _ in range(2):
                try:
                    if provider == "anthropic":
                        content, usage = await cls._generate_with_anthropic(
                            model=model,
                            user_message=user_message,
                            context_lines=context_lines,
                        )
                    else:
                        content, usage = await cls._generate_with_ollama(
                            model=model,
                            user_message=user_message,
                            context_lines=context_lines,
                        )
                    cls._record_success(provider)
                    break
                except Exception as exc:  # noqa: PERF203
                    last_error = exc
                    await asyncio.sleep(0.15)
            else:
                raise RuntimeError(str(last_error) if last_error else "Unknown provider error")
        except Exception as exc:
            cls._record_failure(provider)
            logger.warning(
                "LLM generation failed provider={provider} model={model}: {error}",
                provider=provider,
                model=model,
                error=str(exc),
            )
            error_type = "provider_error"
            if isinstance(exc, httpx.TimeoutException):
                error_type = "provider_timeout"
            elif isinstance(exc, httpx.HTTPStatusError):
                error_type = "provider_http_error"
            if context_lines:
                content = "I found relevant context in your documents:\n" + "\n".join(context_lines[:3])
            else:
                content = "I could not find relevant context in your uploaded documents."
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
    async def _generate_with_ollama(
        cls,
        *,
        model: str,
        user_message: str,
        context_lines: list[str],
    ) -> tuple[str, dict[str, Any]]:
        prompt = cls._build_prompt(user_message=user_message, context_lines=context_lines)
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.post(
                f"{settings.OLLAMA_URL.rstrip('/')}/api/chat",
                json={
                    "model": model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": "You are a concise assistant. Use provided context when relevant."},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()
            message = payload.get("message", {})
            text = str(message.get("content", "")).strip()
            if not text:
                raise RuntimeError("Empty Ollama response")
            prompt_tokens = int(payload.get("prompt_eval_count") or 0)
            completion_tokens = int(payload.get("eval_count") or 0)
            return text, {
                "input_tokens": prompt_tokens or None,
                "output_tokens": completion_tokens or None,
                "total_tokens": (prompt_tokens + completion_tokens) or None,
            }

    @classmethod
    async def _generate_with_anthropic(
        cls,
        *,
        model: str,
        user_message: str,
        context_lines: list[str],
    ) -> tuple[str, dict[str, Any]]:
        if not settings.CLAUDE_API_KEY:
            raise RuntimeError("CLAUDE_API_KEY is not configured")
        prompt = cls._build_prompt(user_message=user_message, context_lines=context_lines)
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.CLAUDE_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": model,
                    "max_tokens": 700,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            payload = response.json()
            content_blocks = payload.get("content", [])
            text_parts = [str(block.get("text", "")).strip() for block in content_blocks if block.get("type") == "text"]
            text = "\n".join(part for part in text_parts if part).strip()
            if not text:
                raise RuntimeError("Empty Anthropic response")
            usage = payload.get("usage", {}) or {}
            input_tokens = int(usage.get("input_tokens") or 0)
            output_tokens = int(usage.get("output_tokens") or 0)
            return text, {
                "input_tokens": input_tokens or None,
                "output_tokens": output_tokens or None,
                "total_tokens": (input_tokens + output_tokens) or None,
            }

    @classmethod
    async def stream_chat_reply(
        cls,
        *,
        model: str,
        user_message: str,
        context_lines: list[str],
    ) -> AsyncIterator[str]:
        provider = "anthropic" if cls.is_anthropic_model(model) else "ollama"
        if provider == "anthropic":
            async for part in cls._stream_with_anthropic(model=model, user_message=user_message, context_lines=context_lines):
                yield part
            return
        async for part in cls._stream_with_ollama(model=model, user_message=user_message, context_lines=context_lines):
            yield part

    @classmethod
    async def _stream_with_ollama(
        cls,
        *,
        model: str,
        user_message: str,
        context_lines: list[str],
    ) -> AsyncIterator[str]:
        prompt = cls._build_prompt(user_message=user_message, context_lines=context_lines)
        async with httpx.AsyncClient(timeout=10.0) as client:
            async with client.stream(
                "POST",
                f"{settings.OLLAMA_URL.rstrip('/')}/api/chat",
                json={
                    "model": model,
                    "stream": True,
                    "messages": [
                        {"role": "system", "content": "You are a concise assistant. Use provided context when relevant."},
                        {"role": "user", "content": prompt},
                    ],
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    message = payload.get("message", {})
                    delta = str(message.get("content", ""))
                    if delta:
                        yield delta

    @classmethod
    async def _stream_with_anthropic(
        cls,
        *,
        model: str,
        user_message: str,
        context_lines: list[str],
    ) -> AsyncIterator[str]:
        if not settings.CLAUDE_API_KEY:
            raise RuntimeError("CLAUDE_API_KEY is not configured")
        prompt = cls._build_prompt(user_message=user_message, context_lines=context_lines)
        async with httpx.AsyncClient(timeout=10.0) as client:
            async with client.stream(
                "POST",
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.CLAUDE_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": model,
                    "max_tokens": 700,
                    "stream": True,
                    "messages": [{"role": "user", "content": prompt}],
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line.removeprefix("data: ").strip()
                    if raw in {"[DONE]", ""}:
                        continue
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if payload.get("type") == "content_block_delta":
                        delta = str((payload.get("delta") or {}).get("text", ""))
                        if delta:
                            yield delta

    @classmethod
    async def provider_health(cls) -> dict[str, Any]:
        ollama_ok = False
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{settings.OLLAMA_URL.rstrip('/')}/api/tags")
                ollama_ok = response.status_code == 200
        except Exception:
            ollama_ok = False
        anthropic_ok = bool(settings.CLAUDE_API_KEY)
        return {
            "ollama": {"healthy": ollama_ok, "circuit_open": cls._is_circuit_open("ollama")},
            "anthropic": {"healthy": anthropic_ok, "circuit_open": cls._is_circuit_open("anthropic")},
        }

    @classmethod
    async def list_models(cls) -> dict[str, list[dict[str, Any]]]:
        ollama_models: list[dict[str, Any]] = []
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{settings.OLLAMA_URL.rstrip('/')}/api/tags")
                response.raise_for_status()
                payload = response.json()
                for model in payload.get("models", []) or []:
                    name = model.get("name")
                    if name:
                        ollama_models.append({"id": name, "provider": "ollama"})
        except Exception as exc:
            logger.debug("Unable to list Ollama models: {}", str(exc))
        anthropic_models = [
            {"id": settings.CLAUDE_SONNET_MODEL, "provider": "anthropic"},
            {"id": settings.CLAUDE_OPUS_MODEL, "provider": "anthropic"},
        ]
        return {"ollama": ollama_models, "anthropic": anthropic_models}

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
    def _record_failure(cls, provider: str) -> None:
        cls._failure_count[provider] = cls._failure_count.get(provider, 0) + 1
        if cls._failure_count[provider] >= 3:
            cls._circuit_open_until[provider] = datetime.now(tz=timezone.utc) + timedelta(seconds=30)

    @classmethod
    def _record_success(cls, provider: str) -> None:
        cls._failure_count[provider] = 0
        cls._circuit_open_until[provider] = None

    @classmethod
    def _is_circuit_open(cls, provider: str) -> bool:
        opened_until = cls._circuit_open_until.get(provider)
        if opened_until is None:
            return False
        if datetime.now(tz=timezone.utc) >= opened_until:
            cls._circuit_open_until[provider] = None
            return False
        return True
