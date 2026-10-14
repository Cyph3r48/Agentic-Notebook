"""Encryption for secrets stored in the database, such as provider API keys.

Values are encrypted with Fernet (authenticated encryption) under keys from `SECRETS_ENCRYPTION_KEY`.
Several comma-separated keys are accepted, newest first, so the master key can rotate: new data uses the
first key and old data still decrypts with the others.

Fernet has no associated-data field, so the owner of a value (for example "<user id>:<provider>") goes
inside the encrypted envelope and is checked on decrypt. A ciphertext copied to another row will not open.

Nothing here puts a key or a plaintext value in an exception message or a log line.
"""

from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import settings


class SecretsNotConfigured(RuntimeError):
    """The master key is missing or invalid, so nothing can be encrypted or decrypted."""


class SecretDecryptError(RuntimeError):
    """A stored value could not be decrypted (master key changed, data corrupted, or wrong owner)."""


class SecretBox:
    def __init__(self, keys: str):
        self._fernet: MultiFernet | None = None
        self._invalid = False
        parts = [part.strip() for part in keys.split(",") if part.strip()]
        if not parts:
            return
        try:
            self._fernet = MultiFernet([Fernet(part.encode("utf-8")) for part in parts])
        except (ValueError, TypeError):
            # The library's message does not include the key, but we drop it anyway.
            self._invalid = True

    @property
    def is_configured(self) -> bool:
        return self._fernet is not None

    @property
    def status(self) -> str:
        """"ok", "missing" (nothing set) or "invalid" (set, but not usable Fernet keys)."""
        if self._fernet is not None:
            return "ok"
        return "invalid" if self._invalid else "missing"

    def _require(self) -> MultiFernet:
        if self._fernet is None:
            raise SecretsNotConfigured(
                "SECRETS_ENCRYPTION_KEY is "
                + ("not a valid Fernet key" if self._invalid else "not set")
                + ". Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        return self._fernet

    def encrypt(self, value: str, *, context: str) -> str:
        envelope = json.dumps({"c": context, "v": value}).encode("utf-8")
        return self._require().encrypt(envelope).decode("ascii")

    def decrypt(self, token: str, *, context: str) -> str:
        fernet = self._require()
        try:
            envelope = json.loads(fernet.decrypt(token.encode("ascii")))
        except (InvalidToken, ValueError, UnicodeError):
            raise SecretDecryptError("Stored value could not be decrypted (master key changed or data corrupted)") from None
        if not isinstance(envelope, dict) or envelope.get("c") != context or not isinstance(envelope.get("v"), str):
            raise SecretDecryptError("Stored value does not belong to this owner")
        return envelope["v"]


_cached: tuple[str, SecretBox] | None = None


def get_secret_box() -> SecretBox:
    """The box for the current settings. Rebuilt when the configured keys change (tests do this)."""
    global _cached
    raw = settings.SECRETS_ENCRYPTION_KEY.get_secret_value()
    if _cached is None or _cached[0] != raw:
        _cached = (raw, SecretBox(raw))
    return _cached[1]
