from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.main import app


pytestmark = []
if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
    import pytest

    pytestmark.append(pytest.mark.skip(reason="Set RUN_DB_INTEGRATION_TESTS=1 to run DB integration tests"))


def _client() -> TestClient:
    return TestClient(app)


def test_auth_session_lifecycle_with_real_db() -> None:
    with _client() as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@structuredintelligence.com", "password": "change_me_immediately"},
        )
        assert login.status_code == 200
        login_payload = login.json()
        access_token = login_payload["access_token"]
        refresh_token = login_payload["refresh_token"]

        me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me.status_code == 200
        assert me.json()["email"] == "admin@structuredintelligence.com"

        refresh = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert refresh.status_code == 200
        refresh_payload = refresh.json()
        new_refresh = refresh_payload["refresh_token"]

        logout = client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": new_refresh},
        )
        assert logout.status_code == 204

        after_logout_refresh = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": new_refresh},
        )
        assert after_logout_refresh.status_code == 401
