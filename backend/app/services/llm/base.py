"""Provider interface for chat models. Endpoints and the LLM façade depend on this, never on an SDK."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol


class UnsupportedModel(ValueError):
    """The model id is not available for this provider and credential. The message is safe to show."""


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


@dataclass(frozen=True)
class ChatRequest:
    model: str
    user_message: str
    context_lines: list[str]
    history: list[dict[str, str]] | None = None
    system_prompt: str | None = None


@dataclass(frozen=True)
class ModelInfo:
    id: str
    name: str


@dataclass
class GenerateResult:
    text: str
    # Normalized usage and end-state keys: input_tokens, output_tokens, total_tokens, truncated,
    # error_type, refusal_category. Missing means unknown.
    usage: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    """One chat provider. Adapters hold no per-request state; credentials arrive with each call."""

    id: str
    # True when the provider works without any saved credential (a local Ollama).
    always_available: bool

    def owns(self, model: str) -> bool: ...

    def normalize_model(self, model: str) -> str: ...

    async def resolve_model(self, model: str, credentials: ProviderCredentials | None) -> str:
        """Return the model id to store, or raise UnsupportedModel."""
        ...

    async def generate(self, request: ChatRequest, credentials: ProviderCredentials | None) -> GenerateResult: ...

    def stream(
        self,
        request: ChatRequest,
        credentials: ProviderCredentials | None,
        outcome: StreamOutcome,
    ) -> AsyncIterator[str]: ...

    async def list_models(self, credentials: ProviderCredentials | None) -> list[ModelInfo]: ...

    async def health(self, credentials: ProviderCredentials | None) -> dict[str, Any]:
        """`{"healthy": bool}`; the façade adds circuit state."""
        ...

    async def test_connection(self, credentials: ProviderCredentials | None) -> dict[str, Any]:
        """Never raises; never contains a key or raw error text."""
        ...

    def classify_error(self, exc: Exception) -> str: ...

    def server_credentials(self) -> ProviderCredentials | None:
        """Server-wide credentials (environment) when allowed, else None."""
        ...
