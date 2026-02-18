from __future__ import annotations

import os

import time

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


def test_chat_requires_auth_with_real_db() -> None:
    with _client() as client:
        response = client.get("/api/v1/chat/conversations")
        assert response.status_code == 401


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


def test_chat_rag_message_returns_sources_with_snippets() -> None:
    marker = "chat-rag-marker-12345"
    with _client() as client:
        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        upload = client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={"file": ("chat-rag.txt", f"This text contains {marker} for retrieval.".encode("utf-8"), "text/plain")},
        )
        assert upload.status_code == 201
        document_id = upload.json()["id"]

        for _ in range(24):
            detail = client.get(f"/api/v1/documents/{document_id}", headers=headers)
            assert detail.status_code == 200
            if detail.json()["status"] == "completed":
                break
            time.sleep(0.25)

        created = client.post("/api/v1/chat/conversations", headers=headers, json={"title": "RAG Chat"})
        assert created.status_code == 201
        conversation_id = created.json()["id"]

        sent = client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            headers=headers,
            json={"content": marker, "use_rag": True},
        )
        assert sent.status_code == 200
        assistant = sent.json()["assistant_message"]
        assert assistant["sources"]
        assert "snippet" in assistant["sources"][0]


def test_chat_update_conversation_title_with_real_db() -> None:
    with _client() as client:
        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        created = client.post(
            "/api/v1/chat/conversations",
            headers=headers,
            json={"title": "Original"},
        )
        assert created.status_code == 201
        conversation_id = created.json()["id"]

        updated = client.patch(
            f"/api/v1/chat/conversations/{conversation_id}",
            headers=headers,
            json={"title": "Renamed"},
        )
        assert updated.status_code == 200
        assert updated.json()["title"] == "Renamed"


def test_chat_list_messages_supports_pagination_with_real_db() -> None:
    with _client() as client:
        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        created = client.post(
            "/api/v1/chat/conversations",
            headers=headers,
            json={"title": "Paging"},
        )
        assert created.status_code == 201
        conversation_id = created.json()["id"]

        first = client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            headers=headers,
            json={"content": "first", "use_rag": False},
        )
        assert first.status_code == 200
        second = client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            headers=headers,
            json={"content": "second", "use_rag": False},
        )
        assert second.status_code == 200

        paged = client.get(
            f"/api/v1/chat/conversations/{conversation_id}/messages?limit=2&offset=2",
            headers=headers,
        )
        assert paged.status_code == 200
        rows = paged.json()
        assert len(rows) == 2
        assert rows[0]["role"] == "user"
        assert rows[0]["content"] == "second"


def test_chat_list_conversations_supports_pagination_with_real_db() -> None:
    with _client() as client:
        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        first = client.post("/api/v1/chat/conversations", headers=headers, json={"title": "Conv A"})
        assert first.status_code == 201
        second = client.post("/api/v1/chat/conversations", headers=headers, json={"title": "Conv B"})
        assert second.status_code == 201

        paged = client.get("/api/v1/chat/conversations?limit=1&offset=1", headers=headers)
        assert paged.status_code == 200
        rows = paged.json()
        assert len(rows) == 1
