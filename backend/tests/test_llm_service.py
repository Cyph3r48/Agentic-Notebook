from __future__ import annotations

import json
import re
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from app.core.config import settings
from app.services import llm_service as llm_module
from app.services.llm_service import REFUSAL_TEXT, LLMService, ProviderCredentials, StreamOutcome


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    monkeypatch.setattr(LLMService, "_failure_count", {"ollama": 0, "anthropic": 0})
    monkeypatch.setattr(LLMService, "_circuit_open_until", {"ollama": None, "anthropic": None})
    monkeypatch.setattr(LLMService, "_model_cache", {})
    monkeypatch.setattr(LLMService, "_effort_ok", {})
    monkeypatch.setattr(llm_module, "OLLAMA_RETRY_DELAY_SECONDS", 0)
    monkeypatch.setattr(settings, "CLAUDE_API_KEY", "")


def _row(role, content, **metadata):
    return SimpleNamespace(role=role, content=content, metadata_json=metadata)


# ---------------------------------------------------------------- history


def test_history_skips_errored_assistant_rows_and_empty_content():
    rows = [
        _row("user", "q1"),
        _row("assistant", "canned fallback", error_type="provider_error"),
        _row("assistant", "a1"),
        _row("user", "   "),
        _row("system", "ignored"),
        _row("user", "q2"),
    ]
    assert LLMService.history_from_messages(rows, max_messages=10, max_chars=1000) == [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
    ]


def test_history_keeps_only_newest_messages_and_starts_with_user():
    rows = [_row("user", "q1"), _row("assistant", "a1"), _row("user", "q2"), _row("assistant", "a2")]
    # The window cuts to [a1, q2, a2]; the leading assistant turn is dropped so the list starts with a user turn.
    assert LLMService.history_from_messages(rows, max_messages=3, max_chars=1000) == [
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
    ]


def test_history_drops_oldest_turns_until_it_fits_the_character_budget():
    rows = [_row("user", "x" * 50), _row("assistant", "y" * 50), _row("user", "z" * 10), _row("assistant", "w" * 10)]
    history = LLMService.history_from_messages(rows, max_messages=10, max_chars=30)
    assert history == [{"role": "user", "content": "z" * 10}, {"role": "assistant", "content": "w" * 10}]


def test_history_of_nothing_is_empty():
    assert LLMService.history_from_messages([], max_messages=10, max_chars=100) == []
    assert LLMService.history_from_messages([_row("user", "q")], max_messages=0, max_chars=100) == []


# ---------------------------------------------------------------- model ids


def test_configured_claude_ids_have_no_dots_or_date_suffixes():
    for entry in LLMService.configured_claude_models():
        model_id = entry["id"]
        assert "." not in model_id
        assert not re.search(r"\d{8}", model_id)
        assert re.fullmatch(r"claude-[a-z]+(-\d+)+", model_id), model_id
    assert settings.CLAUDE_DEFAULT_MODEL in {entry["id"] for entry in LLMService.configured_claude_models()}


def test_normalize_claude_model_maps_dotted_ids_only():
    assert LLMService.normalize_claude_model("claude-sonnet-4.6") == "claude-sonnet-4-6"
    assert LLMService.normalize_claude_model(" claude-opus-5.5 ") == "claude-opus-5-5"
    assert LLMService.normalize_claude_model("claude-sonnet-5-5") == "claude-sonnet-5-5"


def _effort_caps(supported=True, **levels):
    """Capabilities as the Models API reports them; every level is supported unless overridden."""
    flags = {"low": True, "medium": True, "high": True, "max": True, "xhigh": True, **levels}
    return SimpleNamespace(
        effort=SimpleNamespace(supported=supported, **{k: SimpleNamespace(supported=v) for k, v in flags.items()})
    )


class _FakeModels:
    def __init__(self, ids, fail=False, capabilities=None):
        self.ids = ids
        self.fail = fail
        self.capabilities = capabilities or {}
        self.list_calls = 0

    def list(self):
        self.list_calls += 1
        if self.fail:
            raise RuntimeError("models api down")

        async def gen():
            for model_id in self.ids:
                yield SimpleNamespace(
                    id=model_id,
                    display_name=model_id.upper(),
                    capabilities=self.capabilities.get(model_id),
                )

        return gen()


class _FakeAnthropic:
    def __init__(self, *, messages=None, models=None):
        self.messages = messages
        self.models = models if models is not None else _FakeModels(["claude-sonnet-5-5", "claude-sonnet-4-6"])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


def _use_fake_anthropic(monkeypatch, fake):
    monkeypatch.setattr(LLMService, "_anthropic_client", classmethod(lambda cls, **kwargs: fake))
    monkeypatch.setattr(settings, "CLAUDE_API_KEY", "sk-test")
    return fake


@pytest.mark.asyncio
async def test_model_catalog_without_a_key_uses_configured_ids():
    catalog = await LLMService.claude_model_catalog()
    assert [entry["id"] for entry in catalog] == [m["id"] for m in LLMService.configured_claude_models()]
    assert await LLMService.allowed_claude_models() == {entry["id"] for entry in catalog}


@pytest.mark.asyncio
async def test_model_catalog_uses_the_models_api_and_caches_it(monkeypatch):
    models = _FakeModels(["claude-sonnet-5-5", "claude-sonnet-4-6", "not-claude"])
    _use_fake_anthropic(monkeypatch, _FakeAnthropic(models=models))

    first = await LLMService.claude_model_catalog()
    second = await LLMService.claude_model_catalog()

    assert [entry["id"] for entry in first] == ["claude-sonnet-5-5", "claude-sonnet-4-6"]
    assert first[0]["name"] == "CLAUDE-SONNET-5-5"
    assert second == first
    assert models.list_calls == 1
    # Configured IDs stay allowed even when the API list omits them.
    allowed = await LLMService.allowed_claude_models()
    assert {"claude-sonnet-4-6", "claude-opus-5-5", "claude-haiku-5-5"} <= allowed


@pytest.mark.asyncio
async def test_model_catalog_falls_back_to_configured_ids_when_the_api_fails(monkeypatch):
    _use_fake_anthropic(monkeypatch, _FakeAnthropic(models=_FakeModels([], fail=True)))
    catalog = await LLMService.claude_model_catalog()
    assert [entry["id"] for entry in catalog] == [m["id"] for m in LLMService.configured_claude_models()]


# ---------------------------------------------------------------- Ollama


def _install_ollama(monkeypatch, handler):
    calls = []

    def respond(request):
        calls.append(request)
        return handler(request, len(calls))

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        LLMService,
        "_ollama_client",
        classmethod(lambda cls, credentials=None: httpx.AsyncClient(transport=transport, timeout=cls._ollama_timeout())),
    )
    return calls


def _ollama_ok(text="hello", prompt_tokens=7, completion_tokens=3):
    return httpx.Response(
        200,
        json={"message": {"content": text}, "prompt_eval_count": prompt_tokens, "eval_count": completion_tokens},
    )


def test_ollama_timeout_is_not_two_seconds():
    timeout = LLMService._ollama_timeout()
    assert timeout.connect == settings.OLLAMA_CONNECT_TIMEOUT_SECONDS == 5.0
    assert timeout.read == settings.OLLAMA_READ_TIMEOUT_SECONDS == 120.0


@pytest.mark.asyncio
async def test_ollama_request_carries_system_prompt_history_and_context(monkeypatch):
    calls = _install_ollama(monkeypatch, lambda request, n: _ollama_ok())
    history = [{"role": "user", "content": "first question"}, {"role": "assistant", "content": "first answer"}]

    text, metadata = await LLMService.generate_chat_reply(
        model="llama3.2",
        user_message="and the second?",
        context_lines=["doc.txt#0: snippet"],
        history=history,
        system_prompt="Answer in French.",
    )

    assert text == "hello"
    assert metadata["input_tokens"] == 7 and metadata["output_tokens"] == 3 and metadata["total_tokens"] == 10
    body = json.loads(calls[0].content)
    assert calls[0].url.path == "/api/chat"
    assert body["stream"] is False and body["model"] == "llama3.2"
    assert [m["role"] for m in body["messages"]] == ["system", "user", "assistant", "user"]
    assert body["messages"][0]["content"] == "Answer in French."
    assert body["messages"][1]["content"] == "first question"
    assert "and the second?" in body["messages"][-1]["content"]
    assert "doc.txt#0: snippet" in body["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_ollama_uses_the_default_system_prompt_when_none_is_set(monkeypatch):
    calls = _install_ollama(monkeypatch, lambda request, n: _ollama_ok())
    await LLMService.generate_chat_reply(model="llama3.2", user_message="hi", context_lines=[])
    assert json.loads(calls[0].content)["messages"][0]["content"] == llm_module.DEFAULT_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_ollama_retries_a_server_error_once_then_succeeds(monkeypatch):
    calls = _install_ollama(
        monkeypatch, lambda request, n: httpx.Response(503) if n == 1 else _ollama_ok("recovered")
    )
    text, metadata = await LLMService.generate_chat_reply(model="llama3.2", user_message="hi", context_lines=[])
    assert text == "recovered"
    assert len(calls) == 2
    assert "error_type" not in metadata


@pytest.mark.asyncio
async def test_ollama_does_not_retry_client_errors(monkeypatch):
    calls = _install_ollama(monkeypatch, lambda request, n: httpx.Response(404))
    text, metadata = await LLMService.generate_chat_reply(model="nope", user_message="hi", context_lines=[])
    assert len(calls) == 1
    assert metadata["error_type"] == "provider_http_error"
    assert text == llm_module.NO_CONTEXT_TEXT


@pytest.mark.asyncio
async def test_ollama_retries_a_connection_error_once_then_reports_it(monkeypatch):
    def refuse(request, n):
        raise httpx.ConnectError("connection refused", request=request)

    calls = _install_ollama(monkeypatch, refuse)
    _, metadata = await LLMService.generate_chat_reply(model="llama3.2", user_message="hi", context_lines=[])
    assert len(calls) == 2
    assert metadata["error_type"] == "provider_error"
    assert LLMService._failure_count["ollama"] == 1


@pytest.mark.asyncio
async def test_ollama_read_timeout_is_reported_and_not_retried(monkeypatch):
    def slow(request, n):
        raise httpx.ReadTimeout("model still loading", request=request)

    calls = _install_ollama(monkeypatch, slow)
    _, metadata = await LLMService.generate_chat_reply(model="llama3.2", user_message="hi", context_lines=[])
    assert len(calls) == 1
    assert metadata["error_type"] == "provider_timeout"


@pytest.mark.asyncio
async def test_ollama_stream_yields_deltas_sends_history_and_records_usage(monkeypatch):
    lines = [
        json.dumps({"message": {"content": "Hel"}, "done": False}),
        json.dumps({"message": {"content": "lo"}, "done": False}),
        json.dumps({"message": {"content": ""}, "done": True, "done_reason": "stop", "prompt_eval_count": 9, "eval_count": 4}),
    ]
    calls = _install_ollama(monkeypatch, lambda request, n: httpx.Response(200, content=("\n".join(lines) + "\n").encode()))
    outcome = StreamOutcome()

    parts = [
        part
        async for part in LLMService.stream_chat_reply(
            model="llama3.2",
            user_message="hi",
            context_lines=[],
            history=[{"role": "user", "content": "earlier"}],
            outcome=outcome,
        )
    ]

    assert parts == ["Hel", "lo"]
    assert json.loads(calls[0].content)["stream"] is True
    assert json.loads(calls[0].content)["messages"][1]["content"] == "earlier"
    assert (outcome.stop_reason, outcome.input_tokens, outcome.output_tokens) == ("stop", 9, 4)
    assert LLMService._failure_count["ollama"] == 0


# ---------------------------------------------------------------- Anthropic


class _FakeStream:
    def __init__(self, message, deltas=()):
        self._message = message
        self._deltas = deltas
        self.text_stream = self._iterate()

    async def _iterate(self):
        for delta in self._deltas:
            yield delta

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def get_final_message(self):
        return self._message


class _FakeMessages:
    def __init__(self, message=None, deltas=(), error=None):
        self.message = message
        self.deltas = deltas
        self.error = error
        self.calls = []

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return _FakeStream(self.message, self.deltas)


def _message(text="Paris.", stop_reason="end_turn", input_tokens=10, output_tokens=5, category=None):
    content = [SimpleNamespace(type="thinking", text=""), SimpleNamespace(type="text", text=text)]
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        stop_details=SimpleNamespace(category=category) if stop_reason == "refusal" else None,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


class _AuthError(anthropic.AuthenticationError):
    def __init__(self):  # the SDK constructor needs a live response object
        Exception.__init__(self, "invalid x-api-key")


class _TimeoutError(anthropic.APITimeoutError):
    def __init__(self):
        Exception.__init__(self, "Request timed out.")


@pytest.mark.asyncio
async def test_anthropic_request_shape(monkeypatch):
    messages = _FakeMessages(_message())
    _use_fake_anthropic(monkeypatch, _FakeAnthropic(messages=messages))
    history = [{"role": "user", "content": "capital of Spain?"}, {"role": "assistant", "content": "Madrid."}]

    text, metadata = await LLMService.generate_chat_reply(
        model="claude-sonnet-4.6",  # a legacy dotted ID stored on an old conversation
        user_message="and France?",
        context_lines=[],
        history=history,
        system_prompt="Be terse.",
    )

    request = messages.calls[0]
    assert request["model"] == "claude-sonnet-4-6"
    assert request["max_tokens"] == settings.CLAUDE_MAX_OUTPUT_TOKENS
    assert request["output_config"] == {"effort": "medium"}
    assert request["system"] == "Be terse."
    assert request["messages"][:2] == history
    assert request["messages"][-1]["role"] == "user" and "and France?" in request["messages"][-1]["content"]
    # Sampling controls, a thinking switch and assistant prefill are rejected by the current models.
    for forbidden in ("temperature", "top_p", "top_k", "thinking", "tool_choice"):
        assert forbidden not in request

    assert text == "Paris."
    assert metadata["provider"] == "anthropic" and metadata["model"] == "claude-sonnet-4.6"
    assert (metadata["input_tokens"], metadata["output_tokens"], metadata["total_tokens"]) == (10, 5, 15)


@pytest.mark.asyncio
async def test_effort_is_only_sent_to_models_that_accept_it(monkeypatch):
    messages = _FakeMessages(_message())
    models = _FakeModels(
        ["claude-sonnet-5-5", "claude-haiku-4-5"],
        capabilities={"claude-sonnet-5-5": _effort_caps(), "claude-haiku-4-5": _effort_caps(supported=False)},
    )
    _use_fake_anthropic(monkeypatch, _FakeAnthropic(messages=messages, models=models))

    await LLMService.generate_chat_reply(model="claude-sonnet-5-5", user_message="x", context_lines=[])
    await LLMService.generate_chat_reply(model="claude-haiku-4-5", user_message="x", context_lines=[])

    assert messages.calls[0]["output_config"] == {"effort": "medium"}
    assert "output_config" not in messages.calls[1]


@pytest.mark.asyncio
async def test_effort_level_the_model_does_not_support_is_not_sent(monkeypatch):
    monkeypatch.setattr(settings, "CLAUDE_EFFORT", "xhigh")
    messages = _FakeMessages(_message())
    models = _FakeModels(
        ["claude-opus-5-5", "claude-sonnet-4-6"],
        capabilities={"claude-opus-5-5": _effort_caps(), "claude-sonnet-4-6": _effort_caps(xhigh=False)},
    )
    _use_fake_anthropic(monkeypatch, _FakeAnthropic(messages=messages, models=models))

    await LLMService.generate_chat_reply(model="claude-opus-5-5", user_message="x", context_lines=[])
    await LLMService.generate_chat_reply(model="claude-sonnet-4-6", user_message="x", context_lines=[])

    assert messages.calls[0]["output_config"] == {"effort": "xhigh"}
    assert "output_config" not in messages.calls[1]


@pytest.mark.asyncio
async def test_streaming_also_skips_effort_for_models_that_reject_it(monkeypatch):
    messages = _FakeMessages(_message(), deltas=("ok",))
    models = _FakeModels(["claude-haiku-4-5"], capabilities={"claude-haiku-4-5": _effort_caps(supported=False)})
    _use_fake_anthropic(monkeypatch, _FakeAnthropic(messages=messages, models=models))

    parts = [p async for p in LLMService.stream_chat_reply(model="claude-haiku-4-5", user_message="x", context_lines=[])]

    assert parts == ["ok"]
    assert "output_config" not in messages.calls[0]


@pytest.mark.asyncio
async def test_anthropic_refusal_is_reported_without_tripping_the_circuit(monkeypatch):
    _use_fake_anthropic(monkeypatch, _FakeAnthropic(messages=_FakeMessages(_message(text="", stop_reason="refusal", category="cyber"))))
    text, metadata = await LLMService.generate_chat_reply(model="claude-sonnet-5-5", user_message="x", context_lines=["a#0: b"])
    assert text == REFUSAL_TEXT
    assert metadata["error_type"] == "provider_refusal" and metadata["refusal_category"] == "cyber"
    assert LLMService._failure_count["anthropic"] == 0


@pytest.mark.asyncio
async def test_anthropic_truncated_answer_is_flagged(monkeypatch):
    _use_fake_anthropic(monkeypatch, _FakeAnthropic(messages=_FakeMessages(_message(text="cut off", stop_reason="max_tokens"))))
    text, metadata = await LLMService.generate_chat_reply(model="claude-sonnet-5-5", user_message="x", context_lines=[])
    assert text == "cut off" and metadata["truncated"] is True


@pytest.mark.asyncio
async def test_anthropic_auth_error_is_classified_and_made_one_call(monkeypatch):
    messages = _FakeMessages(error=_AuthError())
    _use_fake_anthropic(monkeypatch, _FakeAnthropic(messages=messages))
    _, metadata = await LLMService.generate_chat_reply(model="claude-sonnet-5-5", user_message="x", context_lines=[])
    assert len(messages.calls) == 1
    assert metadata["error_type"] == "provider_auth_error"
    assert LLMService._failure_count["anthropic"] == 1


@pytest.mark.asyncio
async def test_anthropic_timeout_is_classified(monkeypatch):
    _use_fake_anthropic(monkeypatch, _FakeAnthropic(messages=_FakeMessages(error=_TimeoutError())))
    _, metadata = await LLMService.generate_chat_reply(model="claude-sonnet-5-5", user_message="x", context_lines=[])
    assert metadata["error_type"] == "provider_timeout"


@pytest.mark.asyncio
async def test_missing_claude_key_falls_back_with_a_provider_error():
    text, metadata = await LLMService.generate_chat_reply(model="claude-sonnet-5-5", user_message="x", context_lines=["a#0: b"])
    assert text.startswith("I found relevant context")
    assert metadata["error_type"] == "provider_error"


@pytest.mark.asyncio
async def test_circuit_opens_after_repeated_failures_and_skips_the_provider(monkeypatch):
    messages = _FakeMessages(error=_AuthError())
    _use_fake_anthropic(monkeypatch, _FakeAnthropic(messages=messages))
    for _ in range(3):
        await LLMService.generate_chat_reply(model="claude-sonnet-5-5", user_message="x", context_lines=[])
    _, metadata = await LLMService.generate_chat_reply(model="claude-sonnet-5-5", user_message="x", context_lines=[])
    assert metadata["error_type"] == "provider_circuit_open"
    assert len(messages.calls) == 3


@pytest.mark.asyncio
async def test_anthropic_stream_yields_text_and_fills_the_outcome(monkeypatch):
    messages = _FakeMessages(_message(text="Hello there", input_tokens=21, output_tokens=8), deltas=("Hello ", "there"))
    _use_fake_anthropic(monkeypatch, _FakeAnthropic(messages=messages))
    outcome = StreamOutcome()

    parts = [
        part
        async for part in LLMService.stream_chat_reply(
            model="claude-sonnet-5-5",
            user_message="hi",
            context_lines=[],
            history=[{"role": "user", "content": "earlier"}],
            outcome=outcome,
        )
    ]

    assert parts == ["Hello ", "there"]
    assert (outcome.stop_reason, outcome.input_tokens, outcome.output_tokens) == ("end_turn", 21, 8)
    assert outcome.error_type is None and outcome.truncated is False
    assert messages.calls[0]["messages"][0] == {"role": "user", "content": "earlier"}


@pytest.mark.asyncio
async def test_anthropic_stream_refusal_without_text_yields_the_refusal_message(monkeypatch):
    messages = _FakeMessages(_message(text="", stop_reason="refusal", category="bio"))
    _use_fake_anthropic(monkeypatch, _FakeAnthropic(messages=messages))
    outcome = StreamOutcome()

    parts = [p async for p in LLMService.stream_chat_reply(model="claude-sonnet-5-5", user_message="x", context_lines=[], outcome=outcome)]

    assert parts == [REFUSAL_TEXT]
    assert outcome.error_type == "provider_refusal" and outcome.refusal_category == "bio"
    assert LLMService._failure_count["anthropic"] == 0


@pytest.mark.asyncio
async def test_stream_failure_records_the_error_type_and_reraises(monkeypatch):
    _use_fake_anthropic(monkeypatch, _FakeAnthropic(messages=_FakeMessages(error=_AuthError())))
    outcome = StreamOutcome()

    with pytest.raises(anthropic.AuthenticationError):
        async for _ in LLMService.stream_chat_reply(model="claude-sonnet-5-5", user_message="x", context_lines=[], outcome=outcome):
            pass

    assert outcome.error_type == "provider_auth_error"
    assert LLMService._failure_count["anthropic"] == 1


# ---------------------------------------------------------------- model listing


@pytest.mark.asyncio
async def test_list_models_includes_names_for_both_providers(monkeypatch):
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"models": [{"name": "llama3.2:3b"}]}))
    monkeypatch.setattr(llm_module.httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport))

    models = await LLMService.list_models()

    assert models["ollama"] == [{"id": "llama3.2:3b", "name": "llama3.2:3b", "provider": "ollama"}]
    assert {m["provider"] for m in models["anthropic"]} == {"anthropic"}
    assert all(m["name"] for m in models["anthropic"])


# ---------------------------------------------------------------- per-user credentials


def _user_creds(key=None, base_url=None, owner="u1"):
    return ProviderCredentials(api_key=key, base_url=base_url, source="user", owner=owner)


def test_anthropic_client_prefers_the_users_key_over_the_server_key(monkeypatch):
    monkeypatch.setattr(settings, "CLAUDE_API_KEY", "sk-server-key-2222")
    assert LLMService._anthropic_client(credentials=_user_creds("sk-user-key-1111")).api_key == "sk-user-key-1111"
    assert LLMService._anthropic_client().api_key == "sk-server-key-2222"


def test_anthropic_client_without_any_key_fails_clearly():
    with pytest.raises(RuntimeError, match="No Claude API key"):
        LLMService._anthropic_client()


@pytest.mark.asyncio
async def test_the_users_credentials_reach_the_client_for_the_catalog_and_the_call(monkeypatch):
    seen = []
    fake = _FakeAnthropic(messages=_FakeMessages(_message()))

    def factory(cls, *, credentials=None, **kwargs):
        seen.append(credentials)
        return fake

    monkeypatch.setattr(LLMService, "_anthropic_client", classmethod(factory))
    credentials = _user_creds("sk-user-key-1111")

    await LLMService.generate_chat_reply(
        model="claude-sonnet-5-5", user_message="x", context_lines=[], credentials=credentials
    )

    assert len(seen) == 2 and all(item is credentials for item in seen)


@pytest.mark.asyncio
async def test_each_key_gets_its_own_model_catalog(monkeypatch):
    lists = {"sk-key-aaaa-1111": ["claude-sonnet-5-5"], "sk-key-bbbb-2222": ["claude-opus-5-5", "claude-haiku-5-5"]}

    def factory(cls, *, credentials=None, **kwargs):
        return _FakeAnthropic(models=_FakeModels(lists[credentials.api_key]))

    monkeypatch.setattr(LLMService, "_anthropic_client", classmethod(factory))
    first, second = _user_creds("sk-key-aaaa-1111"), _user_creds("sk-key-bbbb-2222")

    ids_a = [e["id"] for e in await LLMService.claude_model_catalog(first)]
    ids_b = [e["id"] for e in await LLMService.claude_model_catalog(second)]

    assert ids_a == ["claude-sonnet-5-5"] and ids_b == ["claude-opus-5-5", "claude-haiku-5-5"]
    assert [e["id"] for e in await LLMService.claude_model_catalog(first)] == ids_a  # still A's list from cache


@pytest.mark.asyncio
async def test_one_users_failures_do_not_open_another_users_circuit(monkeypatch):
    broken = _FakeAnthropic(messages=_FakeMessages(error=_AuthError()))
    working = _FakeAnthropic(messages=_FakeMessages(_message(text="fine")))

    def factory(cls, *, credentials=None, **kwargs):
        return broken if credentials.api_key == "sk-bad-key-0000" else working

    monkeypatch.setattr(LLMService, "_anthropic_client", classmethod(factory))
    bad, good = _user_creds("sk-bad-key-0000", owner="a"), _user_creds("sk-good-key-9999", owner="b")

    for _ in range(3):
        await LLMService.generate_chat_reply(model="claude-sonnet-5-5", user_message="x", context_lines=[], credentials=bad)
    _, bad_result = await LLMService.generate_chat_reply(model="claude-sonnet-5-5", user_message="x", context_lines=[], credentials=bad)
    text, good_result = await LLMService.generate_chat_reply(model="claude-sonnet-5-5", user_message="x", context_lines=[], credentials=good)

    assert bad_result["error_type"] == "provider_circuit_open"
    assert text == "fine" and "error_type" not in good_result
    assert LLMService._failure_count.get("anthropic", 0) == 0  # the server-wide circuit was never touched


@pytest.mark.asyncio
async def test_ollama_uses_the_users_url_and_bearer_key(monkeypatch):
    calls = _install_ollama(monkeypatch, lambda request, n: _ollama_ok())

    await LLMService.generate_chat_reply(
        model="gpt-oss:120b",
        user_message="hi",
        context_lines=[],
        credentials=_user_creds("ollama-key-3333", base_url="https://ollama.com"),
    )

    assert str(calls[0].url) == "https://ollama.com/api/chat"
    assert calls[0].headers["authorization"] == "Bearer ollama-key-3333"


@pytest.mark.asyncio
async def test_ollama_without_credentials_uses_the_server_url_and_sends_no_auth(monkeypatch):
    calls = _install_ollama(monkeypatch, lambda request, n: _ollama_ok())
    await LLMService.generate_chat_reply(model="llama3.2", user_message="hi", context_lines=[])
    assert str(calls[0].url) == f"{settings.OLLAMA_URL.rstrip('/')}/api/chat"
    assert "authorization" not in calls[0].headers


@pytest.mark.asyncio
async def test_ollama_401_is_reported_as_an_auth_error(monkeypatch):
    _install_ollama(monkeypatch, lambda request, n: httpx.Response(401))
    _, metadata = await LLMService.generate_chat_reply(
        model="llama3.2", user_message="hi", context_lines=[], credentials=_user_creds("ollama-key-3333")
    )
    assert metadata["error_type"] == "provider_auth_error"


def _awaitable_models(result=None, error=None):
    async def list_(**kwargs):
        if error is not None:
            raise error
        return result

    return SimpleNamespace(list=list_)


@pytest.mark.asyncio
async def test_connection_test_for_claude(monkeypatch):
    ok = _FakeAnthropic(models=_awaitable_models(result=SimpleNamespace()))
    _use_fake_anthropic(monkeypatch, ok)
    assert (await LLMService.test_connection("anthropic", _user_creds("sk-user-key-1111")))["ok"] is True

    bad = _FakeAnthropic(models=_awaitable_models(error=_AuthError()))
    monkeypatch.setattr(LLMService, "_anthropic_client", classmethod(lambda cls, **kwargs: bad))
    result = await LLMService.test_connection("anthropic", _user_creds("sk-user-key-1111"))
    assert result == {"ok": False, "error_type": "provider_auth_error", "detail": "The provider rejected the key."}
    assert "sk-user-key-1111" not in str(result)


@pytest.mark.asyncio
async def test_connection_test_without_a_claude_key_or_for_openai():
    assert (await LLMService.test_connection("anthropic", None))["error_type"] == "not_configured"
    assert (await LLMService.test_connection("openai", _user_creds("sk-openai-test-9999")))["error_type"] == "provider_not_supported"


@pytest.mark.asyncio
async def test_connection_test_for_ollama(monkeypatch):
    real_client = httpx.AsyncClient
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(401) if request.headers.get("authorization") == "Bearer wrong-key-0000" else httpx.Response(200, json={"models": []})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(llm_module.httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport))

    assert (await LLMService.test_connection("ollama", _user_creds("right-key-1111", base_url="https://ollama.com")))["ok"] is True
    assert str(seen[0].url) == "https://ollama.com/api/tags"
    failed = await LLMService.test_connection("ollama", _user_creds("wrong-key-0000"))
    assert failed["error_type"] == "provider_auth_error" and "wrong-key-0000" not in str(failed)
