from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import settings
from app.services.llm import ollama_provider as ollama_module
from app.services.llm.base import ChatRequest, ProviderCredentials, StreamOutcome, UnsupportedModel
from app.services.llm.ollama_cloud_provider import OLLAMA_CLOUD_URL, OllamaCloudProvider
from app.services.llm.ollama_provider import OllamaProvider
from app.services.llm_service import LLMService

KEY = "ollama-cloud-test-SENTINEL-1111"
OTHER_KEY = "ollama-cloud-test-SENTINEL-2222"


def _creds(key=KEY, base_url=None, owner="u1"):
    return ProviderCredentials(api_key=key, base_url=base_url, source="user", owner=owner)


def _request(**overrides):
    values = dict(model="gpt-oss:120b", user_message="hi", context_lines=[], history=None, system_prompt=None)
    values.update(overrides)
    return ChatRequest(**values)


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    monkeypatch.setattr(OllamaCloudProvider, "_model_cache", {})
    monkeypatch.setattr(LLMService, "_failure_count", {})
    monkeypatch.setattr(LLMService, "_circuit_open_until", {})
    monkeypatch.setattr(ollama_module, "OLLAMA_RETRY_DELAY_SECONDS", 0)
    monkeypatch.setattr(settings, "OLLAMA_URL", "http://local-ollama.invalid:11434")


class _Seen(list):
    """The requests seen so far, plus the handler a test can swap to change the reply."""

    def __init__(self):
        super().__init__()
        self.handlers = {"respond": lambda request: httpx.Response(200, json={"models": []})}


@pytest.fixture
def http(monkeypatch):
    """Route every httpx client through a recorder. Returns the list of requests seen."""
    seen = _Seen()

    def respond(request):
        seen.append(request)
        return seen.handlers["respond"](request)

    transport = httpx.MockTransport(respond)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(ollama_module.httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport, **kwargs))
    return seen


def _chat_ok(text="hello"):
    return httpx.Response(200, json={"message": {"content": text}, "prompt_eval_count": 5, "eval_count": 2})


def _tags(*names):
    return httpx.Response(200, json={"models": [{"name": n} for n in names]})


# ---------------------------------------------------------------- the key only goes to ollama.com


@pytest.mark.asyncio
async def test_chat_goes_to_ollama_com_with_the_users_bearer_key(http):
    http.handlers["respond"] = lambda request: _chat_ok()

    result = await OllamaCloudProvider.generate(_request(), _creds())

    assert result.text == "hello"
    assert [str(r.url) for r in http] == [f"{OLLAMA_CLOUD_URL}/api/chat"]
    assert http[0].headers["authorization"] == f"Bearer {KEY}"
    assert json.loads(http[0].content)["model"] == "gpt-oss:120b"


@pytest.mark.asyncio
async def test_a_saved_base_url_is_ignored_so_the_key_cannot_be_sent_elsewhere(http):
    http.handlers["respond"] = lambda request: _chat_ok()
    hostile = _creds(base_url="https://attacker.example")

    await OllamaCloudProvider.generate(_request(), hostile)
    [chunk async for chunk in OllamaCloudProvider.stream(_request(), hostile, StreamOutcome())]
    await OllamaCloudProvider.list_models(hostile)
    await OllamaCloudProvider.test_connection(hostile)
    await OllamaCloudProvider.health(hostile)

    assert http, "expected requests"
    assert {r.url.host for r in http} == {"ollama.com"}
    assert not any("attacker" in str(r.url) for r in http)


@pytest.mark.asyncio
async def test_the_local_ollama_still_uses_its_own_url_and_sends_no_key_to_the_cloud(http):
    http.handlers["respond"] = lambda request: _chat_ok()

    await OllamaProvider.generate(_request(model="llama3.2:3b"), None)

    assert [r.url.host for r in http] == ["local-ollama.invalid"]
    assert "authorization" not in http[0].headers


@pytest.mark.asyncio
async def test_without_a_key_nothing_is_sent_at_all(http):
    with pytest.raises(RuntimeError, match="No Ollama Cloud API key"):
        await OllamaCloudProvider.generate(_request(), None)
    with pytest.raises(RuntimeError, match="No Ollama Cloud API key"):
        [chunk async for chunk in OllamaCloudProvider.stream(_request(), ProviderCredentials(api_key=None, source="user"))]

    assert await OllamaCloudProvider.list_models(None) == []
    assert await OllamaCloudProvider.health(None) == {"healthy": False}
    assert (await OllamaCloudProvider.test_connection(None))["error_type"] == "not_configured"
    assert http == []


@pytest.mark.asyncio
async def test_streaming_records_usage_like_the_local_provider(http):
    body = "\n".join(
        json.dumps(line)
        for line in (
            {"message": {"content": "Hel"}, "done": False},
            {"message": {"content": "lo"}, "done": True, "done_reason": "stop", "prompt_eval_count": 4, "eval_count": 2},
        )
    )
    http.handlers["respond"] = lambda request: httpx.Response(200, text=body)
    outcome = StreamOutcome()

    parts = [p async for p in OllamaCloudProvider.stream(_request(), _creds(), outcome)]

    assert parts == ["Hel", "lo"] and (outcome.input_tokens, outcome.output_tokens) == (4, 2)


# ---------------------------------------------------------------- models and the test button


@pytest.mark.asyncio
async def test_models_are_listed_from_the_cloud_and_cached_per_credential(http):
    def handler(request):
        key = request.headers["authorization"].removeprefix("Bearer ")
        return _tags("gpt-oss:120b") if key == KEY else _tags("kimi-k2")

    http.handlers["respond"] = handler

    first = await OllamaCloudProvider.list_models(_creds(KEY))
    again = await OllamaCloudProvider.list_models(_creds(KEY))
    other = await OllamaCloudProvider.list_models(_creds(OTHER_KEY))

    assert [m.id for m in first] == [m.id for m in again] == ["gpt-oss:120b"]
    assert [m.id for m in other] == ["kimi-k2"]
    assert len(http) == 2  # the repeat for the first key came from the cache


@pytest.mark.asyncio
async def test_a_failed_listing_is_reported_as_empty_and_remembered_briefly(http):
    http.handlers["respond"] = lambda request: httpx.Response(401)

    assert await OllamaCloudProvider.list_models(_creds()) == []
    assert await OllamaCloudProvider.list_models(_creds()) == []
    assert len(http) == 1


@pytest.mark.asyncio
async def test_resolve_model_checks_the_users_list_but_tolerates_an_empty_one(http):
    http.handlers["respond"] = lambda request: _tags("gpt-oss:120b")
    assert await OllamaCloudProvider.resolve_model(" gpt-oss:120b ", _creds()) == "gpt-oss:120b"
    with pytest.raises(UnsupportedModel, match="Unsupported Ollama Cloud model"):
        await OllamaCloudProvider.resolve_model("nope:1b", _creds())

    http.handlers["respond"] = lambda request: _tags()
    assert await OllamaCloudProvider.resolve_model("anything:1b", _creds(OTHER_KEY)) == "anything:1b"

    with pytest.raises(UnsupportedModel, match="Add one in Settings"):
        await OllamaCloudProvider.resolve_model("gpt-oss:120b", None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected"),
    [(401, "provider_auth_error"), (403, "provider_auth_error"), (429, "provider_rate_limited"), (500, "provider_http_error")],
)
async def test_connection_test_reports_fixed_safe_details(http, status, expected):
    http.handlers["respond"] = lambda request: httpx.Response(status, json={"error": f"nope {KEY}"})

    result = await OllamaCloudProvider.test_connection(_creds())

    assert result["ok"] is False and result["error_type"] == expected
    assert KEY not in repr(result) and "nope" not in repr(result)


@pytest.mark.asyncio
async def test_connection_test_ok(http):
    http.handlers["respond"] = lambda request: _tags("gpt-oss:120b")

    assert (await OllamaCloudProvider.test_connection(_creds()))["ok"] is True


# ---------------------------------------------------------------- identity and isolation


def test_a_cloud_model_is_never_inferred_from_its_name():
    from app.services.llm import provider_for_model

    assert OllamaCloudProvider.owns("gpt-oss:120b") is False
    for name in ("gpt-oss:120b", "kimi-k2", "llama3.2:3b", "gpt-5.5", "claude-sonnet-5-5"):
        assert provider_for_model(name) != "ollama_cloud"


@pytest.mark.asyncio
async def test_the_service_runs_a_conversation_on_the_stored_provider_even_when_names_collide(http):
    http.handlers["respond"] = lambda request: _chat_ok("from cloud")

    _, cloud = await LLMService.generate_chat_reply(
        model="gpt-oss:120b", user_message="hi", context_lines=[], credentials=_creds(), provider="ollama_cloud"
    )
    http.handlers["respond"] = lambda request: _chat_ok("from local")
    _, local = await LLMService.generate_chat_reply(model="gpt-oss:120b", user_message="hi", context_lines=[])

    assert cloud["provider"] == "ollama_cloud" and local["provider"] == "ollama"
    assert [r.url.host for r in http] == ["ollama.com", "local-ollama.invalid"]


@pytest.mark.asyncio
async def test_one_users_cloud_failures_do_not_open_another_users_circuit(http):
    http.handlers["respond"] = lambda request: httpx.Response(401)
    bad, good = _creds(KEY, owner="u1"), _creds(OTHER_KEY, owner="u2")

    for _ in range(3):
        await LLMService.generate_chat_reply(
            model="gpt-oss:120b", user_message="q", context_lines=[], credentials=bad, provider="ollama_cloud"
        )
    _, blocked = await LLMService.generate_chat_reply(
        model="gpt-oss:120b", user_message="q", context_lines=[], credentials=bad, provider="ollama_cloud"
    )
    http.handlers["respond"] = lambda request: _chat_ok("fine")
    content, ok = await LLMService.generate_chat_reply(
        model="gpt-oss:120b", user_message="q", context_lines=[], credentials=good, provider="ollama_cloud"
    )

    assert blocked["error_type"] == "provider_circuit_open"
    assert content == "fine" and "error_type" not in ok


@pytest.mark.asyncio
async def test_an_unknown_provider_is_rejected_before_anything_is_sent(http):
    with pytest.raises(UnsupportedModel, match="Unknown provider"):
        await LLMService.generate_chat_reply(
            model="x", user_message="q", context_lines=[], provider="mistral"
        )
    assert http == []
