"""Hybrid vector search with safe fallback to keyword chunk search."""

from __future__ import annotations

from uuid import UUID

import httpx
from loguru import logger
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qdrant
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories import SearchRepository


class VectorSearchService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.keyword_repo = SearchRepository(session)

    async def search(
        self,
        *,
        user_id: UUID,
        query: str,
        limit: int,
        offset: int = 0,
        min_score: float = 0.1,
    ) -> list[dict]:
        vector_results = await self._search_qdrant(user_id=user_id, query=query, limit=limit, offset=offset)
        if vector_results:
            return vector_results
        return await self.keyword_repo.search_chunks(
            user_id=user_id,
            query=query,
            limit=limit,
            offset=offset,
            min_score=min_score,
        )

    async def index_document_chunks(
        self,
        *,
        user_id: UUID,
        document_id: UUID,
        original_filename: str,
        chunks: list[dict],
    ) -> dict[int, str]:
        if not settings.VECTOR_INDEXING_ENABLED or not chunks:
            return {}
        try:
            embeddings = await self._embed_texts([str(chunk.get("content", "")) for chunk in chunks])
            client = AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None, timeout=2.0)
            await self._ensure_collection(client)
            points: list[qdrant.PointStruct] = []
            id_map: dict[int, str] = {}
            for chunk, vector in zip(chunks, embeddings, strict=False):
                chunk_index = int(chunk["chunk_index"])
                point_id = f"{document_id}:{chunk_index}"
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
            if points:
                await client.upsert(collection_name=settings.QDRANT_COLLECTION, points=points, wait=False)
            await client.close()
            return id_map
        except Exception as exc:
            logger.debug("Vector indexing skipped due to error: {}", str(exc))
            return {}

    async def delete_document_points(self, *, user_id: UUID, document_id: UUID) -> None:
        if not settings.VECTOR_INDEXING_ENABLED:
            return
        try:
            client = AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None, timeout=2.0)
            await client.delete(
                collection_name=settings.QDRANT_COLLECTION,
                points_selector=qdrant.FilterSelector(
                    filter=qdrant.Filter(
                        must=[
                            qdrant.FieldCondition(key="user_id", match=qdrant.MatchValue(value=str(user_id))),
                            qdrant.FieldCondition(key="document_id", match=qdrant.MatchValue(value=str(document_id))),
                        ]
                    )
                ),
                wait=False,
            )
            await client.close()
        except Exception as exc:
            logger.debug("Vector delete skipped due to error: {}", str(exc))

    async def _search_qdrant(self, *, user_id: UUID, query: str, limit: int, offset: int) -> list[dict]:
        if not settings.VECTOR_INDEXING_ENABLED:
            return []
        try:
            embedding = await self._embed_query(query)
            client = AsyncQdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY or None,
                timeout=2.0,
            )
            results = await client.search(
                collection_name=settings.QDRANT_COLLECTION,
                query_vector=embedding,
                limit=limit + offset,
                query_filter=qdrant.Filter(
                    must=[
                        qdrant.FieldCondition(
                            key="user_id",
                            match=qdrant.MatchValue(value=str(user_id)),
                        )
                    ]
                ),
            )
            await client.close()
            trimmed = results[offset : offset + limit]
            mapped: list[dict] = []
            for row in trimmed:
                payload = row.payload or {}
                if not payload:
                    continue
                mapped.append(
                    {
                        "document_id": str(payload.get("document_id", "")),
                        "original_filename": str(payload.get("original_filename", "unknown")),
                        "chunk_index": int(payload.get("chunk_index", 0)),
                        "content": str(payload.get("content", "")),
                        "content_hash": payload.get("content_hash"),
                        "span_start": payload.get("span_start"),
                        "span_end": payload.get("span_end"),
                        "score": float(row.score or 0.0),
                    }
                )
            return [item for item in mapped if item["document_id"]]
        except Exception as exc:
            logger.debug("Vector search fallback triggered: {}", str(exc))
            return []

    async def _embed_query(self, query: str) -> list[float]:
        return (await self._embed_texts([query]))[0]

    async def _embed_texts(self, inputs: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{settings.EMBEDDING_URL.rstrip('/')}/embed",
                json={"inputs": inputs},
            )
            response.raise_for_status()
            payload = response.json()

        if isinstance(payload, list) and payload and isinstance(payload[0], list):
            return [[float(x) for x in vector] for vector in payload]
        if isinstance(payload, list):
            return [[float(x) for x in payload]]
        raise RuntimeError("Unexpected embedding response format")

    async def _ensure_collection(self, client: AsyncQdrantClient) -> None:
        try:
            await client.get_collection(settings.QDRANT_COLLECTION)
        except Exception:
            await client.recreate_collection(
                collection_name=settings.QDRANT_COLLECTION,
                vectors_config=qdrant.VectorParams(size=settings.EMBEDDING_DIM, distance=qdrant.Distance.COSINE),
            )
