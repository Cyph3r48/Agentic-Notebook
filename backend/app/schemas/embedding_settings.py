"""Schemas for the system-wide embedding model. No response ever contains a key."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator

from app.schemas.provider_settings import clean_api_key, clean_base_url

EmbeddingProviderName = Literal["tei", "ollama", "ollama_cloud"]


class EmbeddingCandidate(BaseModel):
    """What an admin wants to test or apply. Omitted fields keep their saved value where that is safe."""

    provider: EmbeddingProviderName
    # TEI serves the one model named in the environment, so its model is not chosen here.
    model: str | None = Field(default=None, max_length=100)
    # Only for a local Ollama. TEI's address comes from the environment; Ollama Cloud's is fixed.
    base_url: str | None = Field(default=None, max_length=500)
    api_key: SecretStr | None = Field(default=None, repr=False)
    clear_key: bool = False

    @field_validator("model")
    @classmethod
    def check_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        raw = value.strip()
        if not raw:
            return None
        if any(ord(ch) < 32 for ch in raw):
            raise ValueError("Model name must not contain control characters")
        return raw

    @field_validator("base_url")
    @classmethod
    def check_base_url(cls, value: str | None) -> str | None:
        return clean_base_url(value)

    @field_validator("api_key")
    @classmethod
    def check_api_key(cls, value: SecretStr | None) -> SecretStr | None:
        return clean_api_key(value)


class EmbeddingSettingsResponse(BaseModel):
    provider: EmbeddingProviderName
    model: str
    base_url: str | None = None
    key_hint: str | None = None
    # The vector size, known once a choice has been probed. Part of the index identity.
    dim: int | None = None
    identity: str | None = None
    # "settings" = saved by an admin; "environment" = the bootstrap values from the environment.
    source: Literal["settings", "environment"]
    # False for TEI, whose model is fixed by the environment.
    model_editable: bool = True
    updated_at: datetime | None = None
    documents_total: int | None = None
    documents_in_index: int | None = None


class EmbeddingTestResult(BaseModel):
    ok: bool
    dim: int | None = None
    latency_ms: int | None = None
    identity: str | None = None
    detail: str
