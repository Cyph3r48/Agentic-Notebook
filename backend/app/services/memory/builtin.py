"""Built-in memory: Postgres chunks (keyword search), Qdrant vectors, and a chosen embedding model.

Vector failures never break a request: search falls back to keywords and says so, ingest still
completes, and every failure is logged at warning and kept for the health check.

The embedding model is chosen by an admin (see `embedding_settings_service`). Each choice (provider, model and
vector size) has its own Qdrant collection, so vectors from different models are never mixed, and a query is always
embedded with the same configuration as the collection it searches.
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
from qdrant_client.http.exceptions import UnexpectedResponse
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
from app.services.memory.embeddings import (
    EmbeddingConfig,
    EmbeddingFormatError,
    VectorPathError,
    build_embedding_provider,
    describe_error,
)

# Point ids must be UUIDs or integers; this namespace makes them stable per (document, chunk).
_POINT_NAMESPACE = uuid.UUID("6f1c3a52-0b7e-4d0e-9d57-2b1f4c8d9a10")


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


_describe = describe_error  # kept under the old name for callers inside this package


class BuiltinMemoryProvider:
    def __init__(
        self,
        session: AsyncSession,
        *,
        qdrant_factory: Callable[[], AsyncQdrantClient] | None = None,
        embed_transport: httpx.AsyncBaseTransport | None = None,
        embedding_config: EmbeddingConfig | None = None,
        document_stats=None,
    ):
        self.session = session
        self.keyword_repo = SearchRepository(session)
        self._qdrant_factory = qdrant_factory
        self._embed_transport = embed_transport
        # A fixed config (used by tests); otherwise the admin's choice is read from the database.
        self._fixed_config = embedding_config
        self._document_stats = document_stats

    async def _config(self) -> EmbeddingConfig:
        """The embedding configuration to use right now, with its vector size. Raises VectorPathError."""
        if self._fixed_config is not None:
            config = self._fixed_config
            if config.dim is None:
                config = config.with_dim((await build_embedding_provider(config, self._embed_transport).probe()).dim)
            return config
        from app.repositories import SystemSettingsRepository
        from app.services.embedding_settings_service import EmbeddingSettingsService

        return await EmbeddingSettingsService(SystemSettingsRepository(self.session)).active_config()

    def _embedder(self, config: EmbeddingConfig):
        return build_embedding_provider(config, self._embed_transport)

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
            config = await self._config()
            embeddings = await self._embedder(config).embed([str(chunk.get("content", "")) for chunk in chunks])
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
                await self._ensure_collection(client, config)
                await client.upsert(collection_name=config.collection_name(), points=points, wait=True)
        except Exception as exc:
            message = self._failure("ingest", exc)
            return IngestOutcome(vector_indexed=False, error=message)
        _record_success()
        return IngestOutcome(id_map=id_map, vector_indexed=True, index=config.identity())

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
        """Remove a document's points from the active index. Older indexes are left alone."""
        if not settings.VECTOR_INDEXING_ENABLED:
            return
        try:
            collection = (await self._config()).collection_name()
            async with self._qdrant() as client:
                if not await client.collection_exists(collection):
                    return
                await client.delete(
                    collection_name=collection,
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

        try:
            config = await self._config()
        except Exception as exc:
            message = describe_error("Embeddings", exc)
            components = {
                "qdrant": await self._probe_qdrant(None),
                "embeddings": ComponentHealth(False, message),
            }
            return self._health_from(components, None)

        components = {
            "qdrant": await self._probe_qdrant(config),
            "embeddings": await self._embedder(config).health(),
        }
        return self._health_from(components, config)

    def _health_from(self, components: dict[str, ComponentHealth], config: EmbeddingConfig | None) -> MemoryHealth:
        failing = [name for name, part in components.items() if not part.ok]
        if not failing:
            status, detail = "ok", "Vector and keyword search are working."
        elif len(failing) == len(components):
            status, detail = "down", "Vector search is unavailable. Search uses keywords only."
        else:
            status, detail = "degraded", "Part of vector search is unavailable. Search uses keywords only."
        embedding = None
        if config is not None:
            embedding = {"provider": config.provider, "model": config.model, "dim": config.dim, "identity": config.identity()}
        return MemoryHealth(
            status=status,
            backend="builtin",
            vector_enabled=True,
            detail=detail,
            components=components,
            last_error=_status.last_error,
            last_error_at=_status.last_error_at,
            embedding=embedding,
        )

    async def index_counts(self, identity: str) -> tuple[int | None, int | None]:
        """(completed documents, documents already in this index). None when the database cannot be asked."""
        try:
            stats = self._document_stats
            if stats is None:
                from app.repositories import DocumentRepository
                from app.services.embedding_settings_service import RepositoryIndexStats

                stats = RepositoryIndexStats(DocumentRepository(self.session))
            return await stats.counts(identity)
        except Exception as exc:
            logger.debug("Could not count indexed documents: {error}", error=type(exc).__name__)
            return None, None

    # ---- internals ----------------------------------------------------------

    def _failure(self, action: str, exc: Exception) -> str:
        component = "Embeddings" if isinstance(exc, httpx.HTTPError) else "Qdrant"
        message = describe_error(component, exc)
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
        config = await self._config()
        # The query is embedded with the same configuration that names the collection it searches.
        embedding = (await self._embedder(config).embed([query]))[0]
        async with self._qdrant() as client:
            if not await client.collection_exists(config.collection_name()):
                return []
            response = await client.query_points(
                collection_name=config.collection_name(),
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

    async def _ensure_collection(self, client: AsyncQdrantClient, config: EmbeddingConfig) -> None:
        name = config.collection_name()
        if not await client.collection_exists(name):
            try:
                await client.create_collection(
                    collection_name=name,
                    vectors_config=qdrant.VectorParams(size=config.dim, distance=qdrant.Distance.COSINE),
                )
                return
            except UnexpectedResponse as exc:
                # Documents are processed concurrently: another upload created the collection between our check
                # and our create. That is fine; use it (after the size check below).
                if exc.status_code != 409:
                    raise
        size = await self._collection_size(client, name)
        if size is not None and size != config.dim:
            raise VectorPathError(f"Qdrant: collection vectors have size {size} but the index expects size {config.dim}")

    @staticmethod
    async def _collection_size(client: AsyncQdrantClient, name: str) -> int | None:
        info = await client.get_collection(name)
        vectors = info.config.params.vectors
        return getattr(vectors, "size", None)

    async def _probe_qdrant(self, config: EmbeddingConfig | None) -> ComponentHealth:
        try:
            async with self._qdrant() as client:
                if config is None:
                    await client.get_collections()
                    return ComponentHealth(True, "Reachable.")
                name = config.collection_name()
                if not await client.collection_exists(name):
                    return ComponentHealth(True, "Reachable. The index is created on the first upload.")
                size = await self._collection_size(client, name)
            if size is not None and size != config.dim:
                return ComponentHealth(False, f"Collection vectors have size {size} but the index expects size {config.dim}")
            return ComponentHealth(True, "Reachable and the index matches the embedding model.")
        except Exception as exc:
            return ComponentHealth(False, describe_error("Qdrant", exc))


__all__ = ["BuiltinMemoryProvider", "EmbeddingFormatError", "VectorPathError", "reset_status"]
