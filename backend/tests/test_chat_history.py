from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import db_session, get_current_user
from app.api.v1.endpoints import chat as chat_module
from app.api.v1.endpoints.chat import router
from app.core.config import settings


async def _fake_db_session():
    yield object()


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[db_session] = _fake_db_session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4(), role="user")
    return TestClient(app)


def _row(role, content, **metadata):
    return SimpleNamespace(role=role, content=content, metadata_json=metadata)


class _Recorder:
    """Records the order of repository calls and what reached the LLM service."""

    def __init__(self):
        self.order: list[str] = []
        self.llm_kwargs: dict = {}
        self.created: list[SimpleNamespace] = []


@pytest.fixture
def recorder(monkeypatch):
    rec = _Recorder()
    conversation = SimpleNamespace(
        id=uuid4(),
        model="llama3.2:3b-instruct-q4_K_M",
        system_prompt="Answer in one sentence.",
    )
    rec.conversation = conversation

    async def fake_get_conversation_for_user(self, *, conversation_id, user_id):
        return conversation

    async def fake_list_recent_messages(self, *, conversation_id, limit):
        rec.order.append("history")
        rec.history_limit = limit
        return [
            _row("user", "first question"),
            _row("assistant", "first answer"),
            _row("assistant", "canned excerpt", error_type="provider_error"),
        ]

    async def fake_create_message(self, **kwargs):
        rec.order.append(f"create:{kwargs['role']}")
        row = SimpleNamespace(
            id=uuid4(),
            conversation_id=kwargs["conversation_id"],
            role=kwargs["role"],
            content=kwargs["content"],
            model=kwargs.get("model"),
            tokens_used=kwargs.get("tokens_used"),
            sources=kwargs.get("sources", []),
            metadata_json=kwargs.get("metadata", {}),
            created_at=datetime.now(tz=timezone.utc),
        )
        rec.created.append(row)
        return row

    monkeypatch.setattr(chat_module.ChatRepository, "get_conversation_for_user", fake_get_conversation_for_user)
    monkeypatch.setattr(chat_module.ChatRepository, "list_recent_messages", fake_list_recent_messages)
    monkeypatch.setattr(chat_module.ChatRepository, "create_message", fake_create_message)
    return rec


EXPECTED_HISTORY = [
    {"role": "user", "content": "first question"},
    {"role": "assistant", "content": "first answer"},
]


def test_send_message_passes_history_and_system_prompt(monkeypatch, recorder):
    async def fake_llm_reply(cls, **kwargs):
        recorder.llm_kwargs = kwargs
        return "second answer", {"provider": "ollama", "model": kwargs["model"]}

    monkeypatch.setattr(chat_module.LLMService, "generate_chat_reply", classmethod(fake_llm_reply))

    with _client() as client:
        response = client.post(
            f"/chat/conversations/{recorder.conversation.id}/messages",
            json={"content": "second question", "use_rag": False},
        )

    assert response.status_code == 200
    assert recorder.llm_kwargs["history"] == EXPECTED_HISTORY
    assert recorder.llm_kwargs["system_prompt"] == "Answer in one sentence."
    assert recorder.llm_kwargs["user_message"] == "second question"
    # History is read before the new message is saved, so the new message is never sent twice.
    assert recorder.order[:2] == ["history", "create:user"]
    assert all("second question" not in turn["content"] for turn in recorder.llm_kwargs["history"])
    assert recorder.history_limit == settings.LLM_HISTORY_MESSAGES + 4


def test_stream_message_passes_history_and_stores_measured_usage(monkeypatch, recorder):
    async def fake_stream(cls, **kwargs):
        recorder.llm_kwargs = kwargs
        kwargs["outcome"].input_tokens = 11
        kwargs["outcome"].output_tokens = 7
        yield "second "
        yield "answer"

    monkeypatch.setattr(chat_module.LLMService, "stream_chat_reply", classmethod(fake_stream))

    with _client() as client:
        response = client.post(
            f"/chat/conversations/{recorder.conversation.id}/messages/stream",
            json={"content": "second question", "use_rag": False},
        )

    assert response.status_code == 200
    assert "event: done" in response.text
    assert recorder.llm_kwargs["history"] == EXPECTED_HISTORY
    assert recorder.llm_kwargs["system_prompt"] == "Answer in one sentence."
    assert recorder.order[:2] == ["history", "create:user"]
    stored = recorder.created[-1]
    assert stored.content == "second answer"
    assert stored.metadata_json["input_tokens"] == 11
    assert stored.metadata_json["output_tokens"] == 7
    assert stored.metadata_json["total_tokens"] == 18
    assert stored.tokens_used == 18
    assert "error_type" not in stored.metadata_json


def test_stream_refusal_is_stored_with_its_category(monkeypatch, recorder):
    async def fake_stream(cls, **kwargs):
        kwargs["outcome"].error_type = "provider_refusal"
        kwargs["outcome"].refusal_category = "cyber"
        yield "The model declined to answer this request."

    monkeypatch.setattr(chat_module.LLMService, "stream_chat_reply", classmethod(fake_stream))

    with _client() as client:
        client.post(
            f"/chat/conversations/{recorder.conversation.id}/messages/stream",
            json={"content": "x", "use_rag": False},
        )

    stored = recorder.created[-1]
    assert stored.metadata_json["error_type"] == "provider_refusal"
    assert stored.metadata_json["refusal_category"] == "cyber"


def test_stream_failure_keeps_the_specific_error_type(monkeypatch, recorder):
    async def failing_stream(cls, **kwargs):
        kwargs["outcome"].error_type = "provider_auth_error"
        raise RuntimeError("invalid x-api-key")
        yield ""

    monkeypatch.setattr(chat_module.LLMService, "stream_chat_reply", classmethod(failing_stream))

    with _client() as client:
        client.post(
            f"/chat/conversations/{recorder.conversation.id}/messages/stream",
            json={"content": "x", "use_rag": False},
        )

    assert recorder.created[-1].metadata_json["error_type"] == "provider_auth_error"


def test_create_conversation_normalizes_and_checks_claude_models(monkeypatch):
    created = {}

    async def fake_create_conversation(self, *, user_id, title, model):
        created["model"] = model
        return SimpleNamespace(
            id=uuid4(),
            title=title,
            model=model,
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )

    monkeypatch.setattr(chat_module.ChatRepository, "create_conversation", fake_create_conversation)

    with _client() as client:
        ok = client.post("/chat/conversations", json={"title": "t", "model": "claude-sonnet-5.5"})
        bad = client.post("/chat/conversations", json={"title": "t", "model": "claude-sonnet-9-9"})

    assert ok.status_code == 201
    assert created["model"] == "claude-sonnet-5-5"  # dotted spelling is stored in API form
    assert ok.json()["model"] == "claude-sonnet-5-5"
    assert bad.status_code == 400
    assert "Unsupported Anthropic model" in bad.json()["detail"]
