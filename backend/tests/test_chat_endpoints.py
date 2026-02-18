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


def test_create_conversation_rejects_unknown_claude_model():
    with _build_test_client() as client:
        response = client.post(
            "/chat/conversations",
            json={"title": "Bad Claude", "model": "claude-unknown-1.0"},
        )

    assert response.status_code == 400
    assert "Unsupported Anthropic model" in response.json()["detail"]


def test_list_conversations_endpoint_with_pagination(monkeypatch):
    rows = [
        SimpleNamespace(
            id=uuid4(),
            title="Paged",
            model="llama3.2:3b-instruct-q4_K_M",
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
    ]
    tracker = {"limit": None, "offset": None}

    async def fake_list_conversations_for_user_paginated(self, *, user_id, limit, offset):
        tracker["limit"] = limit
        tracker["offset"] = offset
        return rows

    monkeypatch.setattr(
        chat_module.ChatRepository,
        "list_conversations_for_user_paginated",
        fake_list_conversations_for_user_paginated,
    )

    with _build_test_client() as client:
        response = client.get("/chat/conversations?limit=1&offset=2")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["title"] == "Paged"
    assert tracker["limit"] == 1
    assert tracker["offset"] == 2


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
            metadata_json=kwargs.get("metadata", {}),
            created_at=datetime.now(tz=timezone.utc),
        )
        created_rows.append(row)
        return row

    async def fake_vector_search(self, *, user_id, query, limit, offset=0, min_score=0.1):
        return [
            {
                "document_id": str(uuid4()),
                "original_filename": "doc.txt",
                "chunk_index": 0,
                "content": "chunk",
                "score": 0.8,
            }
        ]

    async def fake_llm_reply(self, *, model, user_message, context_lines):
        return "assistant-response", {"provider": "ollama", "model": model}

    monkeypatch.setattr(chat_module.ChatRepository, "get_conversation_for_user", fake_get_conversation_for_user)
    monkeypatch.setattr(chat_module.ChatRepository, "create_message", fake_create_message)
    monkeypatch.setattr(chat_module.VectorSearchService, "search", fake_vector_search)
    monkeypatch.setattr(chat_module.LLMService, "generate_chat_reply", classmethod(fake_llm_reply))

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
    assert payload["assistant_message"]["content"] == "assistant-response"
    assert payload["assistant_message"]["metadata"]["provider"] == "ollama"


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


def test_stream_message_endpoint(monkeypatch):
    conversation = SimpleNamespace(id=uuid4(), model="llama3.2:3b-instruct-q4_K_M")

    async def fake_get_conversation_for_user(self, *, conversation_id, user_id):
        return conversation

    async def fake_process_chat_turn(**kwargs):
        message_id = str(uuid4())
        return chat_module.ChatTurnResponse(
            conversation_id=str(conversation.id),
            user_message=chat_module.MessageResponse(
                id=str(uuid4()),
                conversation_id=str(conversation.id),
                role="user",
                content="hello",
                model=conversation.model,
                sources=[],
                metadata={},
                created_at=datetime.now(tz=timezone.utc),
            ),
            assistant_message=chat_module.MessageResponse(
                id=message_id,
                conversation_id=str(conversation.id),
                role="assistant",
                content="stream reply",
                model=conversation.model,
                sources=[],
                metadata={},
                created_at=datetime.now(tz=timezone.utc),
            ),
        )

    monkeypatch.setattr(chat_module.ChatRepository, "get_conversation_for_user", fake_get_conversation_for_user)
    monkeypatch.setattr(chat_module, "_process_chat_turn", fake_process_chat_turn)

    with _build_test_client() as client:
        response = client.post(
            f"/chat/conversations/{conversation.id}/messages/stream",
            json={"content": "hello", "use_rag": False},
        )

    assert response.status_code == 200
    assert "event: message" in response.text
    assert "event: done" in response.text


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


def test_list_messages_endpoint_with_pagination(monkeypatch):
    conversation = SimpleNamespace(id=uuid4())
    rows = [
        SimpleNamespace(
            id=uuid4(),
            conversation_id=conversation.id,
            role="user",
            content="hello",
            model="llama3.2:3b-instruct-q4_K_M",
            sources=[],
            metadata_json={},
            created_at=datetime.now(tz=timezone.utc),
        )
    ]
    tracker = {"limit": None, "offset": None}

    async def fake_get_conversation_for_user(self, *, conversation_id, user_id):
        return conversation

    async def fake_list_messages_for_conversation_paginated(self, *, conversation_id, limit, offset):
        tracker["limit"] = limit
        tracker["offset"] = offset
        return rows

    monkeypatch.setattr(chat_module.ChatRepository, "get_conversation_for_user", fake_get_conversation_for_user)
    monkeypatch.setattr(
        chat_module.ChatRepository,
        "list_messages_for_conversation_paginated",
        fake_list_messages_for_conversation_paginated,
    )

    with _build_test_client() as client:
        response = client.get(f"/chat/conversations/{conversation.id}/messages?limit=1&offset=2")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert tracker["limit"] == 1
    assert tracker["offset"] == 2


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
