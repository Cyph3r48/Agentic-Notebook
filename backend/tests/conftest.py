"""Shared fixtures for provider-credential tests."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.core import secret_box as secret_box_module
from app.core.config import settings


class InMemoryCredentialRepo:
    """Same interface as CredentialRepository, without a database."""

    def __init__(self):
        self.rows: dict[tuple, SimpleNamespace] = {}

    async def get(self, *, user_id, provider):
        return self.rows.get((user_id, provider))

    async def list_for_user(self, *, user_id):
        return [row for (owner, _), row in self.rows.items() if owner == user_id]

    async def upsert(
        self,
        *,
        user_id,
        provider,
        api_key_encrypted=None,
        key_hint=None,
        base_url=None,
        replace_key=False,
        replace_url=False,
    ):
        row = self.rows.get((user_id, provider))
        if row is None:
            row = SimpleNamespace(
                user_id=user_id,
                provider=provider,
                api_key_encrypted=None,
                key_hint=None,
                base_url=None,
                updated_at=None,
            )
            self.rows[(user_id, provider)] = row
        if replace_key:
            row.api_key_encrypted = api_key_encrypted
            row.key_hint = key_hint
        if replace_url:
            row.base_url = base_url
        row.updated_at = datetime.now(tz=timezone.utc)
        return row

    async def delete(self, *, user_id, provider):
        return self.rows.pop((user_id, provider), None) is not None


@pytest.fixture
def credential_repo() -> InMemoryCredentialRepo:
    return InMemoryCredentialRepo()


@pytest.fixture
def master_key(monkeypatch) -> str:
    """A fresh master key set as the app's SECRETS_ENCRYPTION_KEY for the duration of the test."""
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "SECRETS_ENCRYPTION_KEY", SecretStr(key))
    monkeypatch.setattr(secret_box_module, "_cached", None)
    return key


@pytest.fixture(autouse=True)
def _no_server_claude_key(monkeypatch):
    """Tests start with no server-wide Claude key and the fallback allowed; they opt in to anything else."""
    monkeypatch.setattr(settings, "CLAUDE_API_KEY", "")
    monkeypatch.setattr(settings, "ALLOW_SERVER_PROVIDER_KEYS", True)


class FakeMemory:
    """Stands in for a MemoryProvider. Records calls and returns what the test set."""

    def __init__(self, results=None, mode="keyword", degraded_reason=None):
        from app.services.memory import MemoryChunk

        self._chunk = MemoryChunk
        self.results = list(results or [])
        self.mode = mode
        self.degraded_reason = degraded_reason
        self.search_calls: list[dict] = []

    def chunk(self, **overrides):
        values = {
            "document_id": "00000000-0000-0000-0000-000000000001",
            "original_filename": "doc.txt",
            "chunk_index": 0,
            "content": "chunk",
            "score": 0.8,
        }
        values.update(overrides)
        return self._chunk(**values)

    async def search(self, **kwargs):
        from app.services.memory import SearchOutcome

        self.search_calls.append(kwargs)
        return SearchOutcome(self.results, mode=self.mode, degraded_reason=self.degraded_reason)

    async def ingest(self, **kwargs):
        raise AssertionError("not expected in this test")

    async def delete(self, **kwargs):
        raise AssertionError("not expected in this test")

    async def health(self):
        raise AssertionError("not expected in this test")


@pytest.fixture
def fake_memory():
    return FakeMemory()
