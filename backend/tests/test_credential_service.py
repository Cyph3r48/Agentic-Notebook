from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from app.core.config import settings
from app.core.secret_box import SecretBox, SecretsNotConfigured
from app.services.credential_service import CredentialService

SENTINEL = "sk-ant-test-SENTINEL-abcd1234"


def _user(role="user"):
    return SimpleNamespace(id=uuid4(), role=role)


def _service(repo, master_key) -> CredentialService:
    return CredentialService(repo, SecretBox(master_key))


@pytest.mark.asyncio
async def test_saved_key_is_stored_encrypted_and_resolved_back(credential_repo, master_key):
    service, user = _service(credential_repo, master_key), _user()

    status = await service.save(user, "anthropic", api_key=SENTINEL, base_url=None, base_url_provided=False)

    row = credential_repo.rows[(user.id, "anthropic")]
    assert SENTINEL not in row.api_key_encrypted
    assert row.key_hint == "1234"
    assert (status.configured, status.source, status.key_hint) == (True, "user", "1234")
    resolved = await service.resolve(user.id, "anthropic")
    assert resolved.api_key == SENTINEL and resolved.source == "user"


@pytest.mark.asyncio
async def test_status_never_contains_the_key_or_the_ciphertext(credential_repo, master_key):
    service, user = _service(credential_repo, master_key), _user()
    await service.save(user, "anthropic", api_key=SENTINEL, base_url=None, base_url_provided=False)

    dumped = " ".join(item.model_dump_json() for item in await service.status(user.id))

    assert SENTINEL not in dumped
    assert credential_repo.rows[(user.id, "anthropic")].api_key_encrypted not in dumped


@pytest.mark.asyncio
async def test_resolution_order_user_then_server_then_none(credential_repo, master_key, monkeypatch):
    service, user = _service(credential_repo, master_key), _user()
    assert await service.resolve(user.id, "anthropic") is None

    monkeypatch.setattr(settings, "CLAUDE_API_KEY", "sk-server-wide-key-1111")
    server = await service.resolve(user.id, "anthropic")
    assert server.api_key == "sk-server-wide-key-1111" and server.source == "server"
    assert (await service.status_for(user.id, "anthropic")).source == "server"

    await service.save(user, "anthropic", api_key=SENTINEL, base_url=None, base_url_provided=False)
    assert (await service.resolve(user.id, "anthropic")).api_key == SENTINEL


@pytest.mark.asyncio
async def test_server_key_fallback_can_be_switched_off(credential_repo, master_key, monkeypatch):
    monkeypatch.setattr(settings, "CLAUDE_API_KEY", "sk-server-wide-key-1111")
    monkeypatch.setattr(settings, "ALLOW_SERVER_PROVIDER_KEYS", False)
    service, user = _service(credential_repo, master_key), _user()

    assert await service.resolve(user.id, "anthropic") is None
    status = await service.status_for(user.id, "anthropic")
    assert (status.configured, status.source) == (False, "none")


@pytest.mark.asyncio
async def test_users_do_not_see_each_others_keys(credential_repo, master_key):
    service, alice, bob = _service(credential_repo, master_key), _user(), _user()
    await service.save(alice, "anthropic", api_key=SENTINEL, base_url=None, base_url_provided=False)

    assert await service.resolve(bob.id, "anthropic") is None
    assert (await service.status_for(bob.id, "anthropic")).configured is False


@pytest.mark.asyncio
async def test_saving_a_key_needs_a_master_key(credential_repo):
    service = CredentialService(credential_repo, SecretBox(""))
    with pytest.raises(SecretsNotConfigured):
        await service.save(_user(), "anthropic", api_key=SENTINEL, base_url=None, base_url_provided=False)
    assert credential_repo.rows == {}


@pytest.mark.asyncio
async def test_only_admins_can_set_the_ollama_url(credential_repo, master_key):
    service = _service(credential_repo, master_key)
    with pytest.raises(PermissionError):
        await service.save(_user("user"), "ollama", api_key=None, base_url="http://10.0.0.5:11434", base_url_provided=True)

    admin = _user("admin")
    status = await service.save(admin, "ollama", api_key=None, base_url="http://10.0.0.5:11434", base_url_provided=True)
    assert status.base_url == "http://10.0.0.5:11434" and status.source == "user"
    assert (await service.resolve(admin.id, "ollama")).base_url == "http://10.0.0.5:11434"


@pytest.mark.asyncio
async def test_non_admins_can_still_save_an_ollama_key(credential_repo, master_key):
    service, user = _service(credential_repo, master_key), _user("user")
    await service.save(user, "ollama", api_key="ollama-cloud-key-5678", base_url=None, base_url_provided=False)
    resolved = await service.resolve(user.id, "ollama")
    assert resolved.api_key == "ollama-cloud-key-5678" and resolved.base_url is None


@pytest.mark.asyncio
async def test_base_url_is_only_for_ollama_and_empty_saves_are_rejected(credential_repo, master_key):
    service, admin = _service(credential_repo, master_key), _user("admin")
    with pytest.raises(ValueError):
        await service.save(admin, "anthropic", api_key=None, base_url="http://x", base_url_provided=True)
    with pytest.raises(ValueError):
        await service.save(admin, "ollama", api_key=None, base_url=None, base_url_provided=False)


@pytest.mark.asyncio
async def test_a_second_save_without_a_key_keeps_the_saved_key(credential_repo, master_key):
    service, admin = _service(credential_repo, master_key), _user("admin")
    await service.save(admin, "ollama", api_key="ollama-cloud-key-5678", base_url=None, base_url_provided=False)
    await service.save(admin, "ollama", api_key=None, base_url="https://ollama.com", base_url_provided=True)

    resolved = await service.resolve(admin.id, "ollama")
    assert resolved.api_key == "ollama-cloud-key-5678" and resolved.base_url == "https://ollama.com"


@pytest.mark.asyncio
async def test_a_key_that_cannot_be_decrypted_is_reported_not_fatal(credential_repo, master_key):
    service, user = _service(credential_repo, master_key), _user()
    await service.save(user, "anthropic", api_key=SENTINEL, base_url=None, base_url_provided=False)

    after_rotation_loss = CredentialService(credential_repo, SecretBox(Fernet.generate_key().decode()))
    status = await after_rotation_loss.status_for(user.id, "anthropic")
    assert status.needs_reentry is True and status.key_hint is None and status.configured is False
    assert await after_rotation_loss.resolve(user.id, "anthropic") is None


@pytest.mark.asyncio
async def test_rotated_master_key_still_reads_old_rows(credential_repo, master_key):
    user = _user()
    await _service(credential_repo, master_key).save(user, "anthropic", api_key=SENTINEL, base_url=None, base_url_provided=False)

    rotated = CredentialService(credential_repo, SecretBox(f"{Fernet.generate_key().decode()},{master_key}"))
    assert (await rotated.resolve(user.id, "anthropic")).api_key == SENTINEL


@pytest.mark.asyncio
async def test_delete_removes_the_row(credential_repo, master_key):
    service, user = _service(credential_repo, master_key), _user()
    await service.save(user, "anthropic", api_key=SENTINEL, base_url=None, base_url_provided=False)
    assert await service.delete(user.id, "anthropic") is True
    assert await service.delete(user.id, "anthropic") is False
    assert (await service.status_for(user.id, "anthropic")).configured is False


@pytest.mark.asyncio
async def test_openai_keys_can_be_stored_and_the_provider_is_supported(credential_repo, master_key):
    service, user = _service(credential_repo, master_key), _user()
    status = await service.save(user, "openai", api_key="sk-openai-test-9999", base_url=None, base_url_provided=False)
    assert status.supported is True and status.configured is True and status.key_hint == "9999"


@pytest.mark.asyncio
async def test_openai_resolution_order_user_then_server_then_none(credential_repo, master_key, monkeypatch):
    service, user = _service(credential_repo, master_key), _user()
    assert await service.resolve(user.id, "openai") is None
    assert (await service.status_for(user.id, "openai")).source == "none"

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-server-wide-key-3333")
    server = await service.resolve(user.id, "openai")
    assert server.api_key == "sk-server-wide-key-3333" and server.source == "server"
    assert (await service.status_for(user.id, "openai")).source == "server"

    await service.save(user, "openai", api_key=SENTINEL, base_url=None, base_url_provided=False)
    mine = await service.resolve(user.id, "openai")
    assert mine.api_key == SENTINEL and mine.source == "user"


@pytest.mark.asyncio
async def test_openai_server_key_fallback_can_be_switched_off(credential_repo, master_key, monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-server-wide-key-3333")
    monkeypatch.setattr(settings, "ALLOW_SERVER_PROVIDER_KEYS", False)
    service, user = _service(credential_repo, master_key), _user()

    assert await service.resolve(user.id, "openai") is None
    assert (await service.status_for(user.id, "openai")).configured is False


@pytest.mark.asyncio
async def test_a_base_url_can_be_saved_only_for_providers_that_accept_one(credential_repo, master_key):
    service = _service(credential_repo, master_key)
    admin = SimpleNamespace(id=uuid4(), role="admin")

    with pytest.raises(ValueError, match="Only Ollama has a base URL"):
        await service.save(admin, "openai", api_key=None, base_url="https://example.com", base_url_provided=True)
    status = await service.save(admin, "ollama", api_key=None, base_url="http://localhost:11434", base_url_provided=True)
    assert status.base_url == "http://localhost:11434"


@pytest.mark.asyncio
async def test_openai_key_is_encrypted_in_storage_and_bound_to_its_owner(credential_repo, master_key):
    service, user = _service(credential_repo, master_key), _user()
    await service.save(user, "openai", api_key=SENTINEL, base_url=None, base_url_provided=False)

    stored = credential_repo.rows[(user.id, "openai")].api_key_encrypted
    assert SENTINEL not in stored

    # The same ciphertext copied under another user or provider does not decrypt.
    other = _user()
    credential_repo.rows[(other.id, "openai")] = credential_repo.rows[(user.id, "openai")]
    assert await service.resolve(other.id, "openai") is None


@pytest.mark.asyncio
async def test_ollama_cloud_needs_a_saved_key_and_has_no_base_url_or_server_fallback(credential_repo, master_key):
    service, user = _service(credential_repo, master_key), _user()
    assert await service.resolve(user.id, "ollama_cloud") is None
    status = await service.status_for(user.id, "ollama_cloud")
    assert (status.supported, status.configured, status.source) == (True, False, "none")

    admin = SimpleNamespace(id=uuid4(), role="admin")
    with pytest.raises(ValueError, match="Only Ollama has a base URL"):
        await service.save(admin, "ollama_cloud", api_key=None, base_url="https://attacker.example", base_url_provided=True)

    await service.save(user, "ollama_cloud", api_key=SENTINEL, base_url=None, base_url_provided=False)
    mine = await service.resolve(user.id, "ollama_cloud")
    assert mine.api_key == SENTINEL and mine.base_url is None and mine.source == "user"
    assert (await service.status_for(user.id, "ollama_cloud")).source == "user"


@pytest.mark.asyncio
async def test_the_cloud_key_and_the_local_ollama_settings_are_separate_rows(credential_repo, master_key):
    service = _service(credential_repo, master_key)
    admin = SimpleNamespace(id=uuid4(), role="admin")
    await service.save(admin, "ollama", api_key=None, base_url="http://localhost:11434", base_url_provided=True)
    await service.save(admin, "ollama_cloud", api_key=SENTINEL, base_url=None, base_url_provided=False)

    local = await service.resolve(admin.id, "ollama")
    cloud = await service.resolve(admin.id, "ollama_cloud")

    assert local.base_url == "http://localhost:11434" and local.api_key is None
    assert cloud.api_key == SENTINEL and cloud.base_url is None
