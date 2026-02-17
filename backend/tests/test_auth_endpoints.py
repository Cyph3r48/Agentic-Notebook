from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import db_session
from app.api.v1.endpoints import auth as auth_module
from app.main import app


async def _fake_db_session():
    yield object()


def _build_client() -> TestClient:
    app.dependency_overrides[db_session] = _fake_db_session
    return TestClient(app)


def test_login_success(monkeypatch):
    user = SimpleNamespace(
        id=uuid4(),
        email="user@example.com",
        username="user",
        password_hash="hashed",
        role="user",
        is_active=True,
    )
    tracker = {"create_called": False, "last_login_called": False}

    class FakeUserRepository:
        def __init__(self, _session):
            pass

        async def get_by_email(self, _email):
            return user

        async def set_last_login(self, _user, _value):
            tracker["last_login_called"] = True

    class FakeSessionRepository:
        def __init__(self, _session):
            pass

        async def create_session(self, **kwargs):
            tracker["create_called"] = True

    monkeypatch.setattr(auth_module, "UserRepository", FakeUserRepository)
    monkeypatch.setattr(auth_module, "SessionRepository", FakeSessionRepository)
    monkeypatch.setattr(auth_module, "verify_password", lambda plain, hashed: True)
    monkeypatch.setattr(auth_module, "create_access_token", lambda **kwargs: "access-token")
    monkeypatch.setattr(
        auth_module,
        "create_refresh_token",
        lambda **kwargs: ("refresh-token", datetime.now(tz=timezone.utc) + timedelta(days=1)),
    )

    with _build_client() as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "user@example.com", "password": "password123"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["access_token"] == "access-token"
    assert payload["refresh_token"] == "refresh-token"
    assert tracker["create_called"] is True
    assert tracker["last_login_called"] is True


def test_refresh_success(monkeypatch):
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        email="user@example.com",
        role="user",
        is_active=True,
    )
    token_row = SimpleNamespace(
        session_token="old-refresh",
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
    )
    tracker = {"rotated": False}

    class FakeUserRepository:
        def __init__(self, _session):
            pass

        async def get_by_id(self, _user_id):
            return user

    class FakeSessionRepository:
        def __init__(self, _session):
            pass

        async def get_by_token_and_user(self, *, token, user_id):
            return token_row

        async def rotate_session_token(self, row, *, token, expires_at):
            tracker["rotated"] = True
            row.session_token = token
            row.expires_at = expires_at

    monkeypatch.setattr(auth_module, "UserRepository", FakeUserRepository)
    monkeypatch.setattr(auth_module, "SessionRepository", FakeSessionRepository)
    monkeypatch.setattr(auth_module, "decode_access_token", lambda _t: {"type": "refresh", "sub": str(user_id)})
    monkeypatch.setattr(auth_module, "create_access_token", lambda **kwargs: "new-access")
    monkeypatch.setattr(
        auth_module,
        "create_refresh_token",
        lambda **kwargs: ("new-refresh", datetime.now(tz=timezone.utc) + timedelta(days=1)),
    )

    with _build_client() as client:
        response = client.post("/api/v1/auth/refresh", json={"refresh_token": "old-refresh"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["access_token"] == "new-access"
    assert payload["refresh_token"] == "new-refresh"
    assert tracker["rotated"] is True


def test_logout_success(monkeypatch):
    tracker = {"deleted_token": None}

    class FakeSessionRepository:
        def __init__(self, _session):
            pass

        async def delete_by_token(self, token):
            tracker["deleted_token"] = token

    monkeypatch.setattr(auth_module, "SessionRepository", FakeSessionRepository)

    with _build_client() as client:
        response = client.post("/api/v1/auth/logout", json={"refresh_token": "bye-token"})

    assert response.status_code == 204
    assert tracker["deleted_token"] == "bye-token"


def test_login_invalid_credentials_payload_shape(monkeypatch):
    class FakeUserRepository:
        def __init__(self, _session):
            pass

        async def get_by_email(self, _email):
            return None

    class FakeSessionRepository:
        def __init__(self, _session):
            pass

    monkeypatch.setattr(auth_module, "UserRepository", FakeUserRepository)
    monkeypatch.setattr(auth_module, "SessionRepository", FakeSessionRepository)
    monkeypatch.setattr(auth_module, "verify_password", lambda plain, hashed: False)

    with _build_client() as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "user@example.com", "password": "password123"},
        )

    assert response.status_code == 401
    payload = response.json()
    assert payload["error"] == "Unauthorized"
    assert payload["message"] == "Invalid credentials"
    assert "request_id" in payload
