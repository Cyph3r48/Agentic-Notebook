"""Document ingestion and processing service."""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile
from uuid import UUID, uuid4

from bs4 import BeautifulSoup
from docx import Document as DocxDocument
from fastapi import UploadFile
from loguru import logger
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
        doc, is_new = await self.stage_upload(user_id=user_id, upload=upload)
        if not is_new:
            return doc, 0
        chunk_count = await self.process_document(doc.id)
        refreshed = await self.repo.get_by_id(doc.id)
        if refreshed is None:
            raise RuntimeError("Document missing after processing")
        return refreshed, chunk_count

    async def stage_upload(self, *, user_id: UUID, upload: UploadFile) -> tuple[Document, bool]:
        original_filename = upload.filename or "upload.txt"
        declared_ext = Path(original_filename).suffix.lower()
        file_ext = declared_ext
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

        detected_ext = self._detect_file_type(data=data, declared_ext=declared_ext)
        if detected_ext in {".pdf", ".docx"} and detected_ext != declared_ext:
            raise ValueError(f"File content does not match declared type: {declared_ext}")

        file_ext = detected_ext
        content_hash = hashlib.sha256(data).hexdigest()
        existing = await self.repo.get_by_user_and_content_hash(user_id=user_id, content_hash=content_hash)
        if existing is not None:
            return existing, False

        upload_dir = Path(settings.UPLOAD_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)
        stored_filename = f"{uuid4().hex}{file_ext}"
        storage_path = upload_dir / stored_filename
        storage_path.write_bytes(data)
        try:
            doc = await self.repo.create_document(
                user_id=user_id,
                filename=stored_filename,
                original_filename=original_filename,
                file_type=file_ext.lstrip("."),
                file_size=len(data),
                content_hash=content_hash,
                storage_path=str(storage_path),
                metadata_json={
                    "text_length": 0,
                    "content_hash": content_hash,
                },
                status="pending",
            )
        except Exception:
            try:
                storage_path.unlink(missing_ok=True)
            except Exception:
                logger.warning("Failed to cleanup staged file path={path}", path=str(storage_path))
            raise
        return doc, True

    def _detect_file_type(self, *, data: bytes, declared_ext: str) -> str:
        # Strong signatures first.
        if data.startswith(b"%PDF-"):
            return ".pdf"

        if data.startswith(b"PK\x03\x04"):
            try:
                with ZipFile(BytesIO(data)) as archive:
                    names = set(archive.namelist())
                if "[Content_Types].xml" in names and any(name.startswith("word/") for name in names):
                    return ".docx"
            except BadZipFile:
                pass

        # Heuristic for HTML.
        sample = data[:8192].decode("utf-8", errors="ignore").lower()
        if "<html" in sample or "<!doctype html" in sample:
            return ".html"

        # Markdown/text fallback for human-readable payloads.
        if declared_ext in {".txt", ".md"}:
            return declared_ext
        if declared_ext == ".html":
            return ".html"

        if declared_ext == ".pdf":
            raise ValueError("File content does not match declared type: .pdf")
        if declared_ext == ".docx":
            raise ValueError("File content does not match declared type: .docx")

        return declared_ext

    async def process_document(self, document_id: UUID) -> int:
        doc = await self.repo.get_by_id(document_id)
        if doc is None:
            logger.warning("Skipping processing for missing document_id={document_id}", document_id=str(document_id))
            return 0

        await self.repo.update_status(doc, status="processing", processing_error=None)
        try:
            file_ext = f".{doc.file_type}"
            storage_path = Path(doc.storage_path)
            if not storage_path.exists():
                raise ValueError("Stored file not found")

            data = storage_path.read_bytes()
            extracted = self._extract_text(data, file_ext)
            content_type = "html" if file_ext == ".html" else "text"
            sanitized = await SMCService.sanitize_content(extracted, content_type=content_type)
            content_hash = SMCService.compute_hash(sanitized)
            chunks = self._chunk_text(sanitized)
            await self.repo.clear_chunks(doc.id)
            if chunks:
                await self.repo.add_chunks(document_id=doc.id, chunks=chunks)
            await self.repo.update_document(
                doc,
                content_hash=content_hash,
                metadata_json={
                    **(doc.metadata_json or {}),
                    "text_length": len(sanitized),
                    "content_hash": content_hash,
                },
                status="completed",
                processing_error=None,
            )
            return len(chunks)
        except Exception as exc:
            await self.repo.update_status(doc, status="failed", processing_error=str(exc))
            logger.exception("Document processing failed document_id={document_id}: {}", str(exc), document_id=str(document_id))
            raise

    async def delete_document_for_user(self, *, document_id: UUID, user_id: UUID) -> bool:
        doc = await self.repo.get_for_user(document_id=document_id, user_id=user_id)
        if doc is None:
            return False

        await self.repo.delete_document(doc)
        try:
            Path(doc.storage_path).unlink(missing_ok=True)
        except Exception:
            logger.warning("Failed to cleanup deleted file path={path}", path=doc.storage_path)
        return True

    def _extract_text(self, data: bytes, file_ext: str) -> str:
        if file_ext in {".txt", ".md"}:
            try:
                return data.decode("utf-8", errors="replace")
            except Exception as exc:
                raise ValueError("Unable to read text/markdown file content") from exc
        if file_ext == ".html":
            try:
                html = data.decode("utf-8", errors="replace")
                return BeautifulSoup(html, "lxml").get_text(separator="\n")
            except Exception as exc:
                raise ValueError("Unable to parse HTML document content") from exc
        if file_ext == ".pdf":
            try:
                reader = PdfReader(BytesIO(data))
                return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
            except Exception as exc:
                raise ValueError("Unable to extract text from PDF file") from exc
        if file_ext == ".docx":
            try:
                doc = DocxDocument(BytesIO(data))
                return "\n".join(paragraph.text for paragraph in doc.paragraphs).strip()
            except Exception as exc:
                raise ValueError("Unable to extract text from DOCX file") from exc
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
