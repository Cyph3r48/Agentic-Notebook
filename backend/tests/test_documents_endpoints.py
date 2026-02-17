from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import db_session, get_current_user
from app.api.v1.endpoints import documents as documents_module
from app.api.v1.endpoints.documents import router


async def _fake_db_session():
    yield object()


def _fake_user():
    return SimpleNamespace(id=uuid4(), role="user")


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[db_session] = _fake_db_session
    app.dependency_overrides[get_current_user] = _fake_user
    return TestClient(app)


def test_upload_document_endpoint(monkeypatch):
    fake_doc = SimpleNamespace(
        id=uuid4(),
        filename="stored.txt",
        file_type="txt",
        file_size=11,
        status="pending",
        created_at=datetime.now(tz=timezone.utc),
    )

    async def fake_stage_upload(self, *, user_id, upload):
        return fake_doc, True

    async def fake_count_chunks(self, document_id):
        return 0

    async def fake_background(document_id):
        return None

    monkeypatch.setattr(documents_module.DocumentService, "stage_upload", fake_stage_upload)
    monkeypatch.setattr(documents_module.DocumentRepository, "count_chunks", fake_count_chunks)
    monkeypatch.setattr(documents_module, "process_document_in_background", fake_background)

    with _build_test_client() as client:
        response = client.post(
            "/documents/upload",
            files={"file": ("notes.txt", b"hello world", "text/plain")},
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["filename"] == "stored.txt"
    assert payload["chunk_count"] == 0
    assert payload["status"] == "pending"
    assert payload["processing_error"] is None


def test_upload_document_rejects_spoofed_pdf(monkeypatch):
    async def fake_stage_upload(self, *, user_id, upload):
        raise ValueError("File content does not match declared type: .pdf")

    monkeypatch.setattr(documents_module.DocumentService, "stage_upload", fake_stage_upload)

    with _build_test_client() as client:
        response = client.post(
            "/documents/upload",
            files={"file": ("spoof.pdf", b"plain text body", "application/pdf")},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "File content does not match declared type: .pdf"


def test_list_documents_endpoint(monkeypatch):
    docs = [
        SimpleNamespace(
            id=uuid4(),
            filename="a.txt",
            original_filename="alpha.txt",
            file_type="txt",
            file_size=10,
            status="completed",
            created_at=datetime.now(tz=timezone.utc),
        ),
        SimpleNamespace(
            id=uuid4(),
            filename="b.txt",
            original_filename="beta.txt",
            file_type="txt",
            file_size=12,
            status="processing",
            created_at=datetime.now(tz=timezone.utc),
        ),
    ]

    async def fake_list_for_user(self, user_id):
        return docs

    async def fake_chunk_counts_for_user(self, user_id):
        return {docs[0].id: 3}

    monkeypatch.setattr(documents_module.DocumentRepository, "list_for_user", fake_list_for_user)
    monkeypatch.setattr(documents_module.DocumentRepository, "chunk_counts_for_user", fake_chunk_counts_for_user)

    with _build_test_client() as client:
        response = client.get("/documents")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["original_filename"] == "alpha.txt"
    assert payload[0]["chunk_count"] == 3
    assert payload[1]["status"] == "processing"
    assert payload[1]["chunk_count"] == 0


def test_retry_document_endpoint(monkeypatch):
    fake_doc = SimpleNamespace(
        id=uuid4(),
        filename="stored.txt",
        file_type="txt",
        file_size=11,
        status="failed",
        created_at=datetime.now(tz=timezone.utc),
        processing_error="parse failed",
    )

    async def fake_get_for_user(self, *, document_id, user_id):
        return fake_doc

    async def fake_update_status(self, row, *, status, processing_error=None):
        row.status = status
        row.processing_error = processing_error

    async def fake_count_chunks(self, document_id):
        return 0

    async def fake_background(document_id):
        return None

    monkeypatch.setattr(documents_module.DocumentRepository, "get_for_user", fake_get_for_user)
    monkeypatch.setattr(documents_module.DocumentRepository, "update_status", fake_update_status)
    monkeypatch.setattr(documents_module.DocumentRepository, "count_chunks", fake_count_chunks)
    monkeypatch.setattr(documents_module, "process_document_in_background", fake_background)

    with _build_test_client() as client:
        response = client.post(f"/documents/{fake_doc.id}/retry")

    assert response.status_code == 202
    payload = response.json()
    assert payload["id"] == str(fake_doc.id)
    assert payload["status"] == "pending"
    assert payload["chunk_count"] == 0
    assert payload["processing_error"] is None
    assert fake_doc.processing_error is None


def test_retry_document_rejects_non_failed_status(monkeypatch):
    fake_doc = SimpleNamespace(
        id=uuid4(),
        filename="stored.txt",
        file_type="txt",
        file_size=11,
        status="completed",
        created_at=datetime.now(tz=timezone.utc),
        processing_error=None,
    )

    async def fake_get_for_user(self, *, document_id, user_id):
        return fake_doc

    monkeypatch.setattr(documents_module.DocumentRepository, "get_for_user", fake_get_for_user)

    with _build_test_client() as client:
        response = client.post(f"/documents/{fake_doc.id}/retry")

    assert response.status_code == 400
    assert response.json()["detail"] == "Only failed documents can be retried"


def test_retry_document_returns_not_found(monkeypatch):
    async def fake_get_for_user(self, *, document_id, user_id):
        return None

    monkeypatch.setattr(documents_module.DocumentRepository, "get_for_user", fake_get_for_user)

    with _build_test_client() as client:
        response = client.post(f"/documents/{uuid4()}/retry")

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found"


def test_delete_document_endpoint(monkeypatch):
    async def fake_delete_document_for_user(self, *, document_id, user_id):
        return True

    monkeypatch.setattr(documents_module.DocumentService, "delete_document_for_user", fake_delete_document_for_user)

    with _build_test_client() as client:
        response = client.delete(f"/documents/{uuid4()}")

    assert response.status_code == 204
    assert response.content == b""


def test_delete_document_returns_not_found(monkeypatch):
    async def fake_delete_document_for_user(self, *, document_id, user_id):
        return False

    monkeypatch.setattr(documents_module.DocumentService, "delete_document_for_user", fake_delete_document_for_user)

    with _build_test_client() as client:
        response = client.delete(f"/documents/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found"


def test_get_document_endpoint(monkeypatch):
    fake_doc = SimpleNamespace(
        id=uuid4(),
        filename="stored.txt",
        original_filename="notes.txt",
        file_type="txt",
        file_size=11,
        status="completed",
        created_at=datetime.now(tz=timezone.utc),
        processing_error=None,
    )

    async def fake_get_for_user(self, *, document_id, user_id):
        return fake_doc

    async def fake_count_chunks(self, document_id):
        return 2

    monkeypatch.setattr(documents_module.DocumentRepository, "get_for_user", fake_get_for_user)
    monkeypatch.setattr(documents_module.DocumentRepository, "count_chunks", fake_count_chunks)

    with _build_test_client() as client:
        response = client.get(f"/documents/{fake_doc.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(fake_doc.id)
    assert payload["original_filename"] == "notes.txt"
    assert payload["chunk_count"] == 2


def test_get_document_returns_not_found(monkeypatch):
    async def fake_get_for_user(self, *, document_id, user_id):
        return None

    monkeypatch.setattr(documents_module.DocumentRepository, "get_for_user", fake_get_for_user)

    with _build_test_client() as client:
        response = client.get(f"/documents/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found"
