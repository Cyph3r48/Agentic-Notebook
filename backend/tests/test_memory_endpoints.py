from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import db_session, get_current_user, get_memory_provider
from app.api.v1.endpoints.memory import router
from app.core.config import settings
from app.services.memory import ComponentHealth, MemoryHealth


async def _fake_db_session():
    yield object()


class _HealthMemory:
    def __init__(self, report):
        self.report = report

    async def health(self):
        return self.report


def _client(memory, *, authenticated=True) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[db_session] = _fake_db_session
    if authenticated:
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4(), role="user")
    app.dependency_overrides[get_memory_provider] = lambda: memory
    return TestClient(app)


def test_memory_health_returns_status_components_and_last_error():
    when = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
    report = MemoryHealth(
        status="degraded",
        backend="builtin",
        vector_enabled=True,
        detail="Part of vector search is unavailable. Search uses keywords only.",
        components={
            "qdrant": ComponentHealth(False, "Qdrant: could not connect"),
            "embeddings": ComponentHealth(True, "Reachable and returns vectors of the expected size."),
        },
        last_error="Qdrant: could not connect",
        last_error_at=when,
    )

    with _client(_HealthMemory(report)) as client:
        response = client.get("/memory/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded" and body["backend"] == "builtin"
    assert body["components"]["qdrant"] == {"ok": False, "detail": "Qdrant: could not connect"}
    assert body["components"]["embeddings"]["ok"] is True
    assert body["last_error"] == "Qdrant: could not connect"


def test_memory_health_requires_login():
    with _client(_HealthMemory(None), authenticated=False) as client:
        response = client.get("/memory/health")

    assert response.status_code == 401


def test_an_unimplemented_backend_returns_503_with_the_reason(monkeypatch):
    monkeypatch.setattr(settings, "MEMORY_BACKEND", "smc")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[db_session] = _fake_db_session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4(), role="user")

    with TestClient(app) as client:
        response = client.get("/memory/health")

    assert response.status_code == 503
    assert "MEMORY_BACKEND=smc is not implemented" in response.json()["detail"]
