"""Memory interface: the only thing chat, search and ingest know about document memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

# vector: Qdrant answered. keyword: vectors off or no vector hits. keyword_fallback: the vector path failed.
SearchMode = Literal["vector", "keyword", "keyword_fallback"]
MemoryStatusName = Literal["ok", "degraded", "down", "disabled"]


class MemoryBackendUnavailable(RuntimeError):
    """The configured MEMORY_BACKEND has no adapter yet."""


@dataclass(slots=True)
class MemoryChunk:
    document_id: str
    original_filename: str
    chunk_index: int
    content: str
    score: float
    content_hash: str | None = None
    span_start: int | None = None
    span_end: int | None = None

    def as_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "original_filename": self.original_filename,
            "chunk_index": self.chunk_index,
            "content": self.content,
            "score": self.score,
            "content_hash": self.content_hash,
            "span_start": self.span_start,
            "span_end": self.span_end,
        }


@dataclass(slots=True)
class SearchOutcome:
    results: list[MemoryChunk]
    mode: SearchMode
    degraded_reason: str | None = None


@dataclass(slots=True)
class IngestOutcome:
    # chunk_index -> vector point id, for the chunks that were indexed.
    id_map: dict[int, str] = field(default_factory=dict)
    # True: indexed. False: tried and failed (keyword search still works). "disabled": vectors are off.
    vector_indexed: bool | Literal["disabled"] = "disabled"
    error: str | None = None
    # Identity of the index the chunks went into (embedding provider, model and size). None unless indexed.
    index: str | None = None


@dataclass(slots=True)
class ComponentHealth:
    ok: bool
    detail: str


@dataclass(slots=True)
class MemoryHealth:
    status: MemoryStatusName
    backend: str
    vector_enabled: bool
    detail: str
    components: dict[str, ComponentHealth] = field(default_factory=dict)
    last_error: str | None = None
    last_error_at: datetime | None = None
    # Which embedding model is active, and how many documents are already in its index.
    embedding: dict | None = None
    documents_total: int | None = None
    documents_in_index: int | None = None


class MemoryProvider(Protocol):
    """Everything the app needs from a memory backend. `builtin` is Postgres + Qdrant + TEI."""

    async def ingest(
        self,
        *,
        user_id: UUID,
        document_id: UUID,
        original_filename: str,
        chunks: list[dict],
    ) -> IngestOutcome: ...

    async def search(
        self,
        *,
        user_id: UUID,
        query: str,
        limit: int,
        offset: int = 0,
        min_score: float = 0.1,
    ) -> SearchOutcome: ...

    async def delete(self, *, user_id: UUID, document_id: UUID) -> None: ...

    async def health(self) -> MemoryHealth: ...
