from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_model_settings_service
from app.api.v1.endpoints.model_settings import router
from app.schemas.model_settings import DefaultModel
from app.services.llm.base import ProviderCredentials
from app.services.llm_service import LLMService
from app.services.model_settings_service import ModelSettingsService

LISTING = {
    "anthropic": [{"id": "claude-sonnet-5-5", "name": "Claude Sonnet", "provider": "anthropic"}],
    "openai": [
        {"id": "gpt-5.5", "name": "gpt-5.5", "provider": "openai"},
        {"id": "gpt-5.4", "name": "gpt-5.4", "provider": "openai"},
        {"id": "o3", "name": "o3", "provider": "openai"},
    ],
    "ollama_cloud": [{"id": "gpt-oss:120b", "name": "gpt-oss:120b", "provider": "ollama_cloud"}],
    "ollama": [
        {"id": "llama3.2:3b", "name": "llama3.2:3b", "provider": "ollama"},
        {"id": "gpt-oss:20b", "name": "gpt-oss:20b", "provider": "ollama"},
    ],
}


class _Repo:
    """In-memory ModelPreferenceRepository."""

    def __init__(self):
        self.rows: dict = {}

    async def get(self, *, user_id):
        return self.rows.get(user_id)

    async def save(self, *, user_id, default_provider, default_model, enabled_models):
        row = SimpleNamespace(
            user_id=user_id,
            default_provider=default_provider,
            default_model=default_model,
            enabled_models=enabled_models,
        )
        self.rows[user_id] = row
        return row


class _Credentials:
    """Which providers this user has credentials for."""

    def __init__(self, *configured):
        self.configured = set(configured)

    async def resolve(self, user_id, provider):
        if provider in self.configured:
            return ProviderCredentials(api_key="k", source="user", owner=str(user_id))
        return None


@pytest.fixture
def listing(monkeypatch):
    current = {"value": {pid: list(models) for pid, models in LISTING.items()}}

    async def fake_list_models(cls, credentials_by_provider=None):
        return {pid: list(models) for pid, models in current["value"].items()}

    monkeypatch.setattr(LLMService, "list_models", classmethod(fake_list_models))
    return current


def _service(repo=None, *configured):
    return ModelSettingsService(repo or _Repo(), _Credentials(*(configured or ("anthropic", "openai", "ollama_cloud"))))


def _by_id(response):
    return {p.id: p for p in response.providers}


# ---------------------------------------------------------------- the catalog


@pytest.mark.asyncio
async def test_every_provider_appears_with_a_label_and_its_models_all_enabled_by_default(listing):
    user = uuid4()

    response = await _service().get(user)

    providers = _by_id(response)
    assert list(providers) == ["anthropic", "openai", "ollama_cloud", "ollama"]
    assert [providers[p].label for p in providers] == ["Claude", "OpenAI", "Ollama Cloud", "Ollama (local)"]
    assert all(m.enabled and m.available for p in providers.values() for m in p.models)
    assert [m.id for m in providers["openai"].models] == ["gpt-5.5", "gpt-5.4", "o3"]
    assert response.default is None


@pytest.mark.asyncio
async def test_openai_is_listed_without_a_key_marked_not_configured(listing):
    listing["value"]["openai"] = []  # what the adapter returns with no key

    response = await _service(None, "anthropic").get(uuid4())

    openai = _by_id(response)["openai"]
    assert openai.configured is False and openai.models == []
    assert _by_id(response)["ollama"].configured is True  # a local Ollama needs no key


# ---------------------------------------------------------------- saving


@pytest.mark.asyncio
async def test_saving_enabled_models_and_a_default_round_trips(listing):
    repo, user = _Repo(), uuid4()
    service = _service(repo)

    response = await service.update(
        user, {"openai": ["gpt-5.4"], "ollama": []}, DefaultModel(provider="openai", model="gpt-5.4")
    )

    providers = _by_id(response)
    assert [(m.id, m.enabled) for m in providers["openai"].models] == [("gpt-5.5", False), ("gpt-5.4", True), ("o3", False)]
    assert not any(m.enabled for m in providers["ollama"].models)  # an explicit empty list switches all off
    assert all(m.enabled for m in providers["anthropic"].models)  # providers not mentioned stay fully on
    assert response.default == DefaultModel(provider="openai", model="gpt-5.4")
    assert await service.default_for(user) == ("openai", "gpt-5.4")


@pytest.mark.asyncio
async def test_saving_replaces_the_whole_state_so_null_clears_choices(listing):
    repo, user = _Repo(), uuid4()
    service = _service(repo)
    await service.update(user, {"openai": ["gpt-5.4"]}, DefaultModel(provider="openai", model="gpt-5.4"))

    response = await service.update(user, None, None)

    assert response.default is None and await service.default_for(user) is None
    assert all(m.enabled for m in _by_id(response)["openai"].models)


@pytest.mark.asyncio
async def test_duplicate_ids_are_stored_once(listing):
    repo, user = _Repo(), uuid4()
    await _service(repo).update(user, {"openai": ["o3", "o3", "gpt-5.4"]}, None)

    assert repo.rows[user].enabled_models == {"openai": ["o3", "gpt-5.4"]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("enabled", "default", "message"),
    [
        ({"openai": ["gpt-9-nope"]}, None, "not available to you"),
        ({"mistral": ["x"]}, None, "Unknown provider: mistral"),
        (None, DefaultModel(provider="mistral", model="x"), "Unknown provider: mistral"),
        (None, DefaultModel(provider="openai", model="gpt-9-nope"), "default model is not available"),
        ({"openai": ["gpt-5.4"]}, DefaultModel(provider="openai", model="o3"), "default model must be one of the enabled"),
    ],
)
async def test_invalid_choices_are_rejected_with_a_clear_message_and_nothing_is_saved(listing, enabled, default, message):
    repo, user = _Repo(), uuid4()

    with pytest.raises(ValueError, match=message):
        await _service(repo).update(user, enabled, default)

    assert repo.rows == {}


@pytest.mark.asyncio
async def test_a_model_from_another_provider_cannot_be_enabled_under_the_wrong_one(listing):
    with pytest.raises(ValueError, match="not available to you"):
        await _service().update(uuid4(), {"openai": ["claude-sonnet-5-5"]}, None)


# ---------------------------------------------------------------- failed or changed listings never wipe choices


@pytest.mark.asyncio
async def test_saved_choices_survive_a_failed_listing_and_are_marked_unavailable(listing):
    repo, user = _Repo(), uuid4()
    service = _service(repo)
    await service.update(user, {"openai": ["gpt-5.4", "o3"]}, DefaultModel(provider="openai", model="gpt-5.4"))

    listing["value"]["openai"] = []  # the key stopped working or the API is down
    response = await service.get(user)

    openai = _by_id(response)["openai"]
    assert [(m.id, m.enabled, m.available) for m in openai.models] == [("gpt-5.4", True, False), ("o3", True, False)]
    assert response.default == DefaultModel(provider="openai", model="gpt-5.4")


@pytest.mark.asyncio
async def test_saving_again_during_an_outage_keeps_the_unchanged_choices_but_not_new_unknown_ones(listing):
    repo, user = _Repo(), uuid4()
    service = _service(repo)
    await service.update(user, {"openai": ["gpt-5.4"]}, DefaultModel(provider="openai", model="gpt-5.4"))
    listing["value"]["openai"] = []

    kept = await service.update(user, {"openai": ["gpt-5.4"]}, DefaultModel(provider="openai", model="gpt-5.4"))
    assert [m.id for m in _by_id(kept)["openai"].models] == ["gpt-5.4"]

    with pytest.raises(ValueError, match="not available to you"):
        await service.update(user, {"openai": ["gpt-5.4", "o3"]}, None)


@pytest.mark.asyncio
async def test_models_that_appear_later_are_on_unless_the_user_chose_a_list_for_that_provider(listing):
    repo, user = _Repo(), uuid4()
    service = _service(repo)
    await service.update(user, {"openai": ["gpt-5.4"]}, None)
    listing["value"]["anthropic"].append({"id": "claude-opus-5-5", "name": "Opus", "provider": "anthropic"})
    listing["value"]["openai"].append({"id": "gpt-6", "name": "gpt-6", "provider": "openai"})

    providers = _by_id(await service.get(user))

    assert all(m.enabled for m in providers["anthropic"].models)  # no list saved for Claude: new models are on
    assert [m.id for m in providers["openai"].models if m.enabled] == ["gpt-5.4"]  # a saved list is respected


# ---------------------------------------------------------------- the chat list and isolation


@pytest.mark.asyncio
async def test_the_chat_list_only_shows_enabled_models(listing):
    repo, user = _Repo(), uuid4()
    service = _service(repo)
    await service.update(user, {"openai": ["o3"], "ollama": []}, None)

    filtered = await service.only_enabled(user, LISTING)

    assert [m["id"] for m in filtered["openai"]] == ["o3"]
    assert filtered["ollama"] == []
    assert [m["id"] for m in filtered["anthropic"]] == ["claude-sonnet-5-5"]


@pytest.mark.asyncio
async def test_users_do_not_see_each_others_choices(listing):
    repo = _Repo()
    service = _service(repo)
    alice, bob = uuid4(), uuid4()
    await service.update(alice, {"openai": ["o3"]}, DefaultModel(provider="openai", model="o3"))

    assert await service.default_for(bob) is None
    assert all(m.enabled for m in _by_id(await service.get(bob))["openai"].models)
    assert [m["id"] for m in (await service.only_enabled(bob, LISTING))["openai"]] == ["gpt-5.5", "gpt-5.4", "o3"]


# ---------------------------------------------------------------- HTTP


def _client(service, user=None):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user or SimpleNamespace(id=uuid4(), role="user")
    app.dependency_overrides[get_model_settings_service] = lambda: service
    return TestClient(app)


def test_get_and_put_over_http(listing):
    user = SimpleNamespace(id=uuid4(), role="user")
    with _client(_service(), user) as client:
        before = client.get("/settings/models")
        saved = client.put(
            "/settings/models",
            json={"enabled_models": {"openai": ["o3"]}, "default": {"provider": "openai", "model": "o3"}},
        )
        bad = client.put("/settings/models", json={"enabled_models": {"openai": ["gpt-9-nope"]}})

    assert before.status_code == 200 and before.headers["cache-control"] == "no-store"
    assert saved.status_code == 200 and saved.json()["default"] == {"provider": "openai", "model": "o3"}
    assert bad.status_code == 400 and "not available to you" in bad.json()["detail"]


def test_the_endpoints_require_login(listing):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_model_settings_service] = lambda: _service()

    with TestClient(app) as client:
        assert client.get("/settings/models").status_code == 401
        assert client.put("/settings/models", json={}).status_code == 401


def test_oversized_input_is_rejected_by_the_schema(listing):
    with _client(_service()) as client:
        response = client.put("/settings/models", json={"default": {"provider": "x" * 30, "model": "m"}})

    assert response.status_code == 422
