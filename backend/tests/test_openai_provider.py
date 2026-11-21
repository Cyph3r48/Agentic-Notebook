from __future__ import annotations

from types import SimpleNamespace

import httpx2
import openai
import pytest
from loguru import logger

from app.core.config import settings
from app.services.llm.base import ChatRequest, ProviderCredentials, StreamOutcome, UnsupportedModel
from app.services.llm.openai_provider import OpenAIProvider, OpenAIStreamError
from app.services.llm_service import REFUSAL_TEXT, LLMService

KEY = "sk-openai-test-SENTINEL-1111"
OTHER_KEY = "sk-openai-test-SENTINEL-2222"


def _creds(key=KEY, owner="u1"):
    return ProviderCredentials(api_key=key, source="user", owner=owner)


def _request(**overrides):
    values = dict(
        model="gpt-5.5",
        user_message="What is in my notes?",
        context_lines=["notes.txt#0: violets need light"],
        history=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
        system_prompt=None,
    )
    values.update(overrides)
    return ChatRequest(**values)


# ---------------------------------------------------------------- fakes shaped like the SDK's events


def _delta(text):
    return SimpleNamespace(type="response.output_text.delta", delta=text)


def _refusal(text="no"):
    return SimpleNamespace(type="response.refusal.delta", delta=text)


def _usage(input_tokens=11, output_tokens=7):
    return SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=input_tokens + output_tokens)


def _final(kind="response.completed", *, status="completed", usage="default", reason=None, error=None):
    response = SimpleNamespace(
        status=status,
        usage=_usage() if usage == "default" else usage,
        incomplete_details=SimpleNamespace(reason=reason) if reason else None,
        error=error,
    )
    return SimpleNamespace(type=kind, response=response)


def _completed(**kwargs):
    return _final("response.completed", **kwargs)


class _FakeStream:
    """Async iterator over canned events; raises `error_after` once they run out."""

    def __init__(self, events, error_after=None):
        self._events = list(events)
        self._error_after = error_after

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._events:
            return self._events.pop(0)
        if self._error_after is not None:
            error, self._error_after = self._error_after, None
            raise error
        raise StopAsyncIteration


class _FakeResponses:
    def __init__(self, owner):
        self.owner = owner

    async def create(self, **body):
        self.owner.bodies.append(body)
        if self.owner.create_error is not None:
            raise self.owner.create_error
        return _FakeStream(self.owner.events, self.owner.stream_error)


class _FakeList:
    """models.list(): awaitable and async-iterable, like the SDK's paginator."""

    def __init__(self, owner):
        self.owner = owner

    def __await__(self):
        async def _first():
            if self.owner.list_error is not None:
                raise self.owner.list_error
            return self

        return _first().__await__()

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        if self.owner.list_error is not None:
            raise self.owner.list_error
        for item in self.owner.listing:
            yield item


class _FakeModels:
    def __init__(self, owner):
        self.owner = owner

    def list(self, **kwargs):
        self.owner.list_calls += 1
        return _FakeList(self.owner)


class _FakeOpenAI:
    def __init__(self, *, events=None, models=None):
        self.events = events or []
        self.listing = models or []
        self.bodies: list[dict] = []
        self.create_error = None
        self.stream_error = None
        self.list_error = None
        self.list_calls = 0
        self.responses = _FakeResponses(self)
        self.models = _FakeModels(self)
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        self.closed = True
        return False


def _model(model_id, created=1):
    return SimpleNamespace(id=model_id, created=created)


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    monkeypatch.setattr(LLMService, "_failure_count", {})
    monkeypatch.setattr(LLMService, "_circuit_open_until", {})
    monkeypatch.setattr(OpenAIProvider, "_model_cache", {})
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "OPENAI_DEFAULT_MODEL", "gpt-5.5")
    monkeypatch.setattr(settings, "OPENAI_REASONING_EFFORT", "")
    monkeypatch.setattr(settings, "ALLOW_SERVER_PROVIDER_KEYS", True)


@pytest.fixture
def install(monkeypatch):
    """Make the adapter build a fake client; returns the fake so a test can inspect what it was sent."""

    def _install(fake=None, **kwargs):
        fake = fake or _FakeOpenAI(**kwargs)
        monkeypatch.setattr(OpenAIProvider, "_openai_client", classmethod(lambda cls, **kw: fake))
        return fake

    return _install


async def _collect(request=None, credentials=None, outcome=None):
    return [part async for part in OpenAIProvider.stream(request or _request(), credentials or _creds(), outcome)]


def _http_request():
    return httpx2.Request("POST", "https://api.openai.com/v1/responses")


def _status_error(cls, status, body=None):
    return cls("provider said no", response=httpx2.Response(status, request=_http_request()), body=body)


# ---------------------------------------------------------------- streaming


@pytest.mark.asyncio
async def test_stream_yields_text_and_records_usage_and_stop_reason(install):
    install(events=[_delta("Hello "), _delta("there"), _completed()])
    outcome = StreamOutcome()

    parts = await _collect(outcome=outcome)

    assert parts == ["Hello ", "there"]
    assert (outcome.input_tokens, outcome.output_tokens) == (11, 7)
    assert outcome.stop_reason == "completed" and outcome.truncated is False and outcome.error_type is None


@pytest.mark.asyncio
async def test_every_request_sends_store_false_and_no_sampling_or_linking_parameters(install):
    fake = install(events=[_delta("x"), _completed()])

    await _collect()

    body = fake.bodies[0]
    assert body["store"] is False  # the API default would keep the response for at least 30 days
    assert body["stream"] is True
    for forbidden in ("temperature", "top_p", "previous_response_id", "user", "metadata", "reasoning"):
        assert forbidden not in body


@pytest.mark.asyncio
async def test_request_carries_system_prompt_history_and_context(install):
    fake = install(events=[_delta("x"), _completed()])

    await _collect(_request(system_prompt="Answer in one sentence."))

    body = fake.bodies[0]
    assert body["model"] == "gpt-5.5"
    assert body["instructions"] == "Answer in one sentence."
    assert body["max_output_tokens"] == settings.OPENAI_MAX_OUTPUT_TOKENS
    roles = [turn["role"] for turn in body["input"]]
    assert roles == ["user", "assistant", "user"]
    assert body["input"][0]["content"] == "hi" and body["input"][1]["content"] == "hello"
    assert "What is in my notes?" in body["input"][-1]["content"]
    assert "violets need light" in body["input"][-1]["content"]


@pytest.mark.asyncio
async def test_default_system_prompt_is_used_when_none_is_set(install):
    fake = install(events=[_delta("x"), _completed()])

    await _collect(_request(system_prompt="  "))

    assert fake.bodies[0]["instructions"] == "You are a concise assistant. Use provided context when relevant."


@pytest.mark.asyncio
async def test_reasoning_effort_is_sent_only_when_configured(monkeypatch, install):
    fake = install(events=[_delta("x"), _completed()])
    monkeypatch.setattr(settings, "OPENAI_REASONING_EFFORT", "low")

    await _collect()

    assert fake.bodies[0]["reasoning"] == {"effort": "low"}


@pytest.mark.asyncio
async def test_an_incomplete_response_at_the_token_limit_is_marked_truncated(install):
    install(events=[_delta("partial"), _final("response.incomplete", status="incomplete", reason="max_output_tokens")])
    outcome = StreamOutcome()

    parts = await _collect(outcome=outcome)

    assert parts == ["partial"]
    assert outcome.truncated is True and outcome.stop_reason == "max_output_tokens"


@pytest.mark.asyncio
async def test_a_refusal_is_reported_and_canned_text_is_shown_when_nothing_else_was(install):
    install(events=[_refusal("I can't help with that."), _completed()])
    outcome = StreamOutcome()

    parts = await _collect(outcome=outcome)

    assert parts == [REFUSAL_TEXT]
    assert outcome.error_type == "provider_refusal" and outcome.refusal_category is None


@pytest.mark.asyncio
async def test_a_content_filter_stop_is_a_refusal_with_its_category(install):
    install(events=[_final("response.incomplete", status="incomplete", reason="content_filter")])
    outcome = StreamOutcome()

    parts = await _collect(outcome=outcome)

    assert parts == [REFUSAL_TEXT]
    assert outcome.error_type == "provider_refusal" and outcome.refusal_category == "content_filter"


@pytest.mark.asyncio
async def test_missing_usage_is_unknown_not_zero(install):
    install(events=[_delta("x"), _completed(usage=None)])
    outcome = StreamOutcome()

    await _collect(outcome=outcome)

    assert outcome.input_tokens is None and outcome.output_tokens is None


@pytest.mark.asyncio
async def test_a_failed_response_raises_with_only_the_error_code(install):
    error = SimpleNamespace(code="insufficient_quota", message="You exceeded your current quota for key sk-leak")
    install(events=[_delta("x"), _final("response.failed", status="failed", error=error)])

    with pytest.raises(OpenAIStreamError) as caught:
        await _collect()

    assert "sk-leak" not in str(caught.value) and "insufficient_quota" in str(caught.value)
    assert OpenAIProvider.classify_error(caught.value) == "provider_quota_exceeded"


@pytest.mark.asyncio
async def test_an_error_event_raises(install):
    install(events=[SimpleNamespace(type="error", code="rate_limit_exceeded", message="slow down")])

    with pytest.raises(OpenAIStreamError) as caught:
        await _collect()

    assert OpenAIProvider.classify_error(caught.value) == "provider_rate_limited"


@pytest.mark.asyncio
async def test_a_stream_that_ends_without_a_final_event_is_an_error_not_an_empty_answer(install):
    install(events=[_delta("cut off")])

    with pytest.raises(RuntimeError, match="without a final event"):
        await _collect()


@pytest.mark.asyncio
async def test_the_client_is_closed_after_a_stream(install):
    fake = install(events=[_delta("x"), _completed()])

    await _collect()

    assert fake.closed is True


@pytest.mark.asyncio
async def test_the_client_is_closed_when_the_stream_fails_midway(install):
    fake = install(events=[_delta("x")])
    fake.stream_error = _status_error(openai.APIStatusError, 500)

    with pytest.raises(openai.APIStatusError):
        await _collect()

    assert fake.closed is True


# ---------------------------------------------------------------- generate


@pytest.mark.asyncio
async def test_generate_returns_text_and_normalized_usage(install):
    install(events=[_delta("Hello "), _delta("world"), _completed()])

    result = await OpenAIProvider.generate(_request(), _creds())

    assert result.text == "Hello world"
    assert result.usage == {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}


@pytest.mark.asyncio
async def test_generate_marks_truncation(install):
    install(events=[_delta("part"), _final("response.incomplete", status="incomplete", reason="max_output_tokens")])

    result = await OpenAIProvider.generate(_request(), _creds())

    assert result.usage["truncated"] is True


@pytest.mark.asyncio
async def test_generate_reports_a_refusal_with_canned_text(install):
    install(events=[_refusal(), _completed()])

    result = await OpenAIProvider.generate(_request(), _creds())

    assert result.text == REFUSAL_TEXT and result.usage["error_type"] == "provider_refusal"


@pytest.mark.asyncio
async def test_generate_with_no_text_and_no_refusal_is_an_error(install):
    install(events=[_completed()])

    with pytest.raises(RuntimeError, match="Empty OpenAI response"):
        await OpenAIProvider.generate(_request(), _creds())


# ---------------------------------------------------------------- through the LLM service


@pytest.mark.asyncio
async def test_service_reports_openai_metadata_like_the_other_providers(install):
    install(events=[_delta("answer"), _completed()])

    content, metadata = await LLMService.generate_chat_reply(
        model="gpt-5.5", user_message="q", context_lines=[], credentials=_creds()
    )

    assert content == "answer"
    assert metadata["provider"] == "openai" and metadata["model"] == "gpt-5.5"
    assert (metadata["input_tokens"], metadata["output_tokens"], metadata["total_tokens"]) == (11, 7, 18)


@pytest.mark.asyncio
async def test_service_falls_back_to_the_excerpt_with_a_specific_error_type(install):
    fake = install(events=[])
    fake.create_error = _status_error(openai.AuthenticationError, 401)

    content, metadata = await LLMService.generate_chat_reply(
        model="gpt-5.5", user_message="q", context_lines=["notes.txt#0: violets"], credentials=_creds()
    )

    assert "violets" in content and metadata["error_type"] == "provider_auth_error"


@pytest.mark.asyncio
async def test_service_streams_and_records_the_error_type_on_failure(install):
    fake = install(events=[])
    fake.create_error = _status_error(openai.RateLimitError, 429, body={"code": "insufficient_quota"})
    outcome = StreamOutcome()

    with pytest.raises(openai.RateLimitError):
        async for _ in LLMService.stream_chat_reply(
            model="gpt-5.5", user_message="q", context_lines=[], outcome=outcome, credentials=_creds()
        ):
            pass

    assert outcome.error_type == "provider_quota_exceeded"


@pytest.mark.asyncio
async def test_one_users_failures_do_not_open_another_users_circuit(install):
    fake = install(events=[_delta("fine"), _completed()])
    fake.create_error = _status_error(openai.AuthenticationError, 401)
    bad, good = _creds(KEY, "u1"), _creds(OTHER_KEY, "u2")

    for _ in range(3):
        await LLMService.generate_chat_reply(model="gpt-5.5", user_message="q", context_lines=[], credentials=bad)
    _, blocked = await LLMService.generate_chat_reply(model="gpt-5.5", user_message="q", context_lines=[], credentials=bad)

    fake.create_error = None
    content, ok = await LLMService.generate_chat_reply(model="gpt-5.5", user_message="q", context_lines=[], credentials=good)

    assert blocked["error_type"] == "provider_circuit_open"
    assert content == "fine" and "error_type" not in ok


# ---------------------------------------------------------------- models


@pytest.mark.asyncio
async def test_model_list_keeps_chat_models_newest_first(install):
    install(
        models=[
            _model("text-embedding-3-large", 9),
            _model("gpt-5.4", 100),
            _model("whisper-1", 50),
            _model("gpt-5.5", 300),
            _model("gpt-image-1", 400),
            _model("o3", 200),
            _model("gpt-4o-realtime-preview", 500),
            _model("gpt-4o-mini-tts", 600),
            _model("omni-moderation-latest", 700),
            _model("gpt-4o-search-preview", 800),
            _model("davinci-002", 1),
        ]
    )

    models = await OpenAIProvider.list_models(_creds())

    assert [m.id for m in models] == ["gpt-5.5", "o3", "gpt-5.4"]


@pytest.mark.asyncio
async def test_model_list_is_empty_without_a_key(install):
    fake = install(models=[_model("gpt-5.5")])

    assert await OpenAIProvider.list_models(None) == []
    assert fake.list_calls == 0


@pytest.mark.asyncio
async def test_model_list_is_cached_per_credential_and_never_shared(monkeypatch):
    calls = []

    def factory(cls, credentials=None, **kwargs):
        calls.append(credentials.api_key)
        listing = [_model("gpt-5.5")] if credentials.api_key == KEY else [_model("gpt-5.4")]
        return _FakeOpenAI(models=listing)

    monkeypatch.setattr(OpenAIProvider, "_openai_client", classmethod(factory))

    first = await OpenAIProvider.list_models(_creds(KEY))
    again = await OpenAIProvider.list_models(_creds(KEY))
    other = await OpenAIProvider.list_models(_creds(OTHER_KEY))

    assert [m.id for m in first] == [m.id for m in again] == ["gpt-5.5"]
    assert [m.id for m in other] == ["gpt-5.4"]
    assert calls == [KEY, OTHER_KEY]  # the repeat for the first key came from the cache


@pytest.mark.asyncio
async def test_model_list_falls_back_to_the_default_model_when_listing_fails(install, monkeypatch):
    fake = install()
    fake.list_error = _status_error(openai.AuthenticationError, 401)
    monkeypatch.setattr(settings, "OPENAI_DEFAULT_MODEL", "gpt-5.4")

    models = await OpenAIProvider.list_models(_creds())

    assert [m.id for m in models] == ["gpt-5.4"]


@pytest.mark.asyncio
async def test_resolve_model_accepts_listed_and_default_ids_and_rejects_others(install):
    install(models=[_model("gpt-5.4", 5)])

    assert await OpenAIProvider.resolve_model("gpt-5.4", _creds()) == "gpt-5.4"
    assert await OpenAIProvider.resolve_model(" gpt-5.5 ", _creds()) == "gpt-5.5"  # the configured default
    with pytest.raises(UnsupportedModel, match="Unsupported OpenAI model"):
        await OpenAIProvider.resolve_model("gpt-9-nope", _creds())


@pytest.mark.asyncio
async def test_resolve_model_without_a_key_says_to_add_one(install):
    install(models=[_model("gpt-5.5")])

    with pytest.raises(UnsupportedModel, match="Add one in Settings"):
        await OpenAIProvider.resolve_model("gpt-5.5", None)


# ---------------------------------------------------------------- test button


@pytest.mark.asyncio
async def test_connection_ok(install):
    install(models=[_model("gpt-5.5")])

    assert await OpenAIProvider.test_connection(_creds()) == {"ok": True, "error_type": None, "detail": "Connected."}


@pytest.mark.asyncio
async def test_connection_without_a_key(install):
    install()

    result = await OpenAIProvider.test_connection(None)

    assert result["ok"] is False and result["error_type"] == "not_configured"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected", "detail"),
    [
        (_status_error(openai.AuthenticationError, 401), "provider_auth_error", "The provider rejected the key."),
        (_status_error(openai.PermissionDeniedError, 403), "provider_auth_error", "The provider rejected the key."),
        (
            _status_error(openai.RateLimitError, 429, body={"code": "insufficient_quota"}),
            "provider_quota_exceeded",
            "The account has no remaining quota or credit.",
        ),
        (
            _status_error(openai.RateLimitError, 429, body={"code": "rate_limit_exceeded"}),
            "provider_rate_limited",
            "The provider is rate limiting this key.",
        ),
        (openai.APITimeoutError(request=_http_request()), "provider_timeout", "The provider did not answer in time."),
        (openai.APIConnectionError(request=_http_request()), "provider_error", "Could not reach the provider."),
        (_status_error(openai.InternalServerError, 500), "provider_http_error", "The provider returned an error."),
    ],
)
async def test_connection_failures_have_fixed_safe_details(install, error, expected, detail):
    fake = install()
    fake.list_error = error

    result = await OpenAIProvider.test_connection(_creds())

    assert result == {"ok": False, "error_type": expected, "detail": detail}
    assert KEY not in repr(result) and "provider said no" not in repr(result)


@pytest.mark.asyncio
async def test_a_failed_test_logs_the_error_type_and_not_the_key(install):
    fake = install()
    fake.list_error = _status_error(openai.AuthenticationError, 401)
    lines: list[str] = []
    sink = logger.add(lambda message: lines.append(str(message)), level="WARNING")
    try:
        await OpenAIProvider.test_connection(_creds())
    finally:
        logger.remove(sink)

    assert any("provider_auth_error" in line for line in lines)
    assert not any(KEY in line or "provider said no" in line for line in lines)


# ---------------------------------------------------------------- credentials and the client


def test_the_server_wide_key_is_used_only_when_allowed(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-server-wide-key-3333")

    assert OpenAIProvider.server_credentials().api_key == "sk-server-wide-key-3333"
    monkeypatch.setattr(settings, "ALLOW_SERVER_PROVIDER_KEYS", False)
    assert OpenAIProvider.server_credentials() is None


@pytest.mark.asyncio
async def test_the_server_key_is_never_picked_up_behind_the_flags_back(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-server-wide-key-3333")
    monkeypatch.setattr(settings, "ALLOW_SERVER_PROVIDER_KEYS", False)

    assert (await OpenAIProvider.health(None)) == {"healthy": False}
    with pytest.raises(RuntimeError, match="No OpenAI API key"):
        OpenAIProvider._openai_client(credentials=None)


def test_the_client_uses_the_callers_key_and_limits():
    client = OpenAIProvider._openai_client(credentials=_creds(KEY), timeout=5.0, max_retries=0)

    assert client.api_key == KEY
    assert client.max_retries == 0


def test_routing_never_sends_an_ollama_tag_to_openai():
    assert OpenAIProvider.owns("gpt-5.5") and OpenAIProvider.owns("O3") and OpenAIProvider.owns("chatgpt-4o-latest")
    assert not OpenAIProvider.owns("gpt-oss:20b")
    assert not OpenAIProvider.owns("llama3.2:3b") and not OpenAIProvider.owns("claude-sonnet-5-5")
