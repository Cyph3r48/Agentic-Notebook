"""Embedding providers: TEI, a local Ollama, and Ollama Cloud, behind one interface.

An embedding choice is (provider, model, vector size). Vectors from different models are not comparable, so the
vector size and model are part of the index identity: each identity gets its own Qdrant collection, and a query
must be embedded with the same configuration as the collection it searches.

Every failure becomes a fixed, safe message (no URL, key or text), because these messages are logged, stored and
shown in Settings.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field, replace
from typing import Literal, Protocol

import httpx
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from app.core.config import settings
from app.services.llm.ollama_cloud_provider import OLLAMA_CLOUD_URL
from app.services.memory.base import ComponentHealth

EmbeddingProviderId = Literal["tei", "ollama", "ollama_cloud"]
EMBEDDING_PROVIDERS: tuple[str, ...] = ("tei", "ollama", "ollama_cloud")
EMBED_BATCH_SIZE = 32
# Ollama's docs say 384 to 1024 is typical; anything outside this range is almost certainly not an embedding model.
MIN_DIM, MAX_DIM = 64, 8192


class VectorPathError(Exception):
    """A vector-path failure whose message is already safe to log, store and show."""


class EmbeddingFormatError(VectorPathError):
    """The embedding service answered, but not with what we expect."""


class EmbeddingModelNotFound(VectorPathError):
    """The service does not have this model."""


def describe_error(component: str, exc: BaseException) -> str:
    """A fixed-vocabulary message. Never the raw text: it can carry URLs, queries or credentials."""
    if isinstance(exc, VectorPathError):
        return str(exc)
    cause: BaseException = exc
    if isinstance(exc, ResponseHandlingException) and exc.source is not None:
        cause = exc.source
    # Timeouts first: TimeoutError is also an OSError.
    if isinstance(cause, (httpx.TimeoutException, TimeoutError)):
        return f"{component}: timed out"
    if isinstance(cause, (httpx.ConnectError, OSError)):
        return f"{component}: could not connect"
    if isinstance(cause, httpx.HTTPStatusError):
        return f"{component}: returned HTTP {cause.response.status_code}"
    if isinstance(cause, UnexpectedResponse):
        return f"{component}: returned HTTP {cause.status_code}"
    return f"{component}: failed ({type(cause).__name__})"


def slug(model: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")[:40] or "model"


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str
    model: str
    base_url: str | None = None
    api_key: str | None = field(default=None, repr=False)
    # Known after a probe. Part of the index identity.
    dim: int | None = None

    def with_dim(self, dim: int) -> "EmbeddingConfig":
        return replace(self, dim=dim)

    def identity(self) -> str:
        """Stable name of the vector space: provider, model and size. Requires the size."""
        if self.dim is None:
            raise ValueError("The vector size is not known yet")
        digest = hashlib.sha1(self.model.encode("utf-8")).hexdigest()[:6]
        return f"{self.provider}__{slug(self.model)}-{digest}__{self.dim}"

    def collection_name(self) -> str:
        return f"{settings.QDRANT_COLLECTION}__{self.identity()}"


@dataclass(frozen=True)
class ProbeResult:
    dim: int
    latency_ms: int


class EmbeddingProvider(Protocol):
    config: EmbeddingConfig

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def probe(self) -> ProbeResult:
        """Embed a short string and report the vector size. Raises VectorPathError or an httpx error."""
        ...

    async def health(self) -> ComponentHealth: ...


class _HttpEmbeddings:
    def __init__(self, config: EmbeddingConfig, transport: httpx.AsyncBaseTransport | None = None):
        self.config = config
        self._transport = transport

    # Subclasses say where to send a batch and how to read the answer.
    def _request(self, batch: list[str]) -> tuple[str, dict]:
        raise NotImplementedError

    def _headers(self) -> dict[str, str]:
        return {}

    def _vectors(self, payload: object, batch: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=settings.EMBEDDING_TIMEOUT_SECONDS, transport=self._transport)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        async with self._client() as client:
            for start in range(0, len(texts), EMBED_BATCH_SIZE):
                batch = texts[start : start + EMBED_BATCH_SIZE]
                url, body = self._request(batch)
                response = await client.post(url, json=body, headers=self._headers())
                self._raise_for_status(response)
                vectors.extend(self._vectors(response.json(), batch))
        expected = self.config.dim
        for vector in vectors:
            if expected is not None and len(vector) != expected:
                raise EmbeddingFormatError(
                    f"Embeddings: model returns size {len(vector)} but the index expects size {expected}"
                )
        return vectors

    def _raise_for_status(self, response: httpx.Response) -> None:
        response.raise_for_status()

    async def _measure(self) -> ProbeResult:
        """Embed a short string and report the size, without checking it against anything."""
        started = time.perf_counter()
        vectors = await type(self)(replace(self.config, dim=None), self._transport).embed(["ping"])
        return ProbeResult(dim=len(vectors[0]), latency_ms=int((time.perf_counter() - started) * 1000))

    async def probe(self) -> ProbeResult:
        """What choosing a model uses: also refuses sizes that cannot be an embedding model."""
        measured = await self._measure()
        dim = measured.dim
        if not MIN_DIM <= dim <= MAX_DIM:
            raise EmbeddingFormatError(
                f"Embeddings: vector size {dim} is outside the supported range {MIN_DIM} to {MAX_DIM}"
            )
        return measured

    async def health(self) -> ComponentHealth:
        try:
            await self._health_get()
            result = await self._measure()
            if self.config.dim is not None and result.dim != self.config.dim:
                return ComponentHealth(
                    False, f"Embeddings: model returns size {result.dim} but the index expects size {self.config.dim}"
                )
            return ComponentHealth(True, "Reachable and returns vectors of the expected size.")
        except Exception as exc:
            return ComponentHealth(False, describe_error("Embeddings", exc))

    async def _health_get(self) -> None:
        """Extra reachability check some services offer; the probe is the real test."""
        return None


class TeiEmbeddings(_HttpEmbeddings):
    def _base(self) -> str:
        return (self.config.base_url or settings.EMBEDDING_URL).rstrip("/")

    def _request(self, batch: list[str]) -> tuple[str, dict]:
        return f"{self._base()}/embed", {"inputs": batch}

    def _vectors(self, payload: object, batch: list[str]) -> list[list[float]]:
        if not (isinstance(payload, list) and payload and isinstance(payload[0], list)):
            raise EmbeddingFormatError("Embeddings: unexpected response format")
        if len(payload) != len(batch):
            raise EmbeddingFormatError("Embeddings: wrong number of vectors returned")
        return [[float(x) for x in vector] for vector in payload]

    async def _health_get(self) -> None:
        async with self._client() as client:
            response = await client.get(f"{self._base()}/health")
            response.raise_for_status()


class OllamaEmbeddings(_HttpEmbeddings):
    """`POST /api/embed` with `{"model", "input": [...]}`; the answer is `{"embeddings": [[...]]}`."""

    def _base(self) -> str:
        return (self.config.base_url or settings.OLLAMA_URL).rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.api_key}"} if self.config.api_key else {}

    def _request(self, batch: list[str]) -> tuple[str, dict]:
        return f"{self._base()}/api/embed", {"model": self.config.model, "input": batch}

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code == 404:
            raise EmbeddingModelNotFound("Embeddings: the model was not found on the server")
        response.raise_for_status()

    def _vectors(self, payload: object, batch: list[str]) -> list[list[float]]:
        vectors = payload.get("embeddings") if isinstance(payload, dict) else None
        if not (isinstance(vectors, list) and vectors and all(isinstance(v, list) for v in vectors)):
            raise EmbeddingFormatError("Embeddings: unexpected response format")
        if len(vectors) != len(batch):
            raise EmbeddingFormatError("Embeddings: wrong number of vectors returned")
        return [[float(x) for x in vector] for vector in vectors]


class OllamaCloudEmbeddings(OllamaEmbeddings):
    """Same call as a local Ollama, at a fixed address with the Bearer key; a saved URL is never used."""

    def _base(self) -> str:
        return OLLAMA_CLOUD_URL

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.config.api_key:
            raise VectorPathError("Embeddings: no Ollama Cloud API key is saved")
        return await super().embed(texts)


def build_embedding_provider(
    config: EmbeddingConfig, transport: httpx.AsyncBaseTransport | None = None
) -> EmbeddingProvider:
    if config.provider == "tei":
        return TeiEmbeddings(config, transport)
    if config.provider == "ollama":
        return OllamaEmbeddings(config, transport)
    if config.provider == "ollama_cloud":
        return OllamaCloudEmbeddings(config, transport)
    raise VectorPathError("Embeddings: unknown provider")


def bootstrap_config() -> EmbeddingConfig:
    """The choice made through environment variables, used until an admin saves one in Settings."""
    provider = settings.EMBEDDING_PROVIDER
    if provider == "tei":
        return EmbeddingConfig("tei", settings.EMBEDDING_MODEL, base_url=settings.EMBEDDING_URL, dim=settings.EMBEDDING_DIM)
    if provider == "ollama":
        return EmbeddingConfig("ollama", settings.OLLAMA_EMBED_MODEL, base_url=settings.OLLAMA_URL)
    return EmbeddingConfig("ollama_cloud", settings.OLLAMA_EMBED_MODEL)
