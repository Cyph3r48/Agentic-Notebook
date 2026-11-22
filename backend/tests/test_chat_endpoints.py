from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import (
    db_session,
    get_credential_service,
    get_current_user,
    get_memory_provider,
    get_model_settings_service,
)
from app.api.v1.endpoints import chat as chat_module
from app.api.v1.endpoints.chat import router
from app.services.llm.anthropic_provider import AnthropicProvider
from app.services.llm.ollama_provider import OllamaProvider
from app.services.llm.openai_provider import OpenAIProvider
from app.services.llm_service import ProviderCredentials
from conftest import FakeMemory, NoPreferences


class _NoCredentials:
    """Stands in for CredentialService: nothing saved, so the server settings apply."""

    async def resolve(self, user_id, provider):
        return None


async def _fake_db_session():
    yield object()


def _fake_user():
    return SimpleNamespace(id=uuid4(), role="user")


@pytest.fixture(autouse=True)
def _empty_history(monkeypatch):
    """Endpoints load chat history from the database; these tests run without one."""

    async def fake_list_recent_messages(self, *, conversation_id, limit):
        return []

    monkeypatch.setattr(chat_module.ChatRepository, "list_recent_messages", fake_list_recent_messages)


def _build_test_client(memory=None, credentials=None, model_settings=None) -> TestClient:
    memory = memory if memory is not None else FakeMemory()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[db_session] = _fake_db_session
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_credential_service] = lambda: credentials or _NoCredentials()
    app.dependency_overrides[get_memory_provider] = lambda: memory
    app.dependency_overrides[get_model_settings_service] = lambda: model_settings or NoPreferences()
    return TestClient(app)


def test_create_conversation_endpoint(monkeypatch):
    fake_row = SimpleNamespace(
        id=uuid4(),
        title="New Chat",
        model="llama3.2:3b-instruct-q4_K_M",
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
    )

    async def fake_create_conversation(self, *, user_id, title, model, provider=None):
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
    tracker = {"limit": None, "offset": None, "model": None, "sort": None}

    async def fake_list_conversations_for_user_paginated(self, *, user_id, limit, offset, model=None, sort="desc"):
        tracker["limit"] = limit
        tracker["offset"] = offset
        tracker["model"] = model
        tracker["sort"] = sort
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
    assert tracker["model"] is None
    assert tracker["sort"] == "desc"


def test_list_conversations_endpoint_with_model_and_sort(monkeypatch):
    rows = [
        SimpleNamespace(
            id=uuid4(),
            title="Filtered",
            model="claude-sonnet-4-6",
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
    ]
    tracker = {"limit": None, "offset": None, "model": None, "sort": None}

    async def fake_list_conversations_for_user_paginated(self, *, user_id, limit, offset, model=None, sort="desc"):
        tracker["limit"] = limit
        tracker["offset"] = offset
        tracker["model"] = model
        tracker["sort"] = sort
        return rows

    monkeypatch.setattr(
        chat_module.ChatRepository,
        "list_conversations_for_user_paginated",
        fake_list_conversations_for_user_paginated,
    )

    with _build_test_client() as client:
        response = client.get("/chat/conversations?limit=5&offset=1&model=claude-sonnet-4-6&sort=asc")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert tracker["limit"] == 5
    assert tracker["offset"] == 1
    assert tracker["model"] == "claude-sonnet-4-6"
    assert tracker["sort"] == "asc"


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

    memory = FakeMemory(mode="keyword_fallback", degraded_reason="Qdrant: could not connect")
    memory.results = [memory.chunk()]

    async def fake_llm_reply(self, *, model, user_message, context_lines, **kwargs):
        return "assistant-response", {"provider": "ollama", "model": model}

    monkeypatch.setattr(chat_module.ChatRepository, "get_conversation_for_user", fake_get_conversation_for_user)
    monkeypatch.setattr(chat_module.ChatRepository, "create_message", fake_create_message)
    monkeypatch.setattr(chat_module.LLMService, "generate_chat_reply", classmethod(fake_llm_reply))

    with _build_test_client(memory) as client:
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
    # A degraded search is recorded on the reply so the UI can say so.
    assert payload["assistant_message"]["metadata"]["memory_mode"] == "keyword_fallback"
    assert payload["assistant_message"]["metadata"]["memory_degraded_reason"] == "Qdrant: could not connect"
    assert memory.search_calls[0]["query"] == "What is in my docs?"


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
            tokens_used=kwargs.get("tokens_used"),
            sources=kwargs.get("sources", []),
            metadata_json=kwargs.get("metadata", {}),
            created_at=datetime.now(tz=timezone.utc),
        )
        created_rows.append(row)
        return row

    async def fake_stream_chat_reply(cls, *, model, user_message, context_lines, **kwargs):
        yield "stream "
        yield "reply"

    monkeypatch.setattr(chat_module.ChatRepository, "get_conversation_for_user", fake_get_conversation_for_user)
    monkeypatch.setattr(chat_module.ChatRepository, "create_message", fake_create_message)
    monkeypatch.setattr(chat_module.LLMService, "stream_chat_reply", classmethod(fake_stream_chat_reply))

    with _build_test_client() as client:
        response = client.post(
            f"/chat/conversations/{conversation.id}/messages/stream",
            json={"content": "hello", "use_rag": False},
        )

    assert response.status_code == 200
    assert "event: delta" in response.text
    assert "event: message" in response.text
    assert "event: done" in response.text
    assert len(created_rows) == 2
    assert created_rows[1].content == "stream reply"


def test_stream_message_endpoint_falls_back_on_provider_error(monkeypatch):
    conversation = SimpleNamespace(id=uuid4(), model="llama3.2:3b-instruct-q4_K_M")
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
            tokens_used=kwargs.get("tokens_used"),
            sources=kwargs.get("sources", []),
            metadata_json=kwargs.get("metadata", {}),
            created_at=datetime.now(tz=timezone.utc),
        )
        created_rows.append(row)
        return row

    async def fail_stream_chat_reply(cls, *, model, user_message, context_lines, **kwargs):
        raise RuntimeError("provider unavailable")
        yield ""

    monkeypatch.setattr(chat_module.ChatRepository, "get_conversation_for_user", fake_get_conversation_for_user)
    monkeypatch.setattr(chat_module.ChatRepository, "create_message", fake_create_message)
    monkeypatch.setattr(chat_module.LLMService, "stream_chat_reply", classmethod(fail_stream_chat_reply))

    with _build_test_client() as client:
        response = client.post(
            f"/chat/conversations/{conversation.id}/messages/stream",
            json={"content": "hello", "use_rag": False},
        )

    assert response.status_code == 200
    assert "event: message" in response.text
    assert "event: done" in response.text
    assert len(created_rows) == 2
    assert created_rows[1].metadata_json["error_type"] == "provider_stream_error"


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
    tracker = {"limit": None, "offset": None, "role": None, "has_sources": None, "sort": None}

    async def fake_get_conversation_for_user(self, *, conversation_id, user_id):
        return conversation

    async def fake_list_messages_for_conversation_paginated(
        self,
        *,
        conversation_id,
        limit,
        offset,
        role=None,
        has_sources=None,
        sort="asc",
    ):
        tracker["limit"] = limit
        tracker["offset"] = offset
        tracker["role"] = role
        tracker["has_sources"] = has_sources
        tracker["sort"] = sort
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
    assert tracker["role"] is None
    assert tracker["has_sources"] is None
    assert tracker["sort"] == "asc"


def test_list_messages_endpoint_with_filters(monkeypatch):
    conversation = SimpleNamespace(id=uuid4())
    rows = [
        SimpleNamespace(
            id=uuid4(),
            conversation_id=conversation.id,
            role="assistant",
            content="hello",
            model="llama3.2:3b-instruct-q4_K_M",
            tokens_used=11,
            sources=[{"snippet": "x"}],
            metadata_json={},
            created_at=datetime.now(tz=timezone.utc),
        )
    ]
    tracker = {"limit": None, "offset": None, "role": None, "has_sources": None, "sort": None}

    async def fake_get_conversation_for_user(self, *, conversation_id, user_id):
        return conversation

    async def fake_list_messages_for_conversation_paginated(
        self,
        *,
        conversation_id,
        limit,
        offset,
        role=None,
        has_sources=None,
        sort="asc",
    ):
        tracker["limit"] = limit
        tracker["offset"] = offset
        tracker["role"] = role
        tracker["has_sources"] = has_sources
        tracker["sort"] = sort
        return rows

    monkeypatch.setattr(chat_module.ChatRepository, "get_conversation_for_user", fake_get_conversation_for_user)
    monkeypatch.setattr(
        chat_module.ChatRepository,
        "list_messages_for_conversation_paginated",
        fake_list_messages_for_conversation_paginated,
    )

    with _build_test_client() as client:
        response = client.get(
            f"/chat/conversations/{conversation.id}/messages?limit=3&offset=4&role=assistant&has_sources=true&sort=desc"
        )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert tracker["limit"] == 3
    assert tracker["offset"] == 4
    assert tracker["role"] == "assistant"
    assert tracker["has_sources"] is True
    assert tracker["sort"] == "desc"


def test_models_endpoint(monkeypatch):
    async def fake_list_models(cls, *args, **kwargs):
        return {
            "ollama": [{"id": "llama3.2:3b-instruct-q4_K_M", "provider": "ollama"}],
            "anthropic": [{"id": "claude-sonnet-4-6", "provider": "anthropic"}],
        }

    monkeypatch.setattr(chat_module.LLMService, "list_models", classmethod(fake_list_models))

    with _build_test_client() as client:
        response = client.get("/chat/models")

    assert response.status_code == 200
    payload = response.json()
    assert "ollama" in payload
    assert "anthropic" in payload
    assert payload["anthropic"][0]["id"] == "claude-sonnet-4-6"


def test_provider_health_endpoint(monkeypatch):
    async def fake_provider_health(cls, *args, **kwargs):
        return {
            "ollama": {"healthy": True, "circuit_open": False},
            "anthropic": {"healthy": False, "circuit_open": True},
        }

    monkeypatch.setattr(chat_module.LLMService, "provider_health", classmethod(fake_provider_health))

    with _build_test_client() as client:
        response = client.get("/chat/providers/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ollama"]["healthy"] is True
    assert payload["anthropic"]["circuit_open"] is True


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


class _OpenAIKeyOnly:
    """A user who saved an OpenAI key and nothing else."""

    async def resolve(self, user_id, provider):
        if provider == "openai":
            return ProviderCredentials(api_key="sk-openai-test-1234", source="user", owner=str(user_id))
        return None


def test_creating_an_openai_conversation_without_a_key_is_a_clear_400():
    with _build_test_client() as client:
        response = client.post("/chat/conversations", json={"title": "t", "model": "gpt-5.5"})

    assert response.status_code == 400
    assert "Add one in Settings" in response.json()["detail"]


def test_creating_an_openai_conversation_checks_the_model_against_the_users_list(monkeypatch):
    created = {}

    async def fake_create_conversation(self, *, user_id, title, model, provider=None):
        created["model"] = model
        return SimpleNamespace(
            id=uuid4(), title=title, model=model,
            created_at=datetime.now(tz=timezone.utc), updated_at=datetime.now(tz=timezone.utc),
        )

    async def fake_catalog(cls, credentials=None):
        assert credentials.api_key == "sk-openai-test-1234"  # this user's key, not another provider's
        return [{"id": "gpt-5.4", "name": "gpt-5.4"}]

    monkeypatch.setattr(chat_module.ChatRepository, "create_conversation", fake_create_conversation)
    monkeypatch.setattr(OpenAIProvider, "model_catalog", classmethod(fake_catalog))

    with _build_test_client(credentials=_OpenAIKeyOnly()) as client:
        ok = client.post("/chat/conversations", json={"title": "t", "model": "gpt-5.4"})
        bad = client.post("/chat/conversations", json={"title": "t", "model": "gpt-9-nope"})

    assert ok.status_code == 201 and created["model"] == "gpt-5.4"
    assert bad.status_code == 400 and "Unsupported OpenAI model" in bad.json()["detail"]


def test_models_and_health_include_openai_for_the_user(monkeypatch):
    async def fake_catalog(cls, credentials=None):
        return [{"id": "gpt-5.5", "name": "gpt-5.5"}] if credentials else []

    async def no_models(cls, credentials=None):
        return []

    monkeypatch.setattr(OpenAIProvider, "model_catalog", classmethod(fake_catalog))
    monkeypatch.setattr(OllamaProvider, "list_models", classmethod(no_models))
    monkeypatch.setattr(AnthropicProvider, "model_catalog", classmethod(lambda cls, credentials=None: _async([])))

    with _build_test_client(credentials=_OpenAIKeyOnly()) as client:
        models = client.get("/chat/models").json()
        health = client.get("/chat/providers/health").json()

    assert models["openai"] == [{"id": "gpt-5.5", "name": "gpt-5.5", "provider": "openai"}]
    assert health["openai"]["healthy"] is True and health["openai"]["circuit_open"] is False
    assert health["anthropic"]["healthy"] is False


async def _async(value):
    return value


# ---------------------------------------------------------------- stored provider and saved defaults


class _SpyCredentials:
    """Records which provider credentials were asked for, and has a key for ollama_cloud and openai."""

    def __init__(self):
        self.asked: list[str] = []

    async def resolve(self, user_id, provider):
        self.asked.append(provider)
        if provider in ("ollama_cloud", "openai"):
            return ProviderCredentials(api_key=f"key-for-{provider}", source="user", owner=str(user_id))
        return None


class _Preferences(NoPreferences):
    def __init__(self, default=None, enabled=None):
        self._default = default
        self._enabled = enabled

    async def default_for(self, user_id):
        return self._default

    async def only_enabled(self, user_id, listing):
        if self._enabled is None:
            return listing
        return {pid: [m for m in models if m["id"] in self._enabled.get(pid, [m["id"] for m in models])] for pid, models in listing.items()}


def _capture_create(monkeypatch):
    created = {}

    async def fake_create_conversation(self, *, user_id, title, model, provider=None):
        created.update(model=model, provider=provider)
        return SimpleNamespace(
            id=uuid4(), title=title, model=model, provider=provider,
            created_at=datetime.now(tz=timezone.utc), updated_at=datetime.now(tz=timezone.utc),
        )

    monkeypatch.setattr(chat_module.ChatRepository, "create_conversation", fake_create_conversation)
    return created


def _ollama_cloud_catalog(monkeypatch, *names):
    from app.services.llm.ollama_cloud_provider import OllamaCloudProvider
    from app.services.llm.base import ModelInfo

    async def fake_list(cls, credentials):
        return [ModelInfo(id=n, name=n) for n in names] if credentials else []

    monkeypatch.setattr(OllamaCloudProvider, "list_models", classmethod(fake_list))


def test_an_explicit_provider_is_stored_and_returned_even_when_names_collide(monkeypatch):
    created = _capture_create(monkeypatch)
    _ollama_cloud_catalog(monkeypatch, "gpt-oss:120b")

    with _build_test_client(credentials=_SpyCredentials()) as client:
        cloud = client.post("/chat/conversations", json={"title": "t", "model": "gpt-oss:120b", "provider": "ollama_cloud"})
        local = client.post("/chat/conversations", json={"title": "t", "model": "gpt-oss:20b"})

    assert cloud.status_code == 201 and cloud.json()["provider"] == "ollama_cloud"
    assert local.status_code == 201 and local.json()["provider"] == "ollama"  # inferred, then stored
    assert created == {"model": "gpt-oss:20b", "provider": "ollama"}


def test_a_cloud_conversation_without_a_key_is_a_clear_400(monkeypatch):
    _capture_create(monkeypatch)

    with _build_test_client() as client:  # no credentials for anything
        response = client.post("/chat/conversations", json={"title": "t", "model": "gpt-oss:120b", "provider": "ollama_cloud"})

    assert response.status_code == 400 and "Add one in Settings" in response.json()["detail"]


def test_an_unknown_provider_is_a_400(monkeypatch):
    _capture_create(monkeypatch)

    with _build_test_client() as client:
        response = client.post("/chat/conversations", json={"title": "t", "model": "x", "provider": "mistral"})

    assert response.status_code == 400 and "Unknown provider: mistral" in response.json()["detail"]


def test_a_model_from_another_providers_list_is_rejected_for_the_chosen_provider(monkeypatch):
    _capture_create(monkeypatch)
    _ollama_cloud_catalog(monkeypatch, "gpt-oss:120b")

    with _build_test_client(credentials=_SpyCredentials()) as client:
        response = client.post("/chat/conversations", json={"title": "t", "model": "llama3.2:3b", "provider": "ollama_cloud"})

    assert response.status_code == 400 and "Unsupported Ollama Cloud model" in response.json()["detail"]


def test_with_no_choice_in_the_request_the_users_saved_default_is_used(monkeypatch):
    created = _capture_create(monkeypatch)
    _ollama_cloud_catalog(monkeypatch, "gpt-oss:120b")

    with _build_test_client(credentials=_SpyCredentials(), model_settings=_Preferences(("ollama_cloud", "gpt-oss:120b"))) as client:
        response = client.post("/chat/conversations", json={"title": "t"})

    assert response.status_code == 201
    assert created == {"model": "gpt-oss:120b", "provider": "ollama_cloud"}


def test_a_saved_default_that_no_longer_works_falls_back_to_the_server_default(monkeypatch):
    created = _capture_create(monkeypatch)
    _ollama_cloud_catalog(monkeypatch, "kimi-k2")  # the saved model is gone from the list

    with _build_test_client(credentials=_SpyCredentials(), model_settings=_Preferences(("ollama_cloud", "gpt-oss:120b"))) as client:
        response = client.post("/chat/conversations", json={"title": "t"})

    assert response.status_code == 201
    assert created["model"] == chat_module.settings.DEFAULT_MODEL and created["provider"] == "ollama"


def test_a_request_that_names_a_model_ignores_the_saved_default(monkeypatch):
    created = _capture_create(monkeypatch)

    with _build_test_client(model_settings=_Preferences(("ollama_cloud", "gpt-oss:120b"))) as client:
        response = client.post("/chat/conversations", json={"title": "t", "model": "llama3.2:3b"})

    assert response.status_code == 201 and created == {"model": "llama3.2:3b", "provider": "ollama"}


def _send_with_conversation(monkeypatch, conversation, credentials):
    seen = {}

    async def fake_get(self, *, conversation_id, user_id):
        return conversation

    async def fake_create_message(self, **kwargs):
        return SimpleNamespace(
            id=uuid4(), conversation_id=kwargs["conversation_id"], role=kwargs["role"], content=kwargs["content"],
            model=kwargs.get("model"), tokens_used=1, sources=[], metadata_json=kwargs.get("metadata", {}),
            created_at=datetime.now(tz=timezone.utc),
        )

    async def fake_reply(cls, **kwargs):
        seen.update(kwargs)
        return "ok", {"provider": kwargs["provider"] or "inferred", "model": kwargs["model"]}

    monkeypatch.setattr(chat_module.ChatRepository, "get_conversation_for_user", fake_get)
    monkeypatch.setattr(chat_module.ChatRepository, "create_message", fake_create_message)
    monkeypatch.setattr(chat_module.LLMService, "generate_chat_reply", classmethod(fake_reply))

    with _build_test_client(credentials=credentials) as client:
        response = client.post(f"/chat/conversations/{conversation.id}/messages", json={"content": "hi", "use_rag": False})
    return response, seen


def test_a_conversation_runs_on_the_provider_stored_with_it(monkeypatch):
    spy = _SpyCredentials()
    conversation = SimpleNamespace(id=uuid4(), model="gpt-oss:120b", provider="ollama_cloud", system_prompt=None)

    response, seen = _send_with_conversation(monkeypatch, conversation, spy)

    assert response.status_code == 200
    assert spy.asked == ["ollama_cloud"]  # the cloud key, not the local Ollama's
    assert seen["provider"] == "ollama_cloud" and seen["credentials"].api_key == "key-for-ollama_cloud"


def test_a_conversation_from_before_providers_were_stored_is_inferred_from_its_model(monkeypatch):
    spy = _SpyCredentials()
    conversation = SimpleNamespace(id=uuid4(), model="gpt-5.5", system_prompt=None)  # no provider attribute

    response, seen = _send_with_conversation(monkeypatch, conversation, spy)

    assert response.status_code == 200 and spy.asked == ["openai"] and seen["provider"] == "openai"


def test_reading_a_conversation_reports_its_provider_inferred_for_old_rows(monkeypatch):
    async def fake_get(self, *, conversation_id, user_id):
        return SimpleNamespace(
            id=uuid4(), title="t", model="claude-sonnet-5-5", provider=None,
            created_at=datetime.now(tz=timezone.utc), updated_at=datetime.now(tz=timezone.utc),
        )

    monkeypatch.setattr(chat_module.ChatRepository, "get_conversation_for_user", fake_get)

    with _build_test_client() as client:
        response = client.get(f"/chat/conversations/{uuid4()}")

    assert response.status_code == 200 and response.json()["provider"] == "anthropic"


def test_the_model_list_hides_models_the_user_switched_off_unless_all_is_asked_for(monkeypatch):
    listing = {
        "openai": [{"id": "gpt-5.5", "provider": "openai"}, {"id": "o3", "provider": "openai"}],
        "ollama": [{"id": "llama3.2:3b", "provider": "ollama"}],
    }

    async def fake_list_models(cls, *args, **kwargs):
        return listing

    monkeypatch.setattr(chat_module.LLMService, "list_models", classmethod(fake_list_models))
    prefs = _Preferences(enabled={"openai": ["o3"]})

    with _build_test_client(model_settings=prefs) as client:
        mine = client.get("/chat/models").json()
        everything = client.get("/chat/models?all=true").json()

    assert [m["id"] for m in mine["openai"]] == ["o3"] and len(mine["ollama"]) == 1
    assert [m["id"] for m in everything["openai"]] == ["gpt-5.5", "o3"]
