from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from loguru import logger

from app import main as main_module
from app.api.deps import get_current_user, get_embedding_settings_service
from app.api.v1.endpoints.embedding_settings import router
from app.core.config import settings
from app.core.secret_box import SecretBox, SecretDecryptError
from app.schemas.embedding_settings import EmbeddingCandidate
from app.services.embedding_settings_service import (
    SECRET_CONTEXT,
    EmbeddingProbeFailed,
    EmbeddingSettingsService,
    invalidate_active_embedding,
)
from app.services.memory.embeddings import EmbeddingModelNotFound, ProbeResult, VectorPathError

KEY = "ollama-cloud-SENTINEL-1111"
OTHER_KEY = "ollama-cloud-SENTINEL-2222"


class _Repo:
    """In-memory SystemSettingsRepository."""

    def __init__(self):
        self.rows: dict = {}
        self.gets = 0

    async def get(self, key):
        self.gets += 1
        return self.rows.get(key)

    async def put(self, key, value, *, secret_encrypted=None, updated_by=None):
        row = SimpleNamespace(
            key=key, value=value, secret_encrypted=secret_encrypted, updated_by=updated_by,
            updated_at=datetime.now(tz=timezone.utc),
        )
        self.rows[key] = row
        return row


class _Stats:
    def __init__(self, total=10, in_index=4):
        self.total, self.in_index, self.asked = total, in_index, []

    async def counts(self, identity):
        self.asked.append(identity)
        return self.total, self.in_index


class _Factory:
    """Builds fake embedders. `outcome` is a vector size, or an exception to raise from probe()."""

    def __init__(self, outcome=768):
        self.outcome = outcome
        self.configs = []

    def __call__(self, config):
        self.configs.append(config)
        outcome = self.outcome

        class _Embedder:
            async def probe(self_inner):
                if isinstance(outcome, Exception):
                    raise outcome
                return ProbeResult(dim=outcome, latency_ms=7)

        return _Embedder()


@pytest.fixture(autouse=True)
def _settings(monkeypatch, master_key):
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "tei")
    monkeypatch.setattr(settings, "EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5")
    monkeypatch.setattr(settings, "EMBEDDING_URL", "http://tei.invalid:80")
    monkeypatch.setattr(settings, "EMBEDDING_DIM", 1024)
    monkeypatch.setattr(settings, "OLLAMA_URL", "http://local-ollama.invalid:11434")
    monkeypatch.setattr(settings, "OLLAMA_EMBED_MODEL", "embeddinggemma")
    monkeypatch.setattr(settings, "QDRANT_COLLECTION", "si_documents")
    invalidate_active_embedding()
    yield
    invalidate_active_embedding()


def _service(repo=None, factory=None, stats=None):
    return EmbeddingSettingsService(repo or _Repo(), stats, provider_factory=factory or _Factory())


def _candidate(**kwargs):
    kwargs.setdefault("provider", "ollama")
    return EmbeddingCandidate(**kwargs)


# ---------------------------------------------------------------- what is shown


@pytest.mark.asyncio
async def test_with_nothing_saved_the_environment_choice_is_shown_read_only_for_tei():
    stats = _Stats(total=10, in_index=0)

    response = await _service(stats=stats).get()

    assert (response.provider, response.model, response.source) == ("tei", "BAAI/bge-large-en-v1.5", "environment")
    assert response.model_editable is False and response.dim == 1024
    assert response.identity.startswith("tei__baai-bge-large-en-v1-5-") and response.identity.endswith("__1024")
    assert (response.documents_total, response.documents_in_index) == (10, 0)
    assert stats.asked == [response.identity]


@pytest.mark.asyncio
async def test_an_environment_chosen_ollama_model_has_no_size_until_it_is_probed(monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "ollama")

    response = await _service().get()

    assert (response.provider, response.model, response.dim, response.identity) == ("ollama", "embeddinggemma", None, None)
    assert response.documents_total is None


# ---------------------------------------------------------------- test and apply


@pytest.mark.asyncio
async def test_test_reports_the_size_and_identity_and_saves_nothing():
    repo = _Repo()

    result = await _service(repo, _Factory(768)).test(_candidate(model="embeddinggemma"))

    assert result.ok is True and result.dim == 768 and result.latency_ms == 7
    assert result.identity.startswith("ollama__embeddinggemma-") and result.identity.endswith("__768")
    assert "768" in result.detail and repo.rows == {}


@pytest.mark.asyncio
async def test_apply_saves_only_after_a_successful_probe_and_records_the_size_and_editor():
    repo, admin = _Repo(), uuid4()

    response = await _service(repo, _Factory(768)).apply(_candidate(model="embeddinggemma"), admin)

    row = repo.rows["embedding"]
    assert row.value == {
        "provider": "ollama", "model": "embeddinggemma", "base_url": "http://local-ollama.invalid:11434",
        "dim": 768, "key_hint": None,
    }
    assert row.updated_by == admin and row.secret_encrypted is None
    assert (response.source, response.dim, response.model_editable) == ("settings", 768, True)
    assert response.base_url == "http://local-ollama.invalid:11434"


@pytest.mark.asyncio
async def test_a_failed_probe_saves_nothing_and_keeps_the_previous_choice():
    repo = _Repo()
    await _service(repo, _Factory(768)).apply(_candidate(model="embeddinggemma"), uuid4())
    before = dict(repo.rows["embedding"].value)

    with pytest.raises(EmbeddingProbeFailed, match="the model was not found"):
        await _service(repo, _Factory(EmbeddingModelNotFound("Embeddings: the model was not found on the server"))).apply(
            _candidate(model="nope"), uuid4()
        )

    assert repo.rows["embedding"].value == before


@pytest.mark.asyncio
async def test_probe_failures_use_fixed_messages_that_never_contain_the_key_or_address():
    error = httpx.ConnectError(f"cannot reach http://user:hunter2@embed.internal with {KEY}")

    result = await _service(factory=_Factory(error)).test(_candidate(provider="ollama_cloud", model="m", api_key=KEY))

    assert result.ok is False and result.detail == "Embeddings: could not connect"
    assert KEY not in result.detail and "hunter2" not in result.detail


# ---------------------------------------------------------------- the key


@pytest.mark.asyncio
async def test_the_cloud_key_is_stored_encrypted_bound_to_the_system_and_never_returned():
    repo = _Repo()

    response = await _service(repo, _Factory(768)).apply(_candidate(provider="ollama_cloud", model="embeddinggemma", api_key=KEY), uuid4())

    token = repo.rows["embedding"].secret_encrypted
    assert token and KEY not in token and KEY not in str(repo.rows["embedding"].value)
    assert response.key_hint == "1111" and KEY not in response.model_dump_json()
    assert SecretBox(settings.SECRETS_ENCRYPTION_KEY.get_secret_value()).decrypt(token, context=SECRET_CONTEXT) == KEY
    with pytest.raises(SecretDecryptError):
        SecretBox(settings.SECRETS_ENCRYPTION_KEY.get_secret_value()).decrypt(token, context="1234:ollama_cloud")


@pytest.mark.asyncio
async def test_a_saved_key_is_kept_when_none_is_sent_for_the_same_provider():
    repo, factory = _Repo(), _Factory(768)
    service = _service(repo, factory)
    await service.apply(_candidate(provider="ollama_cloud", model="a", api_key=KEY), uuid4())

    await service.apply(_candidate(provider="ollama_cloud", model="b"), uuid4())

    assert factory.configs[-1].api_key == KEY  # the probe used the saved key
    assert SecretBox(settings.SECRETS_ENCRYPTION_KEY.get_secret_value()).decrypt(
        repo.rows["embedding"].secret_encrypted, context=SECRET_CONTEXT
    ) == KEY
    assert repo.rows["embedding"].value["model"] == "b"


@pytest.mark.asyncio
async def test_a_new_key_replaces_the_saved_one_and_clear_key_removes_it():
    repo = _Repo()
    service = _service(repo, _Factory(768))
    await service.apply(_candidate(provider="ollama_cloud", model="a", api_key=KEY), uuid4())

    await service.apply(_candidate(provider="ollama_cloud", model="a", api_key=OTHER_KEY), uuid4())
    assert repo.rows["embedding"].value["key_hint"] == "2222"

    await service.apply(_candidate(provider="ollama_cloud", model="a", clear_key=True), uuid4())
    assert repo.rows["embedding"].secret_encrypted is None and repo.rows["embedding"].value["key_hint"] is None


@pytest.mark.asyncio
async def test_switching_provider_never_carries_the_old_key_along():
    repo, factory = _Repo(), _Factory(768)
    service = _service(repo, factory)
    await service.apply(_candidate(provider="ollama_cloud", model="a", api_key=KEY), uuid4())

    await service.apply(_candidate(provider="ollama", model="a"), uuid4())

    assert factory.configs[-1].api_key is None and repo.rows["embedding"].secret_encrypted is None


@pytest.mark.asyncio
async def test_without_a_master_key_a_key_cannot_be_saved_and_nothing_is_stored(monkeypatch):
    from pydantic import SecretStr

    from app.core import secret_box as secret_box_module
    from app.core.secret_box import SecretsNotConfigured

    monkeypatch.setattr(settings, "SECRETS_ENCRYPTION_KEY", SecretStr(""))
    monkeypatch.setattr(secret_box_module, "_cached", None)
    repo = _Repo()

    with pytest.raises(SecretsNotConfigured):
        await _service(repo, _Factory(768)).apply(_candidate(provider="ollama_cloud", model="a", api_key=KEY), uuid4())

    assert repo.rows == {}


@pytest.mark.asyncio
async def test_a_key_that_can_no_longer_be_read_is_reported_not_crashed_on(monkeypatch):
    repo = _Repo()
    await _service(repo, _Factory(768)).apply(_candidate(provider="ollama_cloud", model="a", api_key=KEY), uuid4())
    repo.rows["embedding"].secret_encrypted = "not-a-valid-token"

    result = await _service(repo, _Factory(768)).test(_candidate(provider="ollama_cloud", model="a"))
    assert result.ok is False and "can no longer be read" in result.detail

    invalidate_active_embedding()
    with pytest.raises(VectorPathError, match="can no longer be read"):
        await _service(repo).active_config()


@pytest.mark.asyncio
async def test_the_key_is_never_logged():
    lines: list[str] = []
    sink = logger.add(lambda message: lines.append(str(message)), level="DEBUG")
    try:
        await _service(_Repo(), _Factory(httpx.ConnectError(KEY))).test(_candidate(provider="ollama_cloud", model="m", api_key=KEY))
        await _service(_Repo(), _Factory(768)).apply(_candidate(provider="ollama_cloud", model="m", api_key=KEY), uuid4())
    finally:
        logger.remove(sink)

    assert lines and not any(KEY in line for line in lines)


# ---------------------------------------------------------------- input rules


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("candidate", "message"),
    [
        (dict(provider="ollama"), "Enter the embedding model name"),
        (dict(provider="ollama_cloud"), "Enter the embedding model name"),
        (dict(provider="tei", base_url="http://attacker.example"), "set in the environment"),
        (dict(provider="ollama_cloud", model="m", base_url="https://attacker.example"), "fixed address"),
    ],
)
async def test_invalid_candidates_are_rejected_before_anything_is_probed(candidate, message):
    factory = _Factory(768)

    with pytest.raises(ValueError, match=message):
        await _service(factory=factory).test(EmbeddingCandidate(**candidate))

    assert factory.configs == []


@pytest.mark.asyncio
async def test_tei_always_uses_the_environments_model_and_address():
    factory = _Factory(1024)

    await _service(factory=factory).apply(EmbeddingCandidate(provider="tei", model="something-else"), uuid4())

    assert (factory.configs[0].model, factory.configs[0].base_url) == ("BAAI/bge-large-en-v1.5", "http://tei.invalid:80")


def test_the_schema_trims_and_validates_inputs():
    assert EmbeddingCandidate(provider="ollama", model="  m ", base_url=" http://h:1/ ").base_url == "http://h:1"
    assert EmbeddingCandidate(provider="ollama", model="  ").model is None
    for bad in ({"base_url": "ftp://x"}, {"base_url": "http://u:p@h"}, {"api_key": "short"}, {"api_key": "has space in key"}):
        with pytest.raises(Exception):
            EmbeddingCandidate(provider="ollama_cloud", **bad)
    assert KEY not in repr(EmbeddingCandidate(provider="ollama_cloud", model="m", api_key=KEY))


# ---------------------------------------------------------------- the active choice


@pytest.mark.asyncio
async def test_active_config_is_the_environment_until_an_admin_saves_one():
    config = await _service().active_config()

    assert (config.provider, config.dim) == ("tei", 1024) and config.api_key is None


@pytest.mark.asyncio
async def test_active_config_uses_the_saved_choice_with_its_decrypted_key_and_is_cached_until_an_apply():
    repo = _Repo()
    service = _service(repo, _Factory(768))
    await service.apply(_candidate(provider="ollama_cloud", model="embeddinggemma", api_key=KEY), uuid4())
    invalidate_active_embedding()

    first = await service.active_config()
    reads = repo.gets
    second = await service.active_config()

    assert (first.provider, first.model, first.dim, first.api_key) == ("ollama_cloud", "embeddinggemma", 768, KEY)
    assert second is first and repo.gets == reads  # the second call did not touch the database

    await service.apply(_candidate(provider="ollama_cloud", model="other"), uuid4())  # clears the cache
    assert (await service.active_config()).model == "other"


@pytest.mark.asyncio
async def test_an_environment_ollama_model_is_probed_once_for_its_size(monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "ollama")
    factory = _Factory(768)
    service = _service(factory=factory)

    first = await service.active_config()
    await service.active_config()

    assert first.dim == 768 and len(factory.configs) == 1


# ---------------------------------------------------------------- HTTP


def _client(service, *, role="admin"):
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, main_module.validation_error_handler)  # the real, sanitizing one
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4(), role=role)
    app.dependency_overrides[get_embedding_settings_service] = lambda: service
    return TestClient(app)


def test_anyone_signed_in_can_read_but_only_an_admin_can_test_or_change():
    service = _service(factory=_Factory(768))
    body = {"provider": "ollama", "model": "embeddinggemma"}

    with _client(service, role="user") as client:
        assert client.get("/settings/embedding").status_code == 200
        assert client.post("/settings/embedding/test", json=body).status_code == 403
        assert client.put("/settings/embedding", json=body).status_code == 403
    with _client(service, role="admin") as client:
        assert client.post("/settings/embedding/test", json=body).json()["ok"] is True
        assert client.put("/settings/embedding", json=body).status_code == 200


def test_the_endpoints_require_login():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_embedding_settings_service] = lambda: _service()

    with TestClient(app) as client:
        assert client.get("/settings/embedding").status_code == 401
        assert client.put("/settings/embedding", json={"provider": "tei"}).status_code == 401


def test_a_failed_apply_is_a_400_that_says_nothing_was_saved_and_leaves_the_old_choice():
    repo = _Repo()
    with _client(_service(repo, _Factory(768))) as client:
        assert client.put("/settings/embedding", json={"provider": "ollama", "model": "good"}).status_code == 200
    with _client(_service(repo, _Factory(httpx.ConnectError("x")))) as client:
        response = client.put("/settings/embedding", json={"provider": "ollama", "model": "bad"})

    assert response.status_code == 400 and response.json()["detail"].startswith("Not saved.")
    assert repo.rows["embedding"].value["model"] == "good"


def test_responses_never_contain_the_key_and_are_not_cached():
    repo = _Repo()
    with _client(_service(repo, _Factory(768))) as client:
        put = client.put("/settings/embedding", json={"provider": "ollama_cloud", "model": "m", "api_key": KEY})
        got = client.get("/settings/embedding")
        tested = client.post("/settings/embedding/test", json={"provider": "ollama_cloud", "model": "m", "api_key": KEY})

    for response in (put, got, tested):
        assert KEY not in response.text and response.headers["cache-control"] == "no-store"
    assert put.json()["key_hint"] == "1111"


def test_invalid_input_is_a_400_or_422_with_no_echo_of_the_key():
    with _client(_service(factory=_Factory(768))) as client:
        missing = client.put("/settings/embedding", json={"provider": "ollama"})
        bad_url = client.put("/settings/embedding", json={"provider": "ollama", "model": "m", "base_url": "ftp://x"})
        bad_key = client.put("/settings/embedding", json={"provider": "ollama_cloud", "model": "m", "api_key": "short key"})
        unknown = client.put("/settings/embedding", json={"provider": "mystery", "model": "m"})

    assert missing.status_code == 400 and "model name" in missing.json()["detail"]
    assert bad_url.status_code == 422 and bad_key.status_code == 422 and unknown.status_code == 422
    assert "short key" not in bad_key.text


def test_no_master_key_is_a_503_and_nothing_is_saved(monkeypatch):
    from pydantic import SecretStr

    from app.core import secret_box as secret_box_module

    monkeypatch.setattr(settings, "SECRETS_ENCRYPTION_KEY", SecretStr(""))
    monkeypatch.setattr(secret_box_module, "_cached", None)
    repo = _Repo()

    with _client(_service(repo, _Factory(768))) as client:
        response = client.put("/settings/embedding", json={"provider": "ollama_cloud", "model": "m", "api_key": KEY})

    assert response.status_code == 503 and repo.rows == {} and KEY not in response.text
