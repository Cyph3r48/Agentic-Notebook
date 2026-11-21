"""Built-in memory: Postgres chunks (keyword search), Qdrant vectors, TEI embeddings.

Vector failures never break a request: search falls back to keywords and says so, ingest still
completes, and every failure is logged at warning and kept for the health check.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import httpx
from loguru import logger
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qdrant
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories import SearchRepository
from app.services.memory.base import (
    ComponentHealth,
    IngestOutcome,
    MemoryChunk,
    MemoryHealth,
    SearchOutcome,
)

EMBED_BATCH_SIZE = 32
# Point ids must be UUIDs or integers; this namespace makes them stable per (document, chunk).
_POINT_NAMESPACE = uuid.UUID("6f1c3a52-0b7e-4d0e-9d57-2b1f4c8d9a10")


class VectorPathError(Exception):
    """A vector-path failure whose message is already safe to log, store and show."""


@dataclass(slots=True)
class _StatusRecord:
    last_error: str | None = None
    last_error_at: datetime | None = None


# One record per process; the live probes in health() stay accurate across workers.
_status = _StatusRecord()


def _record_failure(message: str) -> None:
    _status.last_error = message
    _status.last_error_at = datetime.now(tz=timezone.utc)


def _record_success() -> None:
    _status.last_error = None
    _status.last_error_at = None


def reset_status() -> None:
    _record_success()


def _point_id(document_id: UUID | str, chunk_index: int) -> str:
    return str(uuid.uuid5(_POINT_NAMESPACE, f"{document_id}:{chunk_index}"))


def _describe(component: str, exc: BaseException) -> str:
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


class BuiltinMemoryProvider:
    def __init__(
        self,
        session: AsyncSession,
        *,
        qdrant_factory: Callable[[], AsyncQdrantClient] | None = None,
        embed_transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.session = session
        self.keyword_repo = SearchRepository(session)
        self._qdrant_factory = qdrant_factory
        self._embed_transport = embed_transport

    # ---- public interface -------------------------------------------------

    async def ingest(
        self,
        *,
        user_id: UUID,
        document_id: UUID,
        original_filename: str,
        chunks: list[dict],
    ) -> IngestOutcome:
        if not settings.VECTOR_INDEXING_ENABLED or not chunks:
            return IngestOutcome(vector_indexed="disabled")
        try:
            embeddings = await self._embed_texts([str(chunk.get("content", "")) for chunk in chunks])
            points: list[qdrant.PointStruct] = []
            id_map: dict[int, str] = {}
            for chunk, vector in zip(chunks, embeddings, strict=True):
                chunk_index = int(chunk["chunk_index"])
                point_id = _point_id(document_id, chunk_index)
                id_map[chunk_index] = point_id
                metadata = chunk.get("metadata_json") or {}
                points.append(
                    qdrant.PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            "user_id": str(user_id),
                            "document_id": str(document_id),
                            "original_filename": original_filename,
                            "chunk_index": chunk_index,
                            "content": chunk.get("content", ""),
                            "content_hash": chunk.get("content_hash"),
                            "span_start": metadata.get("start"),
                            "span_end": metadata.get("end"),
                        },
                    )
                )
            async with self._qdrant() as client:
                await self._ensure_collection(client)
                await client.upsert(collection_name=settings.QDRANT_COLLECTION, points=points, wait=True)
        except Exception as exc:
            message = self._failure("ingest", exc)
            return IngestOutcome(vector_indexed=False, error=message)
        _record_success()
        return IngestOutcome(id_map=id_map, vector_indexed=True)

    async def search(
        self,
        *,
        user_id: UUID,
        query: str,
        limit: int,
        offset: int = 0,
        min_score: float = 0.1,
    ) -> SearchOutcome:
        if not settings.VECTOR_INDEXING_ENABLED:
            return SearchOutcome(await self._keyword(user_id, query, limit, offset, min_score), mode="keyword")

        try:
            vector_hits = await self._vector_search(user_id, query, limit, offset, min_score)
        except Exception as exc:
            message = self._failure("search", exc)
            results = await self._keyword(user_id, query, limit, offset, min_score)
            return SearchOutcome(results, mode="keyword_fallback", degraded_reason=message)

        _record_success()
        if vector_hits:
            return SearchOutcome(vector_hits, mode="vector")
        return SearchOutcome(await self._keyword(user_id, query, limit, offset, min_score), mode="keyword")

    async def delete(self, *, user_id: UUID, document_id: UUID) -> None:
        if not settings.VECTOR_INDEXING_ENABLED:
            return
        try:
            async with self._qdrant() as client:
                if not await client.collection_exists(settings.QDRANT_COLLECTION):
                    return
                await client.delete(
                    collection_name=settings.QDRANT_COLLECTION,
                    points_selector=qdrant.FilterSelector(
                        filter=qdrant.Filter(
                            must=[
                                qdrant.FieldCondition(key="user_id", match=qdrant.MatchValue(value=str(user_id))),
                                qdrant.FieldCondition(
                                    key="document_id", match=qdrant.MatchValue(value=str(document_id))
                                ),
                            ]
                        )
                    ),
                    wait=True,
                )
        except Exception as exc:
            # The Postgres delete must still go ahead, so this is recorded, not raised.
            self._failure("delete", exc)

    async def health(self) -> MemoryHealth:
        if not settings.VECTOR_INDEXING_ENABLED:
            return MemoryHealth(
                status="disabled",
                backend="builtin",
                vector_enabled=False,
                detail="Vector search is off. Search uses keywords only.",
            )

        components = {
            "qdrant": await self._probe_qdrant(),
            "embeddings": await self._probe_embeddings(),
        }
        failing = [name for name, part in components.items() if not part.ok]
        if not failing:
            status, detail = "ok", "Vector and keyword search are working."
        elif len(failing) == len(components):
            status, detail = "down", "Vector search is unavailable. Search uses keywords only."
        else:
            status, detail = "degraded", "Part of vector search is unavailable. Search uses keywords only."
        return MemoryHealth(
            status=status,
            backend="builtin",
            vector_enabled=True,
            detail=detail,
            components=components,
            last_error=_status.last_error,
            last_error_at=_status.last_error_at,
        )

    # ---- internals ----------------------------------------------------------

    def _failure(self, action: str, exc: Exception) -> str:
        component = "Embeddings" if _is_embedding_error(exc) else "Qdrant"
        message = _describe(component, exc)
        _record_failure(message)
        logger.warning("Memory vector {action} failed: {message}", action=action, message=message)
        return message

    async def _keyword(self, user_id: UUID, query: str, limit: int, offset: int, min_score: float) -> list[MemoryChunk]:
        rows = await self.keyword_repo.search_chunks(
            user_id=user_id, query=query, limit=limit, offset=offset, min_score=min_score
        )
        return [
            MemoryChunk(
                document_id=str(row["document_id"]),
                original_filename=row["original_filename"],
                chunk_index=int(row["chunk_index"]),
                content=row["content"],
                score=float(row.get("score") or 0.0),
                content_hash=row.get("content_hash"),
                span_start=row.get("span_start"),
                span_end=row.get("span_end"),
            )
            for row in rows
        ]

    async def _vector_search(
        self, user_id: UUID, query: str, limit: int, offset: int, min_score: float
    ) -> list[MemoryChunk]:
        embedding = (await self._embed_texts([query]))[0]
        async with self._qdrant() as client:
            if not await client.collection_exists(settings.QDRANT_COLLECTION):
                return []
            response = await client.query_points(
                collection_name=settings.QDRANT_COLLECTION,
                query=embedding,
                limit=limit,
                offset=offset,
                score_threshold=min_score,
                query_filter=qdrant.Filter(
                    must=[qdrant.FieldCondition(key="user_id", match=qdrant.MatchValue(value=str(user_id)))]
                ),
            )
        hits: list[MemoryChunk] = []
        for point in response.points:
            payload = point.payload or {}
            if not payload.get("document_id"):
                continue
            hits.append(
                MemoryChunk(
                    document_id=str(payload["document_id"]),
                    original_filename=str(payload.get("original_filename", "unknown")),
                    chunk_index=int(payload.get("chunk_index", 0)),
                    content=str(payload.get("content", "")),
                    score=float(point.score or 0.0),
                    content_hash=payload.get("content_hash"),
                    span_start=payload.get("span_start"),
                    span_end=payload.get("span_end"),
                )
            )
        return hits

    @asynccontextmanager
    async def _qdrant(self) -> AsyncIterator[AsyncQdrantClient]:
        client = (
            self._qdrant_factory()
            if self._qdrant_factory
            else AsyncQdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY or None,
                timeout=settings.QDRANT_TIMEOUT_SECONDS,
            )
        )
        try:
            yield client
        finally:
            await client.close()

    async def _ensure_collection(self, client: AsyncQdrantClient) -> None:
        if not await client.collection_exists(settings.QDRANT_COLLECTION):
            await client.create_collection(
                collection_name=settings.QDRANT_COLLECTION,
                vectors_config=qdrant.VectorParams(size=settings.EMBEDDING_DIM, distance=qdrant.Distance.COSINE),
            )
            return
        size = await self._collection_size(client)
        if size is not None and size != settings.EMBEDDING_DIM:
            raise VectorPathError(
                f"Qdrant: collection vectors have size {size} but EMBEDDING_DIM is {settings.EMBEDDING_DIM}"
            )

    @staticmethod
    async def _collection_size(client: AsyncQdrantClient) -> int | None:
        info = await client.get_collection(settings.QDRANT_COLLECTION)
        vectors = info.config.params.vectors
        return getattr(vectors, "size", None)

    async def _embed_texts(self, inputs: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        async with httpx.AsyncClient(
            timeout=settings.EMBEDDING_TIMEOUT_SECONDS, transport=self._embed_transport
        ) as client:
            for start in range(0, len(inputs), EMBED_BATCH_SIZE):
                batch = inputs[start : start + EMBED_BATCH_SIZE]
                response = await client.post(f"{settings.EMBEDDING_URL.rstrip('/')}/embed", json={"inputs": batch})
                response.raise_for_status()
                payload = response.json()
                if not (isinstance(payload, list) and payload and isinstance(payload[0], list)):
                    raise EmbeddingFormatError("Embeddings: unexpected response format")
                if len(payload) != len(batch):
                    raise EmbeddingFormatError("Embeddings: wrong number of vectors returned")
                vectors.extend([[float(x) for x in vector] for vector in payload])
        for vector in vectors:
            if len(vector) != settings.EMBEDDING_DIM:
                raise EmbeddingFormatError(
                    f"Embeddings: model returns size {len(vector)} but EMBEDDING_DIM is {settings.EMBEDDING_DIM}"
                )
        return vectors

    async def _probe_qdrant(self) -> ComponentHealth:
        try:
            async with self._qdrant() as client:
                if not await client.collection_exists(settings.QDRANT_COLLECTION):
                    return ComponentHealth(True, "Reachable. The collection is created on the first upload.")
                size = await self._collection_size(client)
            if size is not None and size != settings.EMBEDDING_DIM:
                return ComponentHealth(
                    False, f"Collection vectors have size {size} but EMBEDDING_DIM is {settings.EMBEDDING_DIM}"
                )
            return ComponentHealth(True, "Reachable and the collection matches EMBEDDING_DIM.")
        except Exception as exc:
            return ComponentHealth(False, _describe("Qdrant", exc))

    async def _probe_embeddings(self) -> ComponentHealth:
        try:
            async with httpx.AsyncClient(
                timeout=settings.EMBEDDING_TIMEOUT_SECONDS, transport=self._embed_transport
            ) as client:
                response = await client.get(f"{settings.EMBEDDING_URL.rstrip('/')}/health")
                response.raise_for_status()
            await self._embed_texts(["ping"])
            return ComponentHealth(True, "Reachable and returns vectors of the expected size.")
        except Exception as exc:
            return ComponentHealth(False, _describe("Embeddings", exc))


class EmbeddingFormatError(VectorPathError):
    """The embedding service answered, but not with what we expect."""


def _is_embedding_error(exc: BaseException) -> bool:
    if isinstance(exc, EmbeddingFormatError):
        return True
    if isinstance(exc, httpx.HTTPError):
        return True
    return False
