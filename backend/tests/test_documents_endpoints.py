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
        status="completed",
        created_at=datetime.now(tz=timezone.utc),
    )

    async def fake_ingest_upload(self, *, user_id, upload):
        return fake_doc, 2

    monkeypatch.setattr(documents_module.DocumentService, "ingest_upload", fake_ingest_upload)

    with _build_test_client() as client:
        response = client.post(
            "/documents/upload",
            files={"file": ("notes.txt", b"hello world", "text/plain")},
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["filename"] == "stored.txt"
    assert payload["chunk_count"] == 2
    assert payload["status"] == "completed"


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

    monkeypatch.setattr(documents_module.DocumentRepository, "list_for_user", fake_list_for_user)

    with _build_test_client() as client:
        response = client.get("/documents")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["original_filename"] == "alpha.txt"
    assert payload[1]["status"] == "processing"

