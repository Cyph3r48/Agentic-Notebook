"""The system-wide embedding model: what an admin chose, how it is tested, and which one is active.

Rules that keep search correct:
- A choice is saved only after a real probe succeeds, so a model that cannot embed never becomes the active one.
- The probe measures the vector size; the size is part of the index identity (see `memory/embeddings.py`).
- The key is write-only: it is encrypted with `SecretBox` (context `system:embedding`) and never returned or logged.
"""

from __future__ import annotations

import time
from typing import Any, Protocol
from uuid import UUID

from loguru import logger

from app.core.config import settings
from app.core.secret_box import SecretBox, SecretDecryptError, SecretsNotConfigured, get_secret_box
from app.schemas.embedding_settings import EmbeddingCandidate, EmbeddingSettingsResponse, EmbeddingTestResult
from app.services.memory.embeddings import (
    EMBEDDING_PROVIDERS,
    EmbeddingConfig,
    VectorPathError,
    bootstrap_config,
    build_embedding_provider,
    describe_error,
)

SETTING_KEY = "embedding"
SECRET_CONTEXT = "system:embedding"
# How long the active choice is remembered in this process. An apply clears it at once.
ACTIVE_CACHE_SECONDS = 10.0

_cache: dict[str, Any] = {"expires": 0.0, "config": None}


def invalidate_active_embedding() -> None:
    _cache.update(expires=0.0, config=None)


class EmbeddingProbeFailed(Exception):
    """The candidate could not embed anything. The message is safe to show."""


class DocumentIndexStats(Protocol):
    async def counts(self, identity: str) -> tuple[int, int]:
        """(completed documents, documents already in the index with this identity)."""
        ...


class EmbeddingSettingsService:
    def __init__(self, repo, stats: DocumentIndexStats | None = None, box: SecretBox | None = None, provider_factory=build_embedding_provider):
        self.repo = repo
        self.stats = stats
        self._box = box
        self._factory = provider_factory

    @property
    def box(self) -> SecretBox:
        return self._box if self._box is not None else get_secret_box()

    # ------------------------------------------------------------------
    # What is saved and what is active
    # ------------------------------------------------------------------

    def _decrypt_key(self, row) -> str | None:
        if not row or not row.secret_encrypted:
            return None
        try:
            return self.box.decrypt(row.secret_encrypted, context=SECRET_CONTEXT)
        except (SecretDecryptError, SecretsNotConfigured) as exc:
            raise VectorPathError("Embeddings: the saved key can no longer be read; enter it again in Settings") from exc

    def _config_from_row(self, row) -> EmbeddingConfig:
        value = row.value or {}
        return EmbeddingConfig(
            provider=value.get("provider", "tei"),
            model=value.get("model", ""),
            base_url=value.get("base_url"),
            api_key=self._decrypt_key(row),
            dim=value.get("dim"),
        )

    async def active_config(self) -> EmbeddingConfig:
        """The configuration every embed and every collection name uses right now. Raises VectorPathError."""
        now = time.monotonic()
        if _cache["config"] is not None and _cache["expires"] > now:
            return _cache["config"]

        row = await self.repo.get(SETTING_KEY)
        config = self._config_from_row(row) if row else bootstrap_config()
        if config.dim is None:
            # Environment-chosen Ollama models have no known size until they are asked once.
            config = config.with_dim((await self._factory(config).probe()).dim)
        _cache.update(expires=now + ACTIVE_CACHE_SECONDS, config=config)
        return config

    async def get(self) -> EmbeddingSettingsResponse:
        row = await self.repo.get(SETTING_KEY)
        if row:
            value = row.value or {}
            provider, model = value.get("provider", "tei"), value.get("model", "")
            base_url, dim, hint = value.get("base_url"), value.get("dim"), value.get("key_hint")
            source, updated_at = "settings", row.updated_at
        else:
            boot = bootstrap_config()
            provider, model, base_url, dim, hint = boot.provider, boot.model, boot.base_url, boot.dim, None
            source, updated_at = "environment", None

        identity = EmbeddingConfig(provider, model, dim=dim).identity() if dim else None
        total = in_index = None
        if self.stats is not None and identity:
            total, in_index = await self.stats.counts(identity)
        return EmbeddingSettingsResponse(
            provider=provider,
            model=model,
            base_url=base_url if provider == "ollama" else None,
            key_hint=hint,
            dim=dim,
            identity=identity,
            source=source,
            model_editable=provider != "tei",
            updated_at=updated_at,
            documents_total=total,
            documents_in_index=in_index,
        )

    # ------------------------------------------------------------------
    # Candidates
    # ------------------------------------------------------------------

    def _candidate_config(self, candidate: EmbeddingCandidate, row) -> tuple[EmbeddingConfig, str | None]:
        """Turn what the admin typed into a config. Raises ValueError (bad input) or EmbeddingProbeFailed."""
        if candidate.provider not in EMBEDDING_PROVIDERS:
            raise ValueError(f"Unknown embedding provider: {candidate.provider}")
        saved = (row.value or {}) if row else {}
        same_provider = saved.get("provider") == candidate.provider

        key = candidate.api_key.get_secret_value() if candidate.api_key else None
        if key is None and same_provider and not candidate.clear_key:
            try:
                key = self._decrypt_key(row)  # keep the saved key when none is sent
            except VectorPathError as exc:
                raise EmbeddingProbeFailed(str(exc)) from exc

        if candidate.provider == "tei":
            if candidate.base_url:
                raise ValueError("The TEI address is set in the environment (EMBEDDING_URL), not here")
            return EmbeddingConfig("tei", settings.EMBEDDING_MODEL, base_url=settings.EMBEDDING_URL), None

        model = candidate.model or (saved.get("model") if same_provider else None)
        if not model:
            raise ValueError("Enter the embedding model name")

        if candidate.provider == "ollama_cloud":
            if candidate.base_url:
                raise ValueError("Ollama Cloud has a fixed address")
            return EmbeddingConfig("ollama_cloud", model, api_key=key), key

        base_url = candidate.base_url or (saved.get("base_url") if same_provider else None) or settings.OLLAMA_URL
        return EmbeddingConfig("ollama", model, base_url=base_url, api_key=key), key

    async def _probe(self, candidate: EmbeddingCandidate) -> tuple[EmbeddingConfig | None, str | None, EmbeddingTestResult]:
        row = await self.repo.get(SETTING_KEY)
        try:
            config, key = self._candidate_config(candidate, row)
        except EmbeddingProbeFailed as exc:
            return None, None, EmbeddingTestResult(ok=False, detail=str(exc))
        try:
            probed = await self._factory(config).probe()
        except Exception as exc:
            detail = describe_error("Embeddings", exc)
            logger.warning("Embedding probe failed provider={provider}: {detail}", provider=config.provider, detail=detail)
            return config, key, EmbeddingTestResult(ok=False, detail=detail)
        config = config.with_dim(probed.dim)
        result = EmbeddingTestResult(
            ok=True,
            dim=probed.dim,
            latency_ms=probed.latency_ms,
            identity=config.identity(),
            detail=f"Works. The model returns vectors of size {probed.dim}.",
        )
        return config, key, result

    async def test(self, candidate: EmbeddingCandidate) -> EmbeddingTestResult:
        """Probe a candidate without saving anything. Raises ValueError for invalid input only."""
        return (await self._probe(candidate))[2]

    async def apply(self, candidate: EmbeddingCandidate, user_id: UUID | None) -> EmbeddingSettingsResponse:
        """Save a candidate as the active choice, but only after it really embedded a test string.

        Raises ValueError (bad input), EmbeddingProbeFailed (the probe failed; nothing is saved) or
        SecretsNotConfigured (no master key to encrypt the key with).
        """
        config, key, result = await self._probe(candidate)
        if not result.ok or config is None:
            raise EmbeddingProbeFailed(result.detail)
        token = self.box.encrypt(key, context=SECRET_CONTEXT) if key else None  # may raise SecretsNotConfigured
        await self.repo.put(
            SETTING_KEY,
            {
                "provider": config.provider,
                "model": config.model,
                "base_url": config.base_url if config.provider == "ollama" else None,
                "dim": config.dim,
                "key_hint": key[-4:] if key else None,
            },
            secret_encrypted=token,
            updated_by=user_id,
        )
        invalidate_active_embedding()
        logger.bind(action="embedding_settings_applied", user_id=str(user_id)).info(
            "Embedding choice applied provider={provider} dim={dim}", provider=config.provider, dim=config.dim
        )
        return await self.get()


class RepositoryIndexStats:
    """Counts documents through the document repository."""

    def __init__(self, document_repo):
        self.document_repo = document_repo

    async def counts(self, identity: str) -> tuple[int, int]:
        return await self.document_repo.count_completed(), await self.document_repo.count_in_index(identity)
