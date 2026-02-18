"""LLM provider integration for chat responses."""

from __future__ import annotations

import time
from typing import Any

import httpx
from loguru import logger

from app.core.config import settings


class LLMService:
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
        try:
            if provider == "anthropic":
                content = await cls._generate_with_anthropic(model=model, user_message=user_message, context_lines=context_lines)
            else:
                content = await cls._generate_with_ollama(model=model, user_message=user_message, context_lines=context_lines)
        except Exception as exc:
            logger.warning("LLM generation failed provider={provider} model={model}: {error}", provider=provider, model=model, error=str(exc))
            if context_lines:
                content = "I found relevant context in your documents:\n" + "\n".join(context_lines[:3])
            else:
                content = "I could not find relevant context in your uploaded documents."

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        metadata = {
            "provider": provider,
            "model": model,
            "latency_ms": latency_ms,
            "token_estimate": max(int(len(content.split()) * 1.3), 1),
        }
        return content, metadata

    @classmethod
    async def _generate_with_ollama(cls, *, model: str, user_message: str, context_lines: list[str]) -> str:
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
            return text

    @classmethod
    async def _generate_with_anthropic(cls, *, model: str, user_message: str, context_lines: list[str]) -> str:
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
            return text

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
