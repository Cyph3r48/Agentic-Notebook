"""Document ingestion and processing service."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from bs4 import BeautifulSoup
from docx import Document as DocxDocument
from fastapi import UploadFile
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Document
from app.repositories import DocumentRepository
from app.services.smc_service import SMCService


class DocumentService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = DocumentRepository(session)

    async def ingest_upload(self, *, user_id: UUID, upload: UploadFile) -> tuple[Document, int]:
        original_filename = upload.filename or "upload.txt"
        file_ext = Path(original_filename).suffix.lower()
        if not file_ext:
            raise ValueError("File must have an extension")
        if file_ext not in settings.ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {file_ext}")

        data = await upload.read()
        if not data:
            raise ValueError("Uploaded file is empty")

        max_size_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if len(data) > max_size_bytes:
            raise ValueError(f"File exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit")

        upload_dir = Path(settings.UPLOAD_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)
        stored_filename = f"{uuid4().hex}{file_ext}"
        storage_path = upload_dir / stored_filename
        storage_path.write_bytes(data)

        extracted = self._extract_text(data, file_ext)
        content_type = "html" if file_ext == ".html" else "text"
        sanitized = await SMCService.sanitize_content(extracted, content_type=content_type)
        content_hash = SMCService.compute_hash(sanitized)

        doc = await self.repo.create_document(
            user_id=user_id,
            filename=stored_filename,
            original_filename=original_filename,
            file_type=file_ext.lstrip("."),
            file_size=len(data),
            content_hash=content_hash,
            storage_path=str(storage_path),
            metadata_json={
                "text_length": len(sanitized),
                "content_hash": content_hash,
            },
            status="processing",
        )

        try:
            chunks = self._chunk_text(sanitized)
            if chunks:
                await self.repo.add_chunks(document_id=doc.id, chunks=chunks)
            await self.repo.update_status(doc, status="completed")
            await self.session.refresh(doc)
            return doc, len(chunks)
        except Exception as exc:
            await self.repo.update_status(doc, status="failed", processing_error=str(exc))
            raise

    def _extract_text(self, data: bytes, file_ext: str) -> str:
        if file_ext in {".txt", ".md"}:
            return data.decode("utf-8", errors="replace")
        if file_ext == ".html":
            html = data.decode("utf-8", errors="replace")
            return BeautifulSoup(html, "lxml").get_text(separator="\n")
        if file_ext == ".pdf":
            reader = PdfReader(BytesIO(data))
            return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        if file_ext == ".docx":
            doc = DocxDocument(BytesIO(data))
            return "\n".join(paragraph.text for paragraph in doc.paragraphs).strip()
        raise ValueError(f"Unsupported file type: {file_ext}")

    def _chunk_text(self, text: str) -> list[dict]:
        normalized = text.strip()
        if not normalized:
            return []

        chunk_size = settings.CHUNK_SIZE
        overlap = settings.CHUNK_OVERLAP
        step = max(chunk_size - overlap, 1)
        chunks: list[dict] = []

        for index, start in enumerate(range(0, len(normalized), step)):
            content = normalized[start : start + chunk_size].strip()
            if not content:
                continue
            chunks.append(
                {
                    "chunk_index": index,
                    "content": content,
                    "content_hash": SMCService.compute_hash(content),
                    "metadata_json": {"start": start, "end": min(start + chunk_size, len(normalized))},
                    "token_count": len(content.split()),
                }
            )
            if start + chunk_size >= len(normalized):
                break

        return chunks

