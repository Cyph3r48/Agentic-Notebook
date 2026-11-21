from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import db_session, get_current_user, get_memory_provider
from app.api.v1.endpoints.search import router


async def _fake_db_session():
    yield object()


def _fake_user():
    return SimpleNamespace(id=uuid4(), role="user")


def _build_test_client(memory) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[db_session] = _fake_db_session
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_memory_provider] = lambda: memory
    return TestClient(app)


def test_search_documents_endpoint(fake_memory):
    fake_memory.results = [
        fake_memory.chunk(original_filename="alpha.txt", content="machine learning basics", score=0.85)
    ]
    fake_memory.mode = "vector"

    with _build_test_client(fake_memory) as client:
        response = client.post(
            "/search",
            json={"query": "machine learning", "limit": 5, "offset": 2, "min_score": 0.25},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "machine learning"
    assert len(payload["results"]) == 1
    assert payload["results"][0]["original_filename"] == "alpha.txt"
    assert payload["mode"] == "vector"
    assert payload["degraded_reason"] is None
    call = fake_memory.search_calls[0]
    assert call["offset"] == 2
    assert call["min_score"] == 0.25


def test_search_reports_when_vector_search_fell_back(fake_memory):
    fake_memory.mode = "keyword_fallback"
    fake_memory.degraded_reason = "Qdrant: could not connect"

    with _build_test_client(fake_memory) as client:
        response = client.post("/search", json={"query": "anything"})

    assert response.status_code == 200
    assert response.json()["mode"] == "keyword_fallback"
    assert response.json()["degraded_reason"] == "Qdrant: could not connect"


def test_search_documents_rejects_blank_query(fake_memory):
    with _build_test_client(fake_memory) as client:
        response = client.post("/search", json={"query": "", "limit": 5})

    assert response.status_code == 422
