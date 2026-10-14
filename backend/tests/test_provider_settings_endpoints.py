from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_credential_service, get_current_user
from app.core.config import settings
from app.main import app
from app.services import credential_service as credential_service_module
from app.services.credential_service import CredentialService

BASE = "/api/v1/settings/providers"
SENTINEL = "sk-ant-test-SENTINEL-abcd1234"


@pytest.fixture
def api(credential_repo, master_key):
    holder = SimpleNamespace(user=SimpleNamespace(id=uuid4(), role="user", is_active=True))
    app.dependency_overrides[get_current_user] = lambda: holder.user
    app.dependency_overrides[get_credential_service] = lambda: CredentialService(credential_repo)
    try:
        yield TestClient(app), holder
    finally:
        app.dependency_overrides.clear()


def test_every_settings_route_and_the_chat_model_routes_need_a_login():
    client = TestClient(app)
    assert client.get(BASE).status_code == 401
    assert client.put(f"{BASE}/anthropic", json={"api_key": SENTINEL}).status_code == 401
    assert client.delete(f"{BASE}/anthropic").status_code == 401
    assert client.post(f"{BASE}/anthropic/test").status_code == 401
    assert client.get("/api/v1/chat/models").status_code == 401
    assert client.get("/api/v1/chat/providers/health").status_code == 401


def test_list_reports_all_three_providers(api):
    client, _ = api
    body = client.get(BASE).json()
    assert [item["provider"] for item in body] == ["anthropic", "openai", "ollama"]
    by_name = {item["provider"]: item for item in body}
    assert by_name["anthropic"]["configured"] is False and by_name["anthropic"]["source"] == "none"
    assert by_name["ollama"]["source"] == "server"
    assert by_name["openai"]["supported"] is False


def test_saving_a_key_returns_a_hint_and_never_the_key(api, credential_repo):
    client, holder = api
    response = client.put(f"{BASE}/anthropic", json={"api_key": SENTINEL})

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["key_hint"] == "1234" and response.json()["source"] == "user"
    stored = credential_repo.rows[(holder.user.id, "anthropic")].api_key_encrypted
    assert SENTINEL not in response.text and stored not in response.text

    listing = client.get(BASE)
    assert SENTINEL not in listing.text and stored not in listing.text
    assert {i["provider"]: i for i in listing.json()}["anthropic"]["key_hint"] == "1234"


def test_saving_without_a_master_key_is_a_clear_503(api, monkeypatch):
    from pydantic import SecretStr

    from app.core import secret_box as secret_box_module

    client, _ = api
    monkeypatch.setattr(settings, "SECRETS_ENCRYPTION_KEY", SecretStr(""))
    monkeypatch.setattr(secret_box_module, "_cached", None)

    response = client.put(f"{BASE}/anthropic", json={"api_key": SENTINEL})

    assert response.status_code == 503
    assert "SECRETS_ENCRYPTION_KEY" in response.text and SENTINEL not in response.text


def test_only_admins_can_set_the_ollama_url(api):
    client, holder = api
    denied = client.put(f"{BASE}/ollama", json={"base_url": "http://10.0.0.5:11434"})
    assert denied.status_code == 403

    holder.user.role = "admin"
    allowed = client.put(f"{BASE}/ollama", json={"base_url": "http://10.0.0.5:11434/"})
    assert allowed.status_code == 200 and allowed.json()["base_url"] == "http://10.0.0.5:11434"


def test_rejected_requests_return_422_without_echoing_the_submitted_key(api):
    client, _ = api
    leaky_key = "sk-ant-test-SENTINEL has spaces and fails validation"
    for body in (
        {"api_key": leaky_key},
        {"api_key": "short"},
        {"base_url": "ftp://example.com"},
        {"api_key": leaky_key, "base_url": "http://user:pass@host"},
    ):
        response = client.put(f"{BASE}/anthropic", json=body)
        assert response.status_code == 422, body
        assert "SENTINEL" not in response.text and "pass@host" not in response.text
        assert all("input" not in err for err in response.json()["details"]["errors"])


def test_unknown_provider_and_empty_body_are_rejected(api):
    client, _ = api
    assert client.put(f"{BASE}/mystery", json={"api_key": SENTINEL}).status_code == 422
    assert client.put(f"{BASE}/anthropic", json={}).status_code == 400


def test_delete_removes_the_saved_key(api):
    client, _ = api
    client.put(f"{BASE}/anthropic", json={"api_key": SENTINEL})
    assert client.delete(f"{BASE}/anthropic").status_code == 204
    assert {i["provider"]: i for i in client.get(BASE).json()}["anthropic"]["configured"] is False


def test_test_endpoint_uses_the_saved_key_and_reports_a_safe_result(api, monkeypatch):
    client, _ = api
    client.put(f"{BASE}/anthropic", json={"api_key": SENTINEL})
    seen = {}

    async def fake_test_connection(cls, provider, credentials):
        seen["provider"], seen["key"] = provider, credentials.api_key
        return {"ok": False, "error_type": "provider_auth_error", "detail": "The provider rejected the key."}

    monkeypatch.setattr(credential_service_module.LLMService, "test_connection", classmethod(fake_test_connection))

    response = client.post(f"{BASE}/anthropic/test")

    assert seen == {"provider": "anthropic", "key": SENTINEL}  # the decrypted key reached the provider call
    assert response.status_code == 200
    assert response.json() == {"ok": False, "error_type": "provider_auth_error", "detail": "The provider rejected the key."}
    assert SENTINEL not in response.text
