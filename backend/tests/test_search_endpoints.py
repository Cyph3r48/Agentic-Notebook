from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import db_session, get_current_user
from app.api.v1.endpoints import search as search_module
from app.api.v1.endpoints.search import router


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


def test_search_documents_endpoint(monkeypatch):
    async def fake_search_chunks(self, *, user_id, query, limit):
        return [
            {
                "document_id": str(uuid4()),
                "original_filename": "alpha.txt",
                "chunk_index": 0,
                "content": "machine learning basics",
                "score": 0.85,
            }
        ]

    monkeypatch.setattr(search_module.SearchRepository, "search_chunks", fake_search_chunks)

    with _build_test_client() as client:
        response = client.post("/search", json={"query": "machine learning", "limit": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "machine learning"
    assert len(payload["results"]) == 1
    assert payload["results"][0]["original_filename"] == "alpha.txt"


def test_search_documents_rejects_blank_query():
    with _build_test_client() as client:
        response = client.post("/search", json={"query": "", "limit": 5})

    assert response.status_code == 422
