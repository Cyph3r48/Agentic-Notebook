from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import db_session, get_current_user
from app.api.v1.endpoints import chat as chat_module
from app.api.v1.endpoints.chat import router


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


def test_create_conversation_endpoint(monkeypatch):
    fake_row = SimpleNamespace(
        id=uuid4(),
        title="New Chat",
        model="llama3.2:3b-instruct-q4_K_M",
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
    )

    async def fake_create_conversation(self, *, user_id, title, model):
        return fake_row

    monkeypatch.setattr(chat_module.ChatRepository, "create_conversation", fake_create_conversation)

    with _build_test_client() as client:
        response = client.post("/chat/conversations", json={"title": "New Chat"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["id"] == str(fake_row.id)
    assert payload["title"] == "New Chat"


def test_send_message_endpoint(monkeypatch):
    conversation = SimpleNamespace(
        id=uuid4(),
        model="llama3.2:3b-instruct-q4_K_M",
    )
    created_rows = []

    async def fake_get_conversation_for_user(self, *, conversation_id, user_id):
        return conversation

    async def fake_create_message(self, **kwargs):
        row = SimpleNamespace(
            id=uuid4(),
            conversation_id=kwargs["conversation_id"],
            role=kwargs["role"],
            content=kwargs["content"],
            model=kwargs.get("model"),
            sources=kwargs.get("sources", []),
            created_at=datetime.now(tz=timezone.utc),
        )
        created_rows.append(row)
        return row

    async def fake_search_chunks(self, *, user_id, query, limit):
        return [
            {
                "document_id": str(uuid4()),
                "original_filename": "doc.txt",
                "chunk_index": 0,
                "content": "chunk",
                "score": 0.8,
            }
        ]

    monkeypatch.setattr(chat_module.ChatRepository, "get_conversation_for_user", fake_get_conversation_for_user)
    monkeypatch.setattr(chat_module.ChatRepository, "create_message", fake_create_message)
    monkeypatch.setattr(chat_module.SearchRepository, "search_chunks", fake_search_chunks)

    with _build_test_client() as client:
        response = client.post(
            f"/chat/conversations/{conversation.id}/messages",
            json={"content": "What is in my docs?", "use_rag": True},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["conversation_id"] == str(conversation.id)
    assert payload["user_message"]["role"] == "user"
    assert payload["assistant_message"]["role"] == "assistant"
    assert len(payload["assistant_message"]["sources"]) == 1
    assert payload["assistant_message"]["sources"][0]["snippet"] == "chunk"
    assert "doc.txt" in payload["assistant_message"]["content"]


def test_send_message_missing_conversation(monkeypatch):
    async def fake_get_conversation_for_user(self, *, conversation_id, user_id):
        return None

    monkeypatch.setattr(chat_module.ChatRepository, "get_conversation_for_user", fake_get_conversation_for_user)

    with _build_test_client() as client:
        response = client.post(
            f"/chat/conversations/{uuid4()}/messages",
            json={"content": "hello", "use_rag": False},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"


def test_get_conversation_endpoint(monkeypatch):
    fake_row = SimpleNamespace(
        id=uuid4(),
        title="Existing Chat",
        model="llama3.2:3b-instruct-q4_K_M",
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
    )

    async def fake_get_conversation_for_user(self, *, conversation_id, user_id):
        return fake_row

    monkeypatch.setattr(chat_module.ChatRepository, "get_conversation_for_user", fake_get_conversation_for_user)

    with _build_test_client() as client:
        response = client.get(f"/chat/conversations/{fake_row.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(fake_row.id)
    assert payload["title"] == "Existing Chat"


def test_delete_conversation_endpoint(monkeypatch):
    fake_row = SimpleNamespace(id=uuid4())
    deleted = {"value": False}

    async def fake_get_conversation_for_user(self, *, conversation_id, user_id):
        return fake_row

    async def fake_delete_conversation(self, row):
        deleted["value"] = True

    monkeypatch.setattr(chat_module.ChatRepository, "get_conversation_for_user", fake_get_conversation_for_user)
    monkeypatch.setattr(chat_module.ChatRepository, "delete_conversation", fake_delete_conversation)

    with _build_test_client() as client:
        response = client.delete(f"/chat/conversations/{fake_row.id}")

    assert response.status_code == 204
    assert deleted["value"] is True


def test_update_conversation_endpoint(monkeypatch):
    fake_row = SimpleNamespace(
        id=uuid4(),
        title="Old",
        model="llama3.2:3b-instruct-q4_K_M",
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
    )

    async def fake_get_conversation_for_user(self, *, conversation_id, user_id):
        return fake_row

    async def fake_update_conversation_title(self, row, *, title):
        row.title = title

    monkeypatch.setattr(chat_module.ChatRepository, "get_conversation_for_user", fake_get_conversation_for_user)
    monkeypatch.setattr(chat_module.ChatRepository, "update_conversation_title", fake_update_conversation_title)

    with _build_test_client() as client:
        response = client.patch(f"/chat/conversations/{fake_row.id}", json={"title": "Renamed"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Renamed"
