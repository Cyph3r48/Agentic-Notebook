"""Document and chunk persistence operations."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy import func
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

    async def get_by_id(self, document_id: UUID) -> Document | None:
        return await self.session.scalar(select(Document).where(Document.id == document_id))

    async def get_for_user(self, *, document_id: UUID, user_id: UUID) -> Document | None:
        return await self.session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.user_id == user_id,
            )
        )

    async def get_by_user_and_content_hash(self, *, user_id: UUID, content_hash: str) -> Document | None:
        return await self.session.scalar(
            select(Document).where(
                Document.user_id == user_id,
                Document.content_hash == content_hash,
            )
        )

    async def update_document(
        self,
        row: Document,
        *,
        content_hash: str | None = None,
        metadata_json: dict | None = None,
        status: str | None = None,
        processing_error: str | None = None,
    ) -> None:
        if content_hash is not None:
            row.content_hash = content_hash
        if metadata_json is not None:
            row.metadata_json = metadata_json
        if status is not None:
            row.status = status
        row.processing_error = processing_error
        await self.session.commit()

    async def clear_chunks(self, document_id: UUID) -> None:
        await self.session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
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

    async def count_chunks(self, document_id: UUID) -> int:
        total = await self.session.scalar(
            select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == document_id)
        )
        return int(total or 0)

    async def chunk_counts_for_user(self, user_id: UUID) -> dict[UUID, int]:
        rows = await self.session.execute(
            select(DocumentChunk.document_id, func.count(DocumentChunk.id))
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.user_id == user_id)
            .group_by(DocumentChunk.document_id)
        )
        return {document_id: int(count) for document_id, count in rows.all()}

    async def delete_document(self, row: Document) -> None:
        await self.session.delete(row)
        await self.session.commit()
