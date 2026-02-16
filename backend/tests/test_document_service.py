from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import UploadFile

from app.core.config import settings
from app.services.document_service import DocumentService


class _FakeRepo:
    def __init__(self):
        self.created = None
        self.chunks = []
        self.statuses = []

    async def create_document(self, **kwargs):
        self.created = kwargs
        return SimpleNamespace(
            id=uuid4(),
            filename=kwargs["filename"],
            original_filename=kwargs["original_filename"],
            file_type=kwargs["file_type"],
            file_size=kwargs["file_size"],
            content_hash=kwargs["content_hash"],
            storage_path=kwargs["storage_path"],
            status=kwargs["status"],
            created_at=datetime.now(tz=timezone.utc),
        )

    async def add_chunks(self, *, document_id, chunks):
        self.chunks = chunks

    async def update_status(self, row, *, status, processing_error=None):
        row.status = status
        self.statuses.append((status, processing_error))


class _FakeSession:
    async def refresh(self, _doc):
        return None


@pytest.mark.asyncio
async def test_ingest_upload_rejects_unsupported_extension(tmp_path):
    service = DocumentService(_FakeSession())
    service.repo = _FakeRepo()

    original_upload_dir = settings.UPLOAD_DIR
    settings.UPLOAD_DIR = str(tmp_path)
    try:
        upload = UploadFile(filename="bad.exe", file=BytesIO(b"hello"))
        with pytest.raises(ValueError, match="Unsupported file type"):
            await service.ingest_upload(user_id=uuid4(), upload=upload)
    finally:
        settings.UPLOAD_DIR = original_upload_dir


@pytest.mark.asyncio
async def test_ingest_upload_stores_and_chunks_text(tmp_path):
    service = DocumentService(_FakeSession())
    repo = _FakeRepo()
    service.repo = repo

    original_upload_dir = settings.UPLOAD_DIR
    original_chunk_size = settings.CHUNK_SIZE
    original_overlap = settings.CHUNK_OVERLAP
    settings.UPLOAD_DIR = str(tmp_path)
    settings.CHUNK_SIZE = 10
    settings.CHUNK_OVERLAP = 2
    try:
        upload = UploadFile(filename="notes.txt", file=BytesIO(b"abcdefghijklmnopqrstuvwxyz"))
        doc, chunk_count = await service.ingest_upload(user_id=uuid4(), upload=upload)
    finally:
        settings.UPLOAD_DIR = original_upload_dir
        settings.CHUNK_SIZE = original_chunk_size
        settings.CHUNK_OVERLAP = original_overlap

    assert repo.created is not None
    assert repo.created["original_filename"] == "notes.txt"
    assert chunk_count > 1
    assert len(repo.chunks) == chunk_count
    assert repo.statuses[-1][0] == "completed"
    assert doc.status == "completed"


@pytest.mark.asyncio
async def test_ingest_upload_rejects_empty_file(tmp_path):
    service = DocumentService(_FakeSession())
    service.repo = _FakeRepo()

    original_upload_dir = settings.UPLOAD_DIR
    settings.UPLOAD_DIR = str(tmp_path)
    try:
        upload = UploadFile(filename="empty.txt", file=BytesIO(b""))
        with pytest.raises(ValueError, match="Uploaded file is empty"):
            await service.ingest_upload(user_id=uuid4(), upload=upload)
    finally:
        settings.UPLOAD_DIR = original_upload_dir


@pytest.mark.asyncio
async def test_ingest_upload_rejects_oversize_file(tmp_path):
    service = DocumentService(_FakeSession())
    service.repo = _FakeRepo()

    original_upload_dir = settings.UPLOAD_DIR
    original_max_upload = settings.MAX_UPLOAD_SIZE_MB
    settings.UPLOAD_DIR = str(tmp_path)
    settings.MAX_UPLOAD_SIZE_MB = 0
    try:
        upload = UploadFile(filename="big.txt", file=BytesIO(b"hello"))
        with pytest.raises(ValueError, match="File exceeds"):
            await service.ingest_upload(user_id=uuid4(), upload=upload)
    finally:
        settings.UPLOAD_DIR = original_upload_dir
        settings.MAX_UPLOAD_SIZE_MB = original_max_upload


@pytest.mark.asyncio
async def test_ingest_upload_bubbles_extraction_failure(tmp_path, monkeypatch):
    service = DocumentService(_FakeSession())
    service.repo = _FakeRepo()

    original_upload_dir = settings.UPLOAD_DIR
    settings.UPLOAD_DIR = str(tmp_path)
    try:
        monkeypatch.setattr(service, "_extract_text", lambda data, ext: (_ for _ in ()).throw(RuntimeError("parse failed")))
        upload = UploadFile(filename="bad.txt", file=BytesIO(b"oops"))
        with pytest.raises(RuntimeError, match="parse failed"):
            await service.ingest_upload(user_id=uuid4(), upload=upload)
    finally:
        settings.UPLOAD_DIR = original_upload_dir
