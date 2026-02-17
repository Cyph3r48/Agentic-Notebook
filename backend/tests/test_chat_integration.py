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


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@structuredintelligence.com", "password": "change_me_immediately"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_chat_conversation_and_messages_with_real_db() -> None:
    with _client() as client:
        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        created = client.post(
            "/api/v1/chat/conversations",
            headers=headers,
            json={"title": "Integration Chat"},
        )
        assert created.status_code == 201
        conversation_id = created.json()["id"]

        sent = client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            headers=headers,
            json={"content": "Hello there", "use_rag": False},
        )
        assert sent.status_code == 200
        turn = sent.json()
        assert turn["conversation_id"] == conversation_id
        assert turn["user_message"]["role"] == "user"
        assert turn["assistant_message"]["role"] == "assistant"

        listed = client.get("/api/v1/chat/conversations", headers=headers)
        assert listed.status_code == 200
        assert any(row["id"] == conversation_id for row in listed.json())

        messages = client.get(f"/api/v1/chat/conversations/{conversation_id}/messages", headers=headers)
        assert messages.status_code == 200
        rows = messages.json()
        assert len(rows) >= 2


def test_chat_delete_conversation_with_real_db() -> None:
    with _client() as client:
        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        created = client.post(
            "/api/v1/chat/conversations",
            headers=headers,
            json={"title": "Delete Me"},
        )
        assert created.status_code == 201
        conversation_id = created.json()["id"]

        deleted = client.delete(f"/api/v1/chat/conversations/{conversation_id}", headers=headers)
        assert deleted.status_code == 204

        detail = client.get(f"/api/v1/chat/conversations/{conversation_id}", headers=headers)
        assert detail.status_code == 404
