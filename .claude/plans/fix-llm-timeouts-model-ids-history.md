# Feature: Fix LLM timeouts, Claude model IDs, and conversation history

The plan should be complete, but validate every file reference and every SDK call against the installed code before relying on it. Pay attention to the names of existing helpers and import from the right modules.

## Feature Description

Real chat generations currently fail and fall back to canned text. Three bugs cause most of it (numbers refer to `progress.md` known bugs):

1. Non-streaming Ollama and Anthropic calls use `timeout=2.0` (`llm_service.py:117`, `:154`); streaming uses `10.0` (`:208`, `:245`).
2. Claude model IDs are dotted (`claude-sonnet-4.6`) in `config.py:63-65` and `docker-compose.yml:112-113`, and `.env.template:55` has an unread variable with a third value. The API does not recognize dotted IDs, and `_resolve_model` (`chat.py:43`) only accepts those two values.
4. The model never sees earlier turns. `_build_prompt` (`llm_service.py:312`) receives only the latest message.

Bug 3 (provider keys saved only in the browser) is the next ticket.

## User Story

As a user chatting with my documents, I want answers from the model I picked, with the conversation remembered, so that follow-up questions work and I do not get a canned excerpt instead of an answer.

## Problem Statement

A first request to Ollama usually exceeds 2 seconds (cold model load), and Claude requests cannot succeed with an invalid model ID. Even when a call succeeds, each turn is answered in isolation.

## Solution Statement

- Replace raw `httpx` Anthropic calls with the official `AsyncAnthropic` SDK (streaming for both endpoints), using current model IDs and the SDK's own retries.
- Give Ollama explicit connect/read timeouts and retry only connection errors and 5xx.
- Add real chat history (last 12 usable messages, character-capped) to both providers, plus the conversation's system prompt.
- Make model IDs configurable in one place, fetched live from the Models API when a key exists, with a static fallback; map legacy dotted IDs at send time.
- Pull the duplicated retrieval and history code in the two chat endpoints into small shared helpers.

## Out of Scope / Non-Goals

- Not included: server-side key storage and the Settings page rewrite (next ticket, bug 3).
- Not included: `LLMProvider` interface, registry, OpenAI, Ollama cloud auth (spec 3.1, later tickets).
- Not included: the server-side refusal-fallback beta. Only a clear message for `stop_reason == "refusal"`.
- Not changing: what the endpoints return when a provider fails (the canned excerpt with `error_type` stays).
- Not changing: the circuit breaker design, RAG retrieval settings (`limit=3`, `min_score=0.1`), SMC layers, frontend code.
- Not removing: unused heavy dependencies (`torch`, `openai`). Tracked as bug 8.

## Feature Metadata

**Feature Type**: Bug Fix + Enhancement  
**Estimated Complexity**: Medium  
**Primary Systems Affected**: `backend/app/services/llm_service.py`, `backend/app/api/v1/endpoints/chat.py`, `backend/app/repositories/chat_repository.py`, config and compose  
**Dependencies**: `anthropic` 0.39.0 to 1.12.1 (brings `httpx2`), `pydantic` 2.10.2 to 2.13.5 (required by the new SDK)

## Related Work

**Implements**: `progress.md` known bugs 1, 2, 4. **Spec**: `spec.md` section 3.1 (provider layer) is the later home for this code.

**Forward-references**: next ticket "server-side provider keys and Settings page" (bug 3); then `LLMProvider` registry + OpenAI.

---

## CONTEXT REFERENCES

### Relevant Codebase Files (read before implementing)

- `backend/app/services/llm_service.py` (whole file, 342 lines) - current behavior to preserve: public classmethods `generate_chat_reply`, `stream_chat_reply`, `list_models`, `provider_health`; circuit breaker (`:324-342`); canned fallback text (`:38-41`, `:89-92`).
- `backend/app/api/v1/endpoints/chat.py:43-54` `_resolve_model`; `:71-140` `_process_chat_turn`; `:323-433` `stream_message` (duplicates retrieval at `:347-370`); `:484-491` models and health routes.
- `backend/app/repositories/chat_repository.py:100-139` message listing (add the history query beside it).
- `backend/app/models/conversation.py` - `Conversation.system_prompt` (unused today), `Message.metadata_json` (holds `error_type`).
- `backend/app/core/config.py:55-66` LLM settings. Note the duplicate undecorated `parse_extensions` near `:127` is unrelated; do not touch.
- `backend/tests/test_chat_endpoints.py:139-198` and `:215-300` - tests that monkeypatch `LLMService` methods with fixed keyword signatures (`:174`, `:237`, `:281`); they must accept new keyword arguments.
- `docker-compose.yml:109-113`, `.env.template:44-55`, `README.md:42-46`.

### New Files to Create

- `backend/tests/test_llm_service.py` - unit tests for the service (no network).
- `backend/tests/test_chat_history.py` - endpoint tests proving history reaches the service in both flows.

### Relevant Documentation (read before implementing)

- Claude API Python reference bundled with the `claude-api` skill: `python/claude-api/README.md` (client init, streaming, error classes, stop reasons) and `python/claude-api/streaming.md`.
  - Why: exact SDK shapes. Do not guess; if a binding is missing, read the installed package source under the venv's `anthropic/`.
- Facts already verified from that reference (2026-10-08):
  - Current IDs: `claude-sonnet-5-5` ($2/$10), `claude-opus-5-5` ($4/$20), `claude-haiku-5-5` ($0.10/$0.50). Never add date suffixes.
  - Do not send `temperature`, `top_p`, `top_k` (400 on these models), `thinking: {type: "disabled"}` or `budget_tokens` (400), forced `tool_choice`, or assistant prefill.
  - Omit `thinking`; thinking blocks arrive empty by default, so read only `text` blocks.
  - Effort goes in `output_config={"effort": "low|medium|high|xhigh|max"}`. Opus 5.5 and Haiku 5.5 default to `medium`, Sonnet 5.5 to `high`.
  - `stop_reason == "refusal"` carries `stop_details.category`; check it before reading content.
  - Models API: `client.models.list()` returns objects with `id` and `display_name`.
  - Catch typed errors: `anthropic.AuthenticationError`, `RateLimitError`, `APIStatusError`, `APIConnectionError`, `APITimeoutError`.

### Patterns to Follow

**Dependency override in endpoint tests** (`test_chat_endpoints.py:12-26`): `app.dependency_overrides[db_session]` and `[get_current_user]`, then `monkeypatch.setattr(chat_module.ChatRepository, "<method>", fake)`. Any new repository call used by an endpoint needs a matching fake.

**Logging**: `logger.warning("... {x}", x=...)` with loguru; bind request context in endpoints (`chat.py:156-161`).

**Errors** (CLAUDE.md rule): provider failures are logged at warning or above and reflected in metadata (`error_type`) and circuit state; never swallowed silently.

**Layering** (CLAUDE.md): endpoints orchestrate; `LLMService` owns provider mechanics with explicit inputs and structured results; repositories own queries.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation (dependencies, config)

Bump pins, add settings, fix IDs everywhere they are declared.

### Phase 2: Service

**Depends on:** Phase 1. Rewrite provider internals in `llm_service.py` while keeping the public classmethod names, add history building, model normalization, live model listing.

### Phase 3: Endpoints and repository

**Depends on:** Phase 2. Add the history query, shared helpers, async model validation, and pass history and system prompt in both flows.

### Phase 4: Tests and docs

Tests per behavior; update `progress.md`, `spec.md` 3.1 note, `README.md` Providers.

---

## STEP-BY-STEP TASKS

### UPDATE backend/requirements.txt

- **IMPLEMENT**: `anthropic==0.39.0` to `anthropic==1.12.1`; `pydantic==2.10.2` to `pydantic==2.13.5`. Leave `httpx==0.27.2` (Ollama client and test client use it; the SDK uses `httpx2` alongside).
- **GOTCHA**: a dry-run resolve with these pins succeeded on 2026-10-08 (adds `httpx2`, `httpcore2`, `docstring-parser`, `truststore`, `typing-inspection`; upgrades `pydantic-core`). Runtime compatibility of `pydantic-settings==2.6.1` and `fastapi==0.115.0` with pydantic 2.13 is unproven; the test suite is the check.
- **VALIDATE**: install into a scratch venv, `python -c "import anthropic, pydantic; print(anthropic.__version__, pydantic.VERSION)"`, then run `piv-validate` and compare to the baseline (51 passed, 14 skipped, the same 4 failures).
- **SATISFIES**: AC 7

### UPDATE backend/app/core/config.py (lines 55-66)

- **IMPLEMENT**: replace the Claude block with `CLAUDE_API_KEY`, `CLAUDE_SONNET_MODEL="claude-sonnet-5-5"`, `CLAUDE_OPUS_MODEL="claude-opus-5-5"`, `CLAUDE_HAIKU_MODEL="claude-haiku-5-5"`, `CLAUDE_DEFAULT_MODEL="claude-sonnet-5-5"`, `CLAUDE_EFFORT="medium"`, `CLAUDE_MAX_OUTPUT_TOKENS=16000`, `ANTHROPIC_REQUEST_TIMEOUT_SECONDS=600`. Remove unused `CLAUDE_MODEL`. Add `OLLAMA_CONNECT_TIMEOUT_SECONDS=5`, `OLLAMA_READ_TIMEOUT_SECONDS=120`, `LLM_HISTORY_MESSAGES=12`, `LLM_HISTORY_MAX_CHARS=24000`, `LLM_MODEL_LIST_TTL_SECONDS=300`.
- **PATTERN**: `Field(default=...)` style at `config.py:58-65`.
- **GOTCHA**: validate `CLAUDE_EFFORT` is one of `low|medium|high|xhigh|max` with a `field_validator` (an invalid value would 400 every call).
- **VALIDATE**: `cd backend && python -c "from app.core.config import settings as s; print(s.CLAUDE_SONNET_MODEL, s.CLAUDE_EFFORT)"`
- **SATISFIES**: AC 2

### UPDATE docker-compose.yml (109-113), .env.template (44-55), README.md (42-46)

- **IMPLEMENT**: compose passes `CLAUDE_SONNET_MODEL`, `CLAUDE_OPUS_MODEL`, `CLAUDE_HAIKU_MODEL`, `CLAUDE_EFFORT` with the new defaults; `.env.template` Claude section lists the same names and drops `CLAUDE_MODEL`; add the Ollama timeout names as commented examples. README Providers bullet names the current IDs and says the list is fetched from the Models API when a key is set.
- **GOTCHA**: compose defaults override `config.py`; a stale dotted default left in compose silently wins. After editing, `grep -rn "4\.6" docker-compose.yml .env.template backend/app` must find nothing model-related.
- **VALIDATE**: `grep -rnE "claude-(sonnet|opus)-4\.6|20250514" docker-compose.yml .env.template backend/app README.md` returns no lines; `docker compose config >/dev/null` if the compose plugin exists in the session.
- **SATISFIES**: AC 2

### UPDATE backend/app/repositories/chat_repository.py

- **IMPLEMENT**: add `list_recent_messages(*, conversation_id, limit)` returning the newest `limit` rows with `role in ("user", "assistant")`, ordered oldest first (query newest first with `limit`, then reverse). Fetch `limit + 4` in the caller to leave room for dropped error rows.
- **PATTERN**: `list_messages_for_conversation_paginated` at `:112-139`.
- **GOTCHA**: do not filter errored rows in SQL; the pure builder below does it so it is unit-testable.
- **VALIDATE**: covered by the integration test under Docker (`tests/test_chat_integration.py`); locally, `python -c "import app.repositories.chat_repository"`.
- **SATISFIES**: AC 4

### UPDATE backend/app/services/llm_service.py

Keep the public classmethods and the circuit breaker. Change internals:

- **IMPLEMENT (history)**: `LLMService.history_from_messages(rows, *, max_messages, max_chars) -> list[dict]`. Pure function over objects with `role`, `content`, `metadata_json`. Drop assistant rows whose `metadata_json` has `error_type`; keep at most `max_messages` newest; drop oldest until total characters are under `max_chars`; then drop leading assistant rows so the list starts with `user`. Returns `[{"role","content"}]`.
- **IMPLEMENT (prompt)**: `_build_messages(history, user_message, context_lines)` returns `history + [{"role": "user", "content": _build_prompt(...)}]`. Keep `_build_prompt` as is. System text: the conversation's `system_prompt` or a module constant (the current "You are a concise assistant..." string).
- **IMPLEMENT (signature)**: add keyword-only `history: list[dict] | None = None` and `system_prompt: str | None = None` to `generate_chat_reply` and `stream_chat_reply`.
- **IMPLEMENT (models)**: `normalize_claude_model(model)` replaces a dot between digits with a hyphen (`claude-sonnet-4.6` becomes `claude-sonnet-4-6`); applied at send time only, never rewriting stored rows. `async allowed_claude_models()` returns the live Models API ids that start with `claude-` (cached for `LLM_MODEL_LIST_TTL_SECONDS`) when a key is set, else the three configured ids; on API error, log a warning and fall back to the configured ids. `list_models()` returns `{"id", "provider", "name"}` entries (add `name` from `display_name`).
- **IMPLEMENT (Anthropic)**: `_anthropic_client()` factory returning `anthropic.AsyncAnthropic(api_key=..., timeout=settings.ANTHROPIC_REQUEST_TIMEOUT_SECONDS, max_retries=2)`. Both generate and stream use `async with client.messages.stream(model=normalized, max_tokens=settings.CLAUDE_MAX_OUTPUT_TOKENS, system=..., messages=..., output_config={"effort": settings.CLAUDE_EFFORT}) as stream`. Non-streaming path awaits `stream.get_final_message()`. Read only `text` blocks. No temperature, no thinking param, no prefill.
- **IMPLEMENT (refusal)**: if `stop_reason == "refusal"`, return the fixed text "The model declined to answer this request." with `error_type="provider_refusal"` and `refusal_category` from `stop_details`; do not count it as a provider failure for the circuit breaker. If `stop_reason == "max_tokens"`, set `truncated=True` in metadata.
- **IMPLEMENT (stream outcome)**: add `@dataclass StreamOutcome` (`stop_reason`, `input_tokens`, `output_tokens`, `error_type`). `stream_chat_reply(..., outcome: StreamOutcome | None = None)` fills it so the endpoint can store real usage and the refusal state. Refusal yields the fixed text as one delta.
- **IMPLEMENT (Ollama)**: build the client with `httpx.Timeout(connect=settings.OLLAMA_CONNECT_TIMEOUT_SECONDS, read=settings.OLLAMA_READ_TIMEOUT_SECONDS, write=10.0, pool=5.0)` via an `_ollama_client()` factory (tests inject a `MockTransport`). Send `[{"role":"system",...}] + history + [final user]`. Retry at most once, 0.5 s apart, only on `httpx.ConnectError`, `httpx.ConnectTimeout`, or `HTTPStatusError` with status >= 500. No retry on 4xx or read timeouts. Streaming applies the same timeouts.
- **IMPLEMENT (errors)**: keep `error_type` values `provider_timeout`, `provider_http_error`, `provider_error`; add Anthropic mappings: `APITimeoutError` to `provider_timeout`, `AuthenticationError`/`PermissionDeniedError` to `provider_auth_error`, `RateLimitError` to `provider_rate_limited`, other `APIStatusError` to `provider_http_error`. Log at warning with the SDK `_request_id` when present. Auth errors do not retry.
- **PATTERN**: current structure `llm_service.py:26-106`; keep the canned fallback block shape.
- **GOTCHA**: delete the generic `for _ in range(2)` retry loop at `:55-75` (it retries auth errors and doubles slow timeouts). Do not leave `import httpx` unused or break `provider_health`/Ollama tag listing. Verify `output_config` and `models.list` exist in the installed SDK before use (`python -c "import inspect, anthropic; ..."`).
- **VALIDATE**: `ruff check backend/app/services/llm_service.py`; unit tests in `test_llm_service.py`.
- **SATISFIES**: AC 1, 2, 3, 5, 6

### UPDATE backend/app/api/v1/endpoints/chat.py

- **IMPLEMENT**: make `_resolve_model` async and check Claude ids with `await LLMService.allowed_claude_models()` (keep the 400 text "Unsupported Anthropic model. Allowed: ..." so `test_create_conversation_rejects_unknown_claude_model` still passes). Update the one caller (`create_conversation`, `:154`).
- **IMPLEMENT**: add `_retrieve_sources(session, user_id, query, use_rag)` returning `(sources, context_lines)`, used by `_process_chat_turn` (`:90-113`) and by `_events` in `stream_message` (`:347-370`). Add `_load_history(chat_repo, conversation)` calling `list_recent_messages` then `LLMService.history_from_messages`. Load history **before** creating the user message so the new message is not duplicated.
- **IMPLEMENT**: pass `history=` and `system_prompt=getattr(conversation, "system_prompt", None)` to `generate_chat_reply` and `stream_chat_reply`. In the stream flow pass an `outcome` object and use its token counts and `error_type` in `assistant_metadata` (`:397-406`), falling back to the estimate when absent.
- **GOTCHA**: test conversations are `SimpleNamespace` without `system_prompt`; use `getattr`. The streaming endpoint's provider label is derived from the model id (`:398`); keep it.
- **VALIDATE**: `pytest tests/test_chat_endpoints.py tests/test_chat_history.py`
- **SATISFIES**: AC 3, 4, 8

### UPDATE backend/tests/test_chat_endpoints.py

- **IMPLEMENT**: fakes at `:174`, `:237`, `:281` accept `**kwargs`; add a fake `list_recent_messages` returning `[]` wherever `create_message` is faked for send/stream tests.
- **VALIDATE**: `pytest tests/test_chat_endpoints.py -q`

### CREATE backend/tests/test_llm_service.py

Unit tests, no network, `pytest.mark.asyncio`:

- history builder: drops errored assistant rows; honors `max_messages` and `max_chars`; starts with `user`; empty input gives `[]`.
- `normalize_claude_model`: `claude-sonnet-4.6` to `claude-sonnet-4-6`; hyphenated ids unchanged.
- config guard: no configured Claude id contains a dot or an 8-digit date suffix.
- `allowed_claude_models`: no key returns the three configured ids; with a fake client returns the live list; fake client raising falls back and logs.
- Ollama (via `httpx.MockTransport`): request JSON has `system`, history turns, then the RAG user turn; timeout object has connect 5 and read 120; a 503 then 200 succeeds after one retry; a 401 is not retried; a connect error is retried once then surfaces `provider_error`.
- Anthropic (fake client with `messages.stream` async context manager and `get_final_message`): called with the normalized model, `max_tokens`, `output_config={"effort": "medium"}`, history in `messages`, and **without** `temperature`, `thinking`, or prefill; text blocks only; usage mapped; `refusal` returns the fixed text with `provider_refusal` and does not trip the circuit breaker; `max_tokens` sets `truncated`; `AuthenticationError` is not retried.
- **VALIDATE**: `pytest tests/test_llm_service.py -q`
- **SATISFIES**: AC 1, 2, 3, 5, 6

### CREATE backend/tests/test_chat_history.py

- Both endpoints: a conversation with prior user/assistant rows returned by the faked `list_recent_messages`; assert the fake `LLMService` method received `history` equal to those turns (and not the new message), and received the conversation's `system_prompt`.
- Stream flow: `StreamOutcome` token counts land in the stored assistant metadata.
- **VALIDATE**: `pytest tests/test_chat_history.py -q`
- **SATISFIES**: AC 4

### UPDATE docs

- `progress.md`: mark bugs 1, 2, 4 fixed with the commit, keep bug 3 as next; add a Log line; update the validation baseline with the new passing count.
- `spec.md` 3.1: one sentence noting the Anthropic adapter now uses the official SDK and IDs come from config plus the Models API.
- **VALIDATE**: `grep -n "4\.6" README.md progress.md` shows only history text.

---

## TESTING STRATEGY

### Unit Tests

New `test_llm_service.py` and `test_chat_history.py` as above. Fakes for the Anthropic client and an `httpx.MockTransport` for Ollama, injected through the `_anthropic_client()` and `_ollama_client()` factories. No live provider calls in CI.

### Integration Tests

Existing `tests/test_chat_integration.py` runs under Docker only. After implementation, run `make test-backend` where a daemon exists; locally these remain skipped. Add one integration case if a daemon is available: two sequential messages, second creates history rows in order. If not, state that it was not run.

### Edge Cases

- First message in a conversation (empty history).
- History where the only rows are errored assistant messages.
- Window cut lands on an assistant row (must drop it so the list starts with `user`).
- Very long messages over the character cap.
- Legacy conversation stored with `claude-sonnet-4.6`.
- No Claude key configured: model list falls back; sending returns the existing `provider_error` fallback.
- Models API unreachable.
- `stop_reason` of `refusal` and `max_tokens`.

---

## VALIDATION COMMANDS

### Level 1: Syntax and style
`ruff check backend/app` and `cd frontend && npm run lint` (frontend unchanged; confirm still clean).

### Level 2: Unit tests
`cd backend && ../.venv-be/bin/python -m pytest -q --no-header -p no:cacheprovider -W ignore` (see `piv-validate`).

### Level 3: Integration tests
`make test-backend` when a Docker daemon exists. Otherwise record as not run.

### Level 4: Manual validation (needs real credentials; do only with the user's key, never print it)
With `CLAUDE_API_KEY` set and `docker compose up`: create a Claude conversation, ask a question, ask a follow-up that depends on the first answer, confirm it is answered with context and the metadata shows real `input_tokens` and `output_tokens`. With Ollama: first request after a model unload completes instead of timing out.

### Level 5: Review
Run `ocr-review-loop` (delegation mode) on the diff before committing.

---

## ACCEPTANCE CRITERIA

- [ ] AC 1: No LLM call uses a 2-second timeout; Ollama has configurable connect/read timeouts; Anthropic uses the SDK timeout setting.
- [ ] AC 2: Claude IDs come from one place, contain no dots or date suffixes, and match across `config.py`, compose, `.env.template` and README.
- [ ] AC 3: Anthropic calls go through `AsyncAnthropic`; no raw `httpx` call to `api.anthropic.com` remains; no `temperature`/`thinking`/prefill is sent.
- [ ] AC 4: Both chat endpoints send up to 12 prior usable messages plus the conversation `system_prompt`, never duplicating the new message, never including errored assistant rows.
- [ ] AC 5: Only connection errors and 5xx are retried for Ollama; auth and 4xx are not retried for either provider.
- [ ] AC 6: Refusals and truncation are reported in metadata, not as generic errors.
- [ ] AC 7: Full native suite: no new failures beyond the 4 known environment failures; passing count increases by the new tests. `ruff` clean.
- [ ] AC 8: Existing endpoint contracts unchanged (response schemas, SSE event names, the 400 text for unknown Claude models).
- [ ] `ocr-review-loop` reports nothing at or above medium, or remaining items are listed.

## COMPLETION CHECKLIST

- [ ] Tasks completed in order, each validated
- [ ] `piv-validate` run; "Not run" items listed honestly (Docker integration, live providers, type checking)
- [ ] `progress.md` updated; plan amendments recorded below
- [ ] Commit with `piv-commit`; no PR unless asked

---

## OPEN QUESTIONS / ASSUMPTIONS

- Assumed: `output_config` and `client.models.list()` exist with these shapes in `anthropic==1.12.1`. First implementation step is to confirm against the installed package.
- Assumed: Sonnet 5.5 at `medium` effort gives acceptable first-token latency for chat. If slow, lower to `low` via `CLAUDE_EFFORT`.
- Assumed: pydantic 2.13 works with `pydantic-settings==2.6.1` and FastAPI 0.115. Tests decide; if not, bump `pydantic-settings` minimally and record it.
- Assumed: legacy dotted ids in old conversations map to their hyphenated equivalents (`claude-sonnet-4-6`, `claude-opus-4-6`), which are valid IDs but older models. Users may re-select a current model.
- Not decided: whether to expose `CLAUDE_EFFORT` per conversation. Deferred to the Settings ticket.
- Privacy: history is only sent to the provider already chosen for that conversation; no new data leaves the machine beyond what each turn already sent.

## NOTES

- Tests that fake `LLMService` classmethods use fixed signatures today; the `**kwargs` update is the cheapest compatible fix and keeps the facade stable for the later `LLMProvider` refactor.
- Streaming is used for the "non-streaming" Anthropic path on purpose: it avoids HTTP timeouts on long answers, and `get_final_message()` gives the same return shape.
- Confidence for one-pass success: 7/10. Main risks are the SDK shapes and the pydantic bump, both checked first.

## AMENDMENTS

- 2026-10-08 - Implemented. Deviations from the plan, all intentional:
  - Added effort-capability handling. Review found that the live Models API lists older models that reject `output_config.effort`; the service now records per-model support (and per-level support) from `capabilities.effort` and omits `effort` when unsupported. The catalog is loaded before the first Claude call.
  - `list_models` adds `name` to Ollama entries as well as Claude entries; the Chat model picker renders `model.name`, which the backend never returned.
  - `stream_chat_reply` now records circuit-breaker success and failure and sets `outcome.error_type` on exceptions (the old streaming path did neither).
  - Streaming Ollama has no retry (output may already have been sent). Only the non-streaming call retries.
  - `test_chat_endpoints.py` uses one autouse fixture for empty history instead of per-test fakes.
  - Review ran inline in the same session, not in a fresh-context subagent.
