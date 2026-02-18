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

    async def _search_qdrant(self, *, user_id: UUID, query: str, limit: int, offset: int) -> list[dict]:
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
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{settings.EMBEDDING_URL.rstrip('/')}/embed",
                json={"inputs": query},
            )
            response.raise_for_status()
            payload = response.json()

        if isinstance(payload, list) and payload and isinstance(payload[0], list):
            return [float(x) for x in payload[0]]
        if isinstance(payload, list):
            return [float(x) for x in payload]
        raise RuntimeError("Unexpected embedding response format")
