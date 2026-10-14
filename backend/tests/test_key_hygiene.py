"""A recognizable fake key goes through every path; it must never come back out in a response or a log line."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from loguru import logger

from app.api.deps import get_credential_service, get_current_user
from app.core.config import settings
from app.main import app
from app.schemas.provider_settings import ProviderSaveRequest
from app.services.credential_service import CredentialService
from app.services.llm_service import LLMService, ProviderCredentials

SENTINEL = "sk-ant-test-SENTINEL-hygiene-0001"
BASE = "/api/v1/settings/providers"


@pytest.fixture
def captured_logs():
    lines: list[str] = []
    handler_id = logger.add(lambda message: lines.append(str(message)), level="DEBUG", format="{level} {message} {extra}")
    try:
        yield lines
    finally:
        logger.remove(handler_id)


def test_objects_that_hold_a_key_do_not_reveal_it_in_repr():
    assert SENTINEL not in repr(ProviderCredentials(api_key=SENTINEL, source="user", owner="u"))
    assert SENTINEL not in repr(ProviderSaveRequest(api_key=SENTINEL))
    assert SENTINEL not in repr(settings.SECRETS_ENCRYPTION_KEY)


def test_save_test_and_delete_leave_no_key_in_responses_or_logs(credential_repo, master_key, captured_logs, monkeypatch):
    user = SimpleNamespace(id=uuid4(), role="admin", is_active=True)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_credential_service] = lambda: CredentialService(credential_repo)
    try:
        client = TestClient(app)
        bodies = [
            client.put(f"{BASE}/anthropic", json={"api_key": SENTINEL}).text,
            client.get(BASE).text,
            client.put(f"{BASE}/anthropic", json={"api_key": SENTINEL + " has spaces"}).text,  # rejected: 422
            client.post(f"{BASE}/openai/test").text,
            client.delete(f"{BASE}/anthropic").text,
        ]
    finally:
        app.dependency_overrides.clear()

    assert not any(SENTINEL in body for body in bodies)
    assert not any(SENTINEL in line for line in captured_logs)
    assert any("provider_credential_saved" in line for line in captured_logs)  # the audit line exists, without the key


class _FailingClient:
    """An Anthropic client stand-in whose every call fails, like a provider outage."""

    def __init__(self):
        self.messages = SimpleNamespace(stream=self._fail)
        self.models = SimpleNamespace(list=self._fail)

    @staticmethod
    def _fail(*args, **kwargs):
        raise RuntimeError("upstream exploded")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


@pytest.mark.asyncio
async def test_a_failing_provider_call_logs_no_key(captured_logs, monkeypatch):
    monkeypatch.setattr(LLMService, "_anthropic_client", classmethod(lambda cls, **kwargs: _FailingClient()))
    monkeypatch.setattr(LLMService, "_model_cache", {})

    credentials = ProviderCredentials(api_key=SENTINEL, source="user", owner="u1")
    _, metadata = await LLMService.generate_chat_reply(
        model="claude-sonnet-5-5", user_message="hi", context_lines=[], credentials=credentials
    )

    assert metadata["error_type"] == "provider_error"
    assert captured_logs, "the failure should have been logged"
    assert not any(SENTINEL in line for line in captured_logs)
    assert SENTINEL not in str(metadata)
