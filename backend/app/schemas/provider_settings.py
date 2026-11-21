"""Schemas for saving and reporting provider credentials. No response ever contains a key."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, SecretStr, field_validator

ProviderName = Literal["anthropic", "openai", "ollama"]
PROVIDERS: tuple[str, ...] = ("anthropic", "openai", "ollama")


class ProviderSaveRequest(BaseModel):
    # SecretStr keeps the key out of repr() and accidental logging of the model.
    api_key: SecretStr | None = Field(default=None, repr=False)
    base_url: str | None = Field(default=None, max_length=500)

    @field_validator("api_key")
    @classmethod
    def check_api_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        raw = value.get_secret_value().strip()
        if not 8 <= len(raw) <= 512:
            raise ValueError("API key must be between 8 and 512 characters")
        if any(ch.isspace() or ord(ch) < 32 for ch in raw):
            raise ValueError("API key must not contain spaces or control characters")
        return SecretStr(raw)

    @field_validator("base_url")
    @classmethod
    def check_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        raw = value.strip().rstrip("/")
        if not raw:
            return None
        parts = urlsplit(raw)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("Base URL must start with http:// or https:// and include a host")
        if parts.username or parts.password:
            raise ValueError("Base URL must not contain credentials")
        return raw


class ProviderStatus(BaseModel):
    provider: ProviderName
    # True when a key or base URL is usable for this user, from their own row or the server-wide key.
    configured: bool
    # "user" = this user's saved key, "server" = the server-wide key, "none" = nothing available.
    source: Literal["user", "server", "none"]
    key_hint: str | None = None
    base_url: str | None = None
    # A saved key exists but cannot be decrypted (master key changed); the user must enter it again.
    needs_reentry: bool = False
    # False while no adapter exists for this provider (OpenAI, for now).
    supported: bool = True
    updated_at: datetime | None = None


class ProviderTestResult(BaseModel):
    ok: bool
    error_type: str | None = None
    detail: str
