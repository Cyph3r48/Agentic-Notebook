"""Search persistence operations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentChunk


class SearchRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def search_chunks(self, *, user_id: UUID, query: str, limit: int) -> list[dict]:
        normalized = query.strip()
        pattern = f"%{normalized}%"
        similarity = func.similarity(DocumentChunk.content, normalized)

        rows = (
            await self.session.execute(
                select(
                    Document.id.label("document_id"),
                    Document.original_filename.label("original_filename"),
                    DocumentChunk.chunk_index.label("chunk_index"),
                    DocumentChunk.content.label("content"),
                    similarity.label("score"),
                )
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(
                    Document.user_id == user_id,
                    Document.status == "completed",
                    or_(
                        DocumentChunk.content.ilike(pattern),
                        similarity >= 0.1,
                    ),
                )
                .order_by(desc("score"), Document.created_at.desc(), DocumentChunk.chunk_index.asc())
                .limit(limit)
            )
        ).all()

        return [
            {
                "document_id": str(row.document_id),
                "original_filename": row.original_filename,
                "chunk_index": row.chunk_index,
                "content": row.content,
                "score": float(row.score or 0.0),
            }
            for row in rows
        ]
