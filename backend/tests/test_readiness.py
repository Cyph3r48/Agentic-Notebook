from __future__ import annotations

import json

import pytest

from app import main as main_module


@pytest.mark.asyncio
async def test_readiness_returns_200_when_dependencies_are_healthy(monkeypatch):
    async def db_ok() -> bool:
        return True

    async def redis_ok() -> bool:
        return True

    monkeypatch.setattr(main_module, "is_db_healthy", db_ok)
    monkeypatch.setattr(main_module, "is_redis_healthy", redis_ok)

    response = await main_module.readiness_check()
    payload = json.loads(response.body.decode("utf-8"))

    assert response.status_code == 200
    assert payload["status"] == "ready"
    assert payload["database"] == "connected"
    assert payload["redis"] == "connected"


@pytest.mark.asyncio
async def test_readiness_returns_503_when_database_is_down(monkeypatch):
    async def db_down() -> bool:
        return False

    async def redis_ok() -> bool:
        return True

    monkeypatch.setattr(main_module, "is_db_healthy", db_down)
    monkeypatch.setattr(main_module, "is_redis_healthy", redis_ok)

    response = await main_module.readiness_check()
    payload = json.loads(response.body.decode("utf-8"))

    assert response.status_code == 503
    assert payload["status"] == "degraded"
    assert payload["database"] == "unavailable"
    assert payload["redis"] == "connected"


@pytest.mark.asyncio
async def test_readiness_returns_503_when_redis_is_down(monkeypatch):
    async def db_ok() -> bool:
        return True

    async def redis_down() -> bool:
        return False

    monkeypatch.setattr(main_module, "is_db_healthy", db_ok)
    monkeypatch.setattr(main_module, "is_redis_healthy", redis_down)

    response = await main_module.readiness_check()
    payload = json.loads(response.body.decode("utf-8"))

    assert response.status_code == 503
    assert payload["status"] == "degraded"
    assert payload["database"] == "connected"
    assert payload["redis"] == "unavailable"


@pytest.mark.asyncio
async def test_readiness_reports_vector_state_but_stays_ready_when_vectors_are_down(monkeypatch):
    async def ok() -> bool:
        return True

    async def vector_down() -> str:
        return "down"

    monkeypatch.setattr(main_module, "is_db_healthy", ok)
    monkeypatch.setattr(main_module, "is_redis_healthy", ok)
    monkeypatch.setattr(main_module, "_vector_status", vector_down)

    response = await main_module.readiness_check()
    payload = json.loads(response.body.decode("utf-8"))

    assert response.status_code == 200
    assert payload["status"] == "ready"
    assert payload["vector_db"] == "down"


@pytest.mark.asyncio
async def test_vector_status_is_unknown_when_the_check_itself_fails(monkeypatch):
    class _Boom:
        async def __aenter__(self):
            raise RuntimeError("db gone")

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(main_module, "SessionLocal", lambda: _Boom())

    assert await main_module._vector_status() == "unknown"
