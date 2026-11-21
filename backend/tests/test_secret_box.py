from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.core import secret_box as secret_box_module
from app.core.config import settings
from app.core.secret_box import SecretBox, SecretDecryptError, SecretsNotConfigured, get_secret_box

SENTINEL = "sk-test-SENTINEL-0123456789"
CTX = "11111111-1111-1111-1111-111111111111:anthropic"


def _key() -> str:
    return Fernet.generate_key().decode()


def test_round_trip_and_ciphertext_hides_the_plaintext():
    box = SecretBox(_key())
    token = box.encrypt(SENTINEL, context=CTX)
    assert SENTINEL not in token
    assert box.decrypt(token, context=CTX) == SENTINEL


def test_each_encryption_differs():
    box = SecretBox(_key())
    assert box.encrypt(SENTINEL, context=CTX) != box.encrypt(SENTINEL, context=CTX)


def test_ciphertext_does_not_open_for_another_owner_or_provider():
    box = SecretBox(_key())
    token = box.encrypt(SENTINEL, context=CTX)
    with pytest.raises(SecretDecryptError):
        box.decrypt(token, context="22222222-2222-2222-2222-222222222222:anthropic")
    with pytest.raises(SecretDecryptError):
        box.decrypt(token, context="11111111-1111-1111-1111-111111111111:openai")


def test_rotation_keeps_old_data_readable_and_new_data_uses_the_new_key():
    old, new = _key(), _key()
    token_under_old = SecretBox(old).encrypt(SENTINEL, context=CTX)

    rotated = SecretBox(f"{new},{old}")
    assert rotated.decrypt(token_under_old, context=CTX) == SENTINEL

    token_under_new = rotated.encrypt(SENTINEL, context=CTX)
    assert SecretBox(new).decrypt(token_under_new, context=CTX) == SENTINEL  # new key alone is enough
    with pytest.raises(SecretDecryptError):
        SecretBox(old).decrypt(token_under_new, context=CTX)


def test_dropping_the_old_key_makes_old_rows_unreadable_without_leaking_anything():
    old, new = _key(), _key()
    token = SecretBox(old).encrypt(SENTINEL, context=CTX)
    with pytest.raises(SecretDecryptError) as caught:
        SecretBox(new).decrypt(token, context=CTX)
    assert SENTINEL not in str(caught.value) and token not in str(caught.value)


def test_unset_master_key_is_reported_and_refuses_to_encrypt():
    box = SecretBox("")
    assert (box.is_configured, box.status) == (False, "missing")
    with pytest.raises(SecretsNotConfigured) as caught:
        box.encrypt(SENTINEL, context=CTX)
    assert "not set" in str(caught.value) and SENTINEL not in str(caught.value)


def test_invalid_master_key_is_reported_without_echoing_it():
    bad = "this-is-not-a-fernet-key-DO-NOT-ECHO"
    box = SecretBox(bad)
    assert (box.is_configured, box.status) == (False, "invalid")
    with pytest.raises(SecretsNotConfigured) as caught:
        box.encrypt(SENTINEL, context=CTX)
    assert bad not in str(caught.value) and "not a valid Fernet key" in str(caught.value)


def test_garbage_token_raises_a_decrypt_error():
    box = SecretBox(_key())
    with pytest.raises(SecretDecryptError):
        box.decrypt("not-a-token", context=CTX)


def test_get_secret_box_follows_the_settings_and_the_setting_hides_its_value(monkeypatch):
    from pydantic import SecretStr

    key = _key()
    monkeypatch.setattr(settings, "SECRETS_ENCRYPTION_KEY", SecretStr(key))
    monkeypatch.setattr(secret_box_module, "_cached", None)
    assert get_secret_box().is_configured
    assert key not in repr(settings) and key not in str(settings.SECRETS_ENCRYPTION_KEY)

    monkeypatch.setattr(settings, "SECRETS_ENCRYPTION_KEY", SecretStr(""))
    assert get_secret_box().status == "missing"
