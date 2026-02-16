"""Document and chunk persistence operations."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentChunk


class DocumentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_document(
        self,
        *,
        user_id: UUID,
        filename: str,
        original_filename: str,
        file_type: str,
        file_size: int,
        content_hash: str,
        storage_path: str,
        metadata_json: dict | None = None,
        status: str = "pending",
    ) -> Document:
        row = Document(
            user_id=user_id,
            filename=filename,
            original_filename=original_filename,
            file_type=file_type,
            file_size=file_size,
            content_hash=content_hash,
            storage_path=storage_path,
            metadata_json=metadata_json or {},
            status=status,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def update_status(
        self,
        row: Document,
        *,
        status: str,
        processing_error: str | None = None,
    ) -> None:
        row.status = status
        row.processing_error = processing_error
        await self.session.commit()

    async def add_chunks(
        self,
        *,
        document_id: UUID,
        chunks: list[dict],
    ) -> None:
        for chunk in chunks:
            self.session.add(
                DocumentChunk(
                    document_id=document_id,
                    chunk_index=chunk["chunk_index"],
                    content=chunk["content"],
                    content_hash=chunk["content_hash"],
                    metadata_json=chunk.get("metadata_json", {}),
                    token_count=chunk.get("token_count"),
                    vector_id=chunk.get("vector_id"),
                )
            )
        await self.session.commit()

    async def list_for_user(self, user_id: UUID) -> Sequence[Document]:
        return (
            await self.session.scalars(
                select(Document).where(Document.user_id == user_id).order_by(Document.created_at.desc())
            )
        ).all()

