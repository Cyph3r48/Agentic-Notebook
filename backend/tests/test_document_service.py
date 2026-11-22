from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi import UploadFile

from app.core.config import settings
from app.services import document_service as document_service_module
from app.services.document_service import DocumentService
from app.services.memory import IngestOutcome


class _FakeRepo:
    def __init__(self):
        self.created = None
        self.chunks = []
        self.statuses = []
        self._docs = {}
        self._docs_by_hash = {}
        self.create_error = None
        self.deleted_ids = []

    async def create_document(self, **kwargs):
        if self.create_error is not None:
            raise self.create_error
        self.created = kwargs
        doc = SimpleNamespace(
            id=uuid4(),
            user_id=kwargs["user_id"],
            filename=kwargs["filename"],
            original_filename=kwargs["original_filename"],
            file_type=kwargs["file_type"],
            file_size=kwargs["file_size"],
            content_hash=kwargs["content_hash"],
            storage_path=kwargs["storage_path"],
            status=kwargs["status"],
            metadata_json=kwargs["metadata_json"],
            created_at=datetime.now(tz=timezone.utc),
        )
        self._docs[doc.id] = doc
        self._docs_by_hash[(doc.user_id, doc.content_hash)] = doc
        return doc

    async def get_by_id(self, document_id):
        return self._docs.get(document_id)

    async def get_by_user_and_content_hash(self, *, user_id, content_hash):
        return self._docs_by_hash.get((user_id, content_hash))

    async def get_for_user(self, *, document_id, user_id):
        doc = self._docs.get(document_id)
        if doc is None or doc.user_id != user_id:
            return None
        return doc

    async def add_chunks(self, *, document_id, chunks):
        self.chunks = chunks

    async def update_status(self, row, *, status, processing_error=None):
        row.status = status
        row.processing_error = processing_error
        self.statuses.append((status, processing_error))

    async def update_document(
        self,
        row,
        *,
        content_hash=None,
        metadata_json=None,
        status=None,
        processing_error=None,
    ):
        if content_hash is not None:
            row.content_hash = content_hash
        if metadata_json is not None:
            row.metadata_json = metadata_json
        if status is not None:
            row.status = status
        row.processing_error = processing_error
        self.statuses.append((row.status, processing_error))

    async def clear_chunks(self, document_id):
        self.chunks = []

    async def delete_document(self, row):
        self.deleted_ids.append(row.id)
        self._docs.pop(row.id, None)
        self._docs_by_hash.pop((row.user_id, row.content_hash), None)


class _FakeSession:
    async def refresh(self, _doc):
        return None


class _RecordingMemory:
    """Stands in for the memory backend so these tests never reach Qdrant or the embedding service."""

    def __init__(self):
        self.outcome = IngestOutcome(vector_indexed="disabled")
        self.ingested: list[dict] = []
        self.deleted: list[tuple] = []

    async def ingest(self, **kwargs):
        self.ingested.append(kwargs)
        return self.outcome

    async def delete(self, *, user_id, document_id):
        self.deleted.append((user_id, document_id))


@pytest.fixture(autouse=True)
def memory(monkeypatch):
    recording = _RecordingMemory()
    monkeypatch.setattr(document_service_module, "get_memory_provider", lambda session: recording)
    return recording


def _minimal_broken_docx_bytes() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr("word/document.xml", "<broken>")
    return buffer.getvalue()


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
async def test_ingest_upload_invalid_pdf_returns_parser_specific_error(tmp_path):
    service = DocumentService(_FakeSession())
    service.repo = _FakeRepo()

    original_upload_dir = settings.UPLOAD_DIR
    settings.UPLOAD_DIR = str(tmp_path)
    try:
        upload = UploadFile(filename="bad.pdf", file=BytesIO(b"%PDF-1.7\nthis-is-not-a-real-pdf"))
        with pytest.raises(ValueError, match="Unable to extract text from PDF file"):
            await service.ingest_upload(user_id=uuid4(), upload=upload)
    finally:
        settings.UPLOAD_DIR = original_upload_dir


@pytest.mark.asyncio
async def test_ingest_upload_invalid_docx_returns_parser_specific_error(tmp_path):
    service = DocumentService(_FakeSession())
    service.repo = _FakeRepo()

    original_upload_dir = settings.UPLOAD_DIR
    settings.UPLOAD_DIR = str(tmp_path)
    try:
        upload = UploadFile(filename="bad.docx", file=BytesIO(_minimal_broken_docx_bytes()))
        with pytest.raises(ValueError, match="Unable to extract text from DOCX file"):
            await service.ingest_upload(user_id=uuid4(), upload=upload)
    finally:
        settings.UPLOAD_DIR = original_upload_dir


@pytest.mark.asyncio
async def test_stage_upload_rejects_pdf_extension_spoofing(tmp_path):
    service = DocumentService(_FakeSession())
    service.repo = _FakeRepo()

    original_upload_dir = settings.UPLOAD_DIR
    settings.UPLOAD_DIR = str(tmp_path)
    try:
        upload = UploadFile(filename="spoof.pdf", file=BytesIO(b"this is plain text"))
        with pytest.raises(ValueError, match="File content does not match declared type: .pdf"):
            await service.stage_upload(user_id=uuid4(), upload=upload)
    finally:
        settings.UPLOAD_DIR = original_upload_dir


@pytest.mark.asyncio
async def test_stage_upload_rejects_docx_extension_spoofing(tmp_path):
    service = DocumentService(_FakeSession())
    service.repo = _FakeRepo()

    original_upload_dir = settings.UPLOAD_DIR
    settings.UPLOAD_DIR = str(tmp_path)
    try:
        upload = UploadFile(filename="spoof.docx", file=BytesIO(b"this is plain text"))
        with pytest.raises(ValueError, match="File content does not match declared type: .docx"):
            await service.stage_upload(user_id=uuid4(), upload=upload)
    finally:
        settings.UPLOAD_DIR = original_upload_dir


@pytest.mark.asyncio
async def test_process_document_persists_parser_specific_failure_for_pdf(tmp_path):
    service = DocumentService(_FakeSession())
    repo = _FakeRepo()
    service.repo = repo

    original_upload_dir = settings.UPLOAD_DIR
    settings.UPLOAD_DIR = str(tmp_path)
    user_id = uuid4()
    try:
        upload = UploadFile(filename="broken.pdf", file=BytesIO(b"%PDF-1.7\nbroken-content"))
        doc, is_new = await service.stage_upload(user_id=user_id, upload=upload)
        assert is_new is True

        with pytest.raises(ValueError, match="Unable to extract text from PDF file"):
            await service.process_document(doc.id)

        stored = await repo.get_by_id(doc.id)
        assert stored is not None
        assert stored.status == "failed"
        assert stored.processing_error is not None
        assert "Unable to extract text from PDF file" in stored.processing_error
    finally:
        settings.UPLOAD_DIR = original_upload_dir


@pytest.mark.asyncio
async def test_stage_upload_deduplicates_by_content_hash(tmp_path):
    service = DocumentService(_FakeSession())
    repo = _FakeRepo()
    service.repo = repo

    original_upload_dir = settings.UPLOAD_DIR
    settings.UPLOAD_DIR = str(tmp_path)
    user_id = uuid4()
    try:
        upload1 = UploadFile(filename="one.txt", file=BytesIO(b"same-content"))
        first_doc, first_new = await service.stage_upload(user_id=user_id, upload=upload1)
        assert first_new is True

        upload2 = UploadFile(filename="two.txt", file=BytesIO(b"same-content"))
        second_doc, second_new = await service.stage_upload(user_id=user_id, upload=upload2)
        assert second_new is False
        assert second_doc.id == first_doc.id
    finally:
        settings.UPLOAD_DIR = original_upload_dir


@pytest.mark.asyncio
async def test_stage_upload_cleans_up_staged_file_when_db_create_fails(tmp_path):
    service = DocumentService(_FakeSession())
    repo = _FakeRepo()
    repo.create_error = RuntimeError("db write failed")
    service.repo = repo

    original_upload_dir = settings.UPLOAD_DIR
    settings.UPLOAD_DIR = str(tmp_path)
    try:
        upload = UploadFile(filename="notes.txt", file=BytesIO(b"hello"))
        with pytest.raises(RuntimeError, match="db write failed"):
            await service.stage_upload(user_id=uuid4(), upload=upload)
    finally:
        settings.UPLOAD_DIR = original_upload_dir

    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_delete_document_for_user_removes_db_row_and_file(tmp_path):
    service = DocumentService(_FakeSession())
    repo = _FakeRepo()
    service.repo = repo

    original_upload_dir = settings.UPLOAD_DIR
    settings.UPLOAD_DIR = str(tmp_path)
    user_id = uuid4()
    try:
        upload = UploadFile(filename="delete-me.txt", file=BytesIO(b"hello"))
        doc, is_new = await service.stage_upload(user_id=user_id, upload=upload)
        assert is_new is True
        file_path = tmp_path / doc.filename
        assert file_path.exists()

        deleted = await service.delete_document_for_user(document_id=doc.id, user_id=user_id)
        assert deleted is True
        assert doc.id in repo.deleted_ids
        assert not file_path.exists()
    finally:
        settings.UPLOAD_DIR = original_upload_dir


@pytest.mark.asyncio
async def test_delete_document_for_user_returns_false_when_missing(tmp_path):
    service = DocumentService(_FakeSession())
    service.repo = _FakeRepo()

    original_upload_dir = settings.UPLOAD_DIR
    settings.UPLOAD_DIR = str(tmp_path)
    try:
        deleted = await service.delete_document_for_user(document_id=uuid4(), user_id=uuid4())
        assert deleted is False
    finally:
        settings.UPLOAD_DIR = original_upload_dir


@pytest.mark.asyncio
async def test_process_document_missing_document_returns_zero():
    service = DocumentService(_FakeSession())
    service.repo = _FakeRepo()

    count = await service.process_document(uuid4())
    assert count == 0


async def _process_text(tmp_path, memory, text=b"alpha beta gamma"):
    service = DocumentService(_FakeSession())
    repo = _FakeRepo()
    service.repo = repo
    original_upload_dir = settings.UPLOAD_DIR
    settings.UPLOAD_DIR = str(tmp_path)
    try:
        doc, _ = await service.stage_upload(
            user_id=uuid4(), upload=UploadFile(filename="n.txt", file=BytesIO(text))
        )
        await service.process_document(doc.id)
    finally:
        settings.UPLOAD_DIR = original_upload_dir
    return doc, repo


@pytest.mark.asyncio
async def test_process_document_stores_vector_ids_and_marks_the_document_indexed(tmp_path, memory):
    memory.outcome = IngestOutcome(id_map={0: "point-0"}, vector_indexed=True)

    doc, repo = await _process_text(tmp_path, memory)

    assert doc.status == "completed"
    assert repo.chunks[0]["vector_id"] == "point-0"
    assert doc.metadata_json["vector_indexed"] is True
    assert "vector_index_error" not in doc.metadata_json
    assert memory.deleted and memory.ingested[0]["original_filename"] == "n.txt"


@pytest.mark.asyncio
async def test_a_failed_vector_index_does_not_fail_the_upload_but_is_recorded(tmp_path, memory):
    memory.outcome = IngestOutcome(vector_indexed=False, error="Qdrant: could not connect")

    doc, repo = await _process_text(tmp_path, memory)

    assert doc.status == "completed"
    assert repo.chunks and repo.chunks[0]["vector_id"] is None
    assert doc.metadata_json["vector_indexed"] is False
    assert doc.metadata_json["vector_index_error"] == "Qdrant: could not connect"


@pytest.mark.asyncio
async def test_document_with_vectors_off_is_marked_disabled(tmp_path, memory):
    doc, _ = await _process_text(tmp_path, memory)

    assert doc.metadata_json["vector_indexed"] == "disabled"


@pytest.mark.asyncio
async def test_deleting_a_document_also_deletes_its_vectors(tmp_path, memory):
    service = DocumentService(_FakeSession())
    service.repo = _FakeRepo()
    original_upload_dir = settings.UPLOAD_DIR
    settings.UPLOAD_DIR = str(tmp_path)
    user_id = uuid4()
    try:
        doc, _ = await service.stage_upload(user_id=user_id, upload=UploadFile(filename="x.txt", file=BytesIO(b"hi")))
        await service.delete_document_for_user(document_id=doc.id, user_id=user_id)
    finally:
        settings.UPLOAD_DIR = original_upload_dir

    assert memory.deleted == [(user_id, doc.id)]
