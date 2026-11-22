# Feature: LLMProvider interface, registry and OpenAI adapter

The plan below is meant to be complete, but check names and signatures against the code before you start. Do the
refactor as a mechanical move first (behavior identical, suite green), then add OpenAI.

## Feature Description

`LLMService` today holds Anthropic and Ollama code side by side and routes with `startswith("claude-")`; endpoints also
branch on provider names. This ticket introduces an `LLMProvider` interface and a registry, moves the Anthropic and
Ollama code into adapters behind it, adds an OpenAI adapter, and removes provider-name branching from the endpoints.
OpenAI keys already have a slot in `/settings/providers` (`supported=false`); this flips it to supported with a working
Test button, per-user model list, per-credential circuit breaker and model cache.

## User Story

As someone using the notebook
I want to choose OpenAI, Claude or Ollama per conversation and keep my own keys for each
So that I am not tied to one provider and my keys stay mine.

## Problem Statement

- Provider routing is a prefix check plus `is_anthropic_model` in `llm_service.py` and in `endpoints/chat.py` (lines 49, 185, 347, 375, 429, 531, 542). Adding a provider means editing endpoints, which `CLAUDE.md` forbids.
- OpenAI has a settings slot but no adapter. `openai==1.54.0` sits unused in `requirements.txt` (known bug 8).
- `spec.md` 3.1 requires normalized usage and errors, including "credit exhausted".

## Solution Statement

- New package `backend/app/services/llm/`: `base.py` (types and the `LLMProvider` protocol), `common.py` (prompt/history building, circuit breaker, model cache, shared constants), `registry.py` (`provider_for_model`, `get_provider`, `PROVIDER_IDS`), and adapters `anthropic.py`, `ollama.py`, `openai.py`.
- `LLMService` stays as the single entry point with the same public method names (`generate_chat_reply`, `stream_chat_reply`, `list_models`, `provider_health`, `test_connection`, `history_from_messages`, `provider_for`) so endpoints and tests change little; it delegates to the registry. Claude-only helpers on the façade (`normalize_claude_model`, `allowed_claude_models`) move into the Anthropic adapter and are reached through a generic `resolve_model`.
- OpenAI uses the **Responses API** with streaming, `store=False` always, no sampling parameters. Usage and end state come from the final `response.completed` / `response.incomplete` event.
- `list_models` and `provider_health` take a `{provider_id: credentials}` mapping and return a dict keyed by provider id, so a new provider appears in the API and UI without endpoint edits.

## Out of Scope / Non-Goals

- Not included: Laya `DecisionService`, the sensitivity gate and cross-provider fallback (spec 3.1 says opt-in and gated; later ticket). A provider failure still falls back to the document excerpt as today.
- Not included: a per-conversation `provider` column. Routing stays by model id (see Assumptions); a migration is a follow-up if ids collide.
- Not included: OpenAI tools, files, images, audio, embeddings, `previous_response_id`, `store=True`.
- Not included: a privacy-policy control (which providers may receive sensitive content; spec 3.2).
- Not included: a model picker redesign; the existing dropdown gets an OpenAI group.
- Not changing: history trimming, prompt text, `StreamOutcome` fields, message metadata keys, stored `error_type` names (one is added), the `/chat/*` response shapes (new provider keys only).

## Feature Metadata

**Feature Type**: Refactor + New Capability
**Estimated Complexity**: High (breadth; many tests retargeted)
**Primary Systems Affected**: `services/llm_service.py` (split), `credential_service`, `endpoints/chat.py`, config, requirements, compose/env, Chat and Settings pages
**Dependencies**: `openai==3.57.0` (latest on PyPI today; replaces the unused 1.54.0). It depends on `httpx2`, a separate package, so the existing `httpx==0.27.2` pin is untouched (checked with a dry-run install). Docker image must be rebuilt.

## Related Work

**Implements**: `progress.md` Next item 3 and part of known bug 8   ·   **Epic**: `spec.md` 3.1

**Back-references**:
- `.claude/plans/fix-llm-timeouts-model-ids-history.md` - the Anthropic/Ollama code and `StreamOutcome` being moved
- `.claude/plans/server-side-provider-keys.md` - `ProviderCredentials`, per-credential breakers, `/settings/providers`
- `.claude/plans/memory-provider-builtin.md` - same interface-plus-registry layering

**Forward-references**:
- `.claude/plans/model-selection-and-embeddings.md` - adds a `provider` column and `ollama_cloud`, which replace the name-based routing used here

---

## CONTEXT REFERENCES

### Relevant Codebase Files (read before implementing)

- `backend/app/services/llm_service.py` (all, 745 lines) - the code to split. Key spots: `StreamOutcome` 32-41, `ProviderCredentials` 44-57, `_breaker_key` 60-64, class state 67-77, `claude_model_catalog` 108-141, history/prompt helpers 163-222, `generate_chat_reply` 234-306, `stream_chat_reply` 309-342, Ollama 345-480, Anthropic 484-615, `provider_health` 619-642, `list_models` 645-677, `test_connection` 680-704, `_error_type` 707-720, breaker 724-745
- `backend/app/services/credential_service.py` (19, 59, 87-91, 160) - `SUPPORTED_PROVIDERS`, server-key fallback, status, `test`
- `backend/app/api/v1/endpoints/chat.py` (lines 43-55 `_resolve_model`, 183-190 create_conversation, 347, 375, 429, 525-545) - provider branching to remove
- `backend/app/schemas/provider_settings.py`, `backend/app/api/v1/endpoints/provider_settings.py` - already handle `openai`
- `backend/app/core/config.py` (lines 64-77) - Claude settings pattern to mirror
- `backend/tests/test_llm_service.py` (42 tests), `test_chat_endpoints.py`, `test_chat_history.py`, `test_credential_service.py`, `test_provider_settings_endpoints.py`, `test_key_hygiene.py` - tests to retarget; `conftest.py`
- `frontend/src/pages/Chat.jsx` (lines 269-330 model dropdown), `frontend/src/pages/Settings.jsx` (AI Providers section), `frontend/src/components/ProviderKeyFields.jsx`

### New Files to Create

- `backend/app/services/llm/{__init__,base,common,registry,anthropic,ollama,openai}.py`
- `backend/tests/test_openai_provider.py`, `test_llm_registry.py`, `test_provider_boundary.py`

### Relevant Documentation

Verified from the installed SDK source (`openai==3.57.0`, read in a scratch venv) because the docs hosts were not reachable at planning time:
- Responses API stream events: `response.output_text.delta` (`.delta`), `response.refusal.delta`, `response.completed`, `response.incomplete`, `response.failed` (each carries `.response`), and `error` (`.message`, `.code`). Final `response.usage` has `input_tokens`, `output_tokens`, `total_tokens`. `response.incomplete_details.reason` is one of `max_output_tokens`, `max_messages`, `content_filter`, `steered`. `response.status` is one of `completed, failed, in_progress, cancelled, queued, incomplete`.
- `responses.create` accepts `model, instructions, input, max_output_tokens, store, stream, reasoning, temperature`. **`store` defaults to true when omitted and stored data is kept at least 30 days** (docstring in `response_create_params.py`). We always send `store=False`.
- `reasoning_effort` literal: `none, minimal, low, medium, high, xhigh, max` (not every model accepts every level).
- `models.list()` items have `id, created, owned_by, shutdown_date`. No capability flags, so chat-capable models are filtered by id.
- Errors: `AuthenticationError`(401), `PermissionDeniedError`(403), `RateLimitError`(429), `APIStatusError`, `APIConnectionError`; `APITimeoutError` is a subclass of `APIConnectionError`; `APIError.code` carries the body's `code` (`insufficient_quota` on a 429 means out of credit).
- Client: `AsyncOpenAI(api_key, timeout, max_retries)`, default timeout 10 minutes, default `max_retries=2`.
- Model ids present in the SDK's `ChatModel` literal include `gpt-5.5`, `gpt-5.4-mini`, `gpt-5.4-nano`, `gpt-5.6-sol`, `gpt-6-sol`, `gpt-6.1-sol`. The SDK does not say which is the flagship.
- **Not verified** (docs hosts blocked): OpenAI's data-retention and training-use wording, the Chat Completions deprecation status, and the recommended model for chat. The README must not state a training policy; it may state what this app sends (`store=False`) and link to OpenAI's data controls page for the user to read.

### Patterns to Follow

**Layering** (`CLAUDE.md`): endpoints validate, check auth, call services, map results; they never branch on provider names. Provider-specific code lives behind the provider interface.

**Per-credential state**: breaker key `_breaker_key(provider, credentials)`; model cache keyed by credential fingerprint (see `claude_model_catalog`). Server credentials keep the plain provider key.

**Errors**: fixed safe strings, never raw exception text or keys in results (`test_connection`, `_TEST_DETAIL`). Warn-level logs carry `error_type`, `request_id`, never the key or message content.

**Tests**: fake clients injected by monkeypatching the adapter's client factory (see `test_llm_service.py` `_FakeAnthropic`); endpoint tests use `dependency_overrides` (`test_chat_history.py`).

---

## IMPLEMENTATION PLAN

### Phase 1: Interface and shared code (no behavior change)
Create `llm/base.py`, `llm/common.py`, `llm/registry.py`. Move `StreamOutcome`, `ProviderCredentials`, `_breaker_key`, history/prompt/breaker helpers; keep `app.services.llm_service` re-exporting them so existing imports work.

### Phase 2: Port Anthropic and Ollama
**Depends on:** Phase 1. Move code mechanically; retarget tests; run the suite after each adapter.

### Phase 3: OpenAI adapter
**Depends on:** Phase 2 (needs the interface and registry). **Independent of:** Phase 4 frontend.

### Phase 4: Integration
**Depends on:** Phase 3. Credential service, endpoints without provider branching, config, requirements, compose/env.

### Phase 5: Frontend
**Depends on:** Phase 4.

### Phase 6: Tests, docs, validation

---

## STEP-BY-STEP TASKS

### CREATE backend/app/services/llm/base.py
- **IMPLEMENT**: dataclasses `ChatRequest(model, user_message, context_lines, history, system_prompt)`, `ModelInfo(id, name)`, `GenerateResult(text, usage: dict)`; move `StreamOutcome` and `ProviderCredentials` here unchanged; `LLMProvider` Protocol with `id: str`, `owns(model) -> bool`, `normalize_model`, `async resolve_model(model, credentials) -> str` (raises `UnsupportedModel(message)`), `async generate(request, credentials) -> GenerateResult`, `stream(request, credentials, outcome) -> AsyncIterator[str]`, `async list_models(credentials) -> list[ModelInfo]`, `async health(credentials) -> dict`, `async test_connection(credentials) -> dict`, `classify_error(exc) -> str`, `server_credentials() -> ProviderCredentials | None`.
- **PATTERN**: `memory/base.py` for dataclass-plus-Protocol style.
- **GOTCHA**: `ProviderCredentials.fingerprint` must keep its exact behavior (tests and the breaker rely on it).
- **VALIDATE**: `cd backend && ../.venv-be/bin/python -c "from app.services.llm.base import LLMProvider, StreamOutcome, ProviderCredentials"`
- **SATISFIES**: AC 1

### CREATE backend/app/services/llm/common.py
- **IMPLEMENT**: move from `LLMService`: `DEFAULT_SYSTEM_PROMPT`, `REFUSAL_TEXT`, `NO_CONTEXT_TEXT`, `MODEL_LIST_FAILURE_TTL_SECONDS`, `history_from_messages`, `build_prompt`, `build_messages`, `system_text`, `fallback_content`, `_breaker_key`, and the breaker as a small `CircuitBreakers` class (`record_failure/record_success/is_open`) with the same 3-failures/30-seconds behavior. Add `ModelCache` (get/put with TTL per credential fingerprint) replacing the Claude-only dict.
- **GOTCHA**: tests read `LLMService._failure_count` directly (7 places). Keep a class attribute on `LLMService` that is the same dict object the breaker uses (`LLMService._failure_count = breakers.failure_count`), or retarget those tests; do not silently lose them.
- **VALIDATE**: `cd backend && ../.venv-be/bin/python -m pytest tests/test_llm_service.py -q`
- **SATISFIES**: AC 1, 5

### CREATE backend/app/services/llm/anthropic.py and ollama.py (mechanical move)
- **IMPLEMENT**: `AnthropicProvider` takes `_anthropic_client`, `_anthropic_request`, `_anthropic_usage`, generate, stream, model catalog (`claude_model_catalog`, `allowed_claude_models`, `_supports_effort`, `_effort_ok`), `normalize_claude_model`, `test_connection` branch, health branch, error mapping for `anthropic.*`. `OllamaProvider` takes the `_ollama_*` helpers, generate, stream, tags listing, probe, error mapping for `httpx`. `owns()`: Anthropic = `claude-` prefix; Ollama = fallback for everything the registry does not assign elsewhere.
- **PATTERN**: the existing code, copied without edits other than `self`/`cls` and imports.
- **GOTCHA**: `OLLAMA_MAX_ATTEMPTS` / retry constants move with it. The `_error_type` function becomes per-adapter `classify_error`; the façade tries the owning adapter only.
- **VALIDATE**: after each adapter, `cd backend && ../.venv-be/bin/python -m pytest -q` (only the 4 known failures allowed)
- **SATISFIES**: AC 1, 2

### CREATE backend/app/services/llm/registry.py
- **IMPLEMENT**: `PROVIDER_IDS = ("anthropic", "openai", "ollama")`; `get_provider(name)`; `provider_for_model(model)`: lower-cased, `claude-` -> anthropic; contains `:` -> ollama (Ollama tags; this keeps `gpt-oss:20b` off OpenAI); matches `^(gpt-|o\d|chatgpt-)` -> openai; else ollama. `async resolve_model(model, credentials_by_provider)` normalizes and validates against the owning adapter.
- **GOTCHA**: this heuristic is the one place provider ids are inferred from model names. Cover it with a table test, including `gpt-oss:20b`, `gpt-oss` (no tag: documented to route to OpenAI and then fail validation with a clear message), `o3`, `o4-mini`, `llama3.2:3b-instruct-q4_K_M`, `claude-sonnet-5-5`, `GPT-5.5`.
- **VALIDATE**: `cd backend && ../.venv-be/bin/python -m pytest tests/test_llm_registry.py -q`
- **SATISFIES**: AC 1, 3

### UPDATE backend/app/services/llm_service.py
- **IMPLEMENT**: reduce to the façade. Keep public names. `generate_chat_reply` / `stream_chat_reply` pick the adapter via the registry, apply the breaker, build the fallback and metadata exactly as today. `list_models(credentials_by_provider)` and `provider_health(credentials_by_provider)` loop over `PROVIDER_IDS`. Add `resolve_model` and `provider_for` delegating to the registry. Re-export `StreamOutcome`, `ProviderCredentials`.
- **GOTCHA**: keep `metadata["provider"]` equal to the adapter id so stored messages stay comparable.
- **VALIDATE**: `cd backend && ../.venv-be/bin/python -m pytest tests -q`
- **SATISFIES**: AC 1, 2

### CREATE backend/app/services/llm/openai.py
- **IMPLEMENT**: `OpenAIProvider`:
  - client: `openai.AsyncOpenAI(api_key=..., timeout=settings.OPENAI_REQUEST_TIMEOUT_SECONDS, max_retries=2)`; probe and listing use `timeout=10, max_retries=0`. Raise `RuntimeError("No OpenAI API key is configured")` when no key (same as Anthropic).
  - request: `model`, `instructions=system_text(...)`, `input=[{"role": turn.role, "content": turn.content}, ...]` built from `build_messages` (roles are only `user`/`assistant`), `max_output_tokens=settings.OPENAI_MAX_OUTPUT_TOKENS`, `store=False`, `stream=True`. Add `reasoning={"effort": settings.OPENAI_REASONING_EFFORT}` only when that setting is non-empty. Never send `temperature`, `top_p`, `previous_response_id`, `user` or `metadata`.
  - stream: iterate events. `response.output_text.delta` -> yield `delta`. `response.refusal.delta` -> accumulate refusal text. `response.completed` / `response.incomplete` -> read `.response.usage` and `incomplete_details.reason`. `response.failed` -> raise `ProviderStreamError` carrying the error code. `error` event -> raise likewise.
  - outcome: `stop_reason` = `response.status` or incomplete reason; tokens from usage; `truncated=True` for `max_output_tokens`; refusal (refusal deltas and no text, or `content_filter`) -> `error_type="provider_refusal"`, `refusal_category` = `"content_filter"` or `None`, yield `REFUSAL_TEXT` if nothing was yielded.
  - generate: consume the same stream and return text plus usage dict with the same keys as Anthropic (`input_tokens`, `output_tokens`, `total_tokens`, `truncated`, `error_type`, `refusal_category`). Empty text with no refusal -> `RuntimeError("Empty OpenAI response")`.
  - list_models: `client.models.list()` (async iteration), keep ids matching `^(gpt-|o\d|chatgpt-)` and not containing any of `embedding, whisper, tts, transcribe, audio, realtime, image, moderation, search, dall-e`; newest `created` first; cache per credential fingerprint for `LLM_MODEL_LIST_TTL_SECONDS`; on failure cache the static list (`[OPENAI_DEFAULT_MODEL]`) for 30 seconds and log a warning with the error type.
  - resolve_model: allowed = live list plus `OPENAI_DEFAULT_MODEL`; otherwise `UnsupportedModel("Unsupported OpenAI model. Allowed: [...]")`.
  - test_connection: one `models.list()` page with `timeout=10, max_retries=0`; fixed safe detail strings.
  - classify_error: `APITimeoutError` -> `provider_timeout` (checked before the connection error); `AuthenticationError`/`PermissionDeniedError` -> `provider_auth_error`; `RateLimitError` with `code == "insufficient_quota"` -> new `provider_quota_exceeded`, other `RateLimitError` -> `provider_rate_limited`; other `APIStatusError` -> `provider_http_error`; else `provider_error`.
  - health: `{"healthy": bool(key), "circuit_open": ...}` like Anthropic.
  - `server_credentials()`: `OPENAI_API_KEY` when `ALLOW_SERVER_PROVIDER_KEYS`.
- **GOTCHA**: `store=False` is a privacy requirement, not a tuning choice: the API default is to store for at least 30 days. A test must fail if it is ever omitted. Responses can arrive with `usage=None`; treat missing usage as unknown (`None`), not zero. A stream that ends without a terminal event is an error (`RuntimeError`), not a silent empty answer. Do not log message content.
- **IMPORTS**: `openai`, `app.services.llm.common`, `app.services.llm.base`.
- **VALIDATE**: `cd backend && ../.venv-be/bin/python -m pytest tests/test_openai_provider.py -q`
- **SATISFIES**: AC 2, 3, 4, 6

### UPDATE backend/app/core/config.py, backend/requirements.txt, docker-compose.yml, .env.template
- **ADD**: `OPENAI_API_KEY: str = ""` (server-wide fallback), `OPENAI_DEFAULT_MODEL: str = "gpt-5.5"`, `OPENAI_MAX_OUTPUT_TOKENS: int = 16000`, `OPENAI_REQUEST_TIMEOUT_SECONDS: float = 600.0`, `OPENAI_REASONING_EFFORT: str = ""` with a validator accepting `""` or one of `none, minimal, low, medium, high, xhigh, max`. `requirements.txt`: `openai==3.57.0` replacing `openai==1.54.0`. Compose and env template pass-through with comments (key optional; users normally save theirs in Settings).
- **GOTCHA**: the validator must not echo an invalid value in its error text if it could be a key; this field is not a secret, so the `CLAUDE_EFFORT` validator pattern is fine. Keep `OPENAI_API_KEY` out of every log and `repr`.
- **VALIDATE**: `cd backend && ../.venv-be/bin/pip install -q -r <(grep -vE "^(torch|transformers|sentence-transformers)" requirements.txt) && ../.venv-be/bin/python -c "from app.core.config import settings; print(settings.OPENAI_DEFAULT_MODEL)"`
- **SATISFIES**: AC 6

### UPDATE backend/app/services/credential_service.py
- **IMPLEMENT**: `SUPPORTED_PROVIDERS` from the registry; server fallback via `get_provider(provider).server_credentials()` instead of the hard-coded Anthropic branch (in `resolve` and `_status_for`); `test()` unchanged.
- **GOTCHA**: Ollama's "always available" server source stays special-cased only for the status display, via the adapter (`server_credentials()` returns None for Ollama; `_status_for` keeps `source="server"` for providers whose adapter reports `always_available=True`).
- **VALIDATE**: `cd backend && ../.venv-be/bin/python -m pytest tests/test_credential_service.py tests/test_provider_settings_endpoints.py -q`
- **SATISFIES**: AC 2, 3

### UPDATE backend/app/api/v1/endpoints/chat.py
- **IMPLEMENT**: delete `claude-`/`anthropic`/`ollama` literals. `_resolve_model` calls `LLMService.resolve_model(model, credentials_for(provider))` and maps `UnsupportedModel` to 400. A small helper `_credentials_for(credential_service, user_id, model)` resolves credentials for `LLMService.provider_for(model)`. `assistant_metadata["provider"] = LLMService.provider_for(model)`. `/chat/models` and `/chat/providers/health` resolve credentials for every id in `PROVIDER_IDS` and call the façade once.
- **GOTCHA**: keep error text for Claude unchanged (`"Unsupported Anthropic model. Allowed: ..."`) because a test asserts it. The 400 is raised before saving the conversation.
- **VALIDATE**: `cd backend && ../.venv-be/bin/python -m pytest tests/test_chat_endpoints.py tests/test_chat_history.py -q`
- **SATISFIES**: AC 1, 3

### UPDATE frontend Chat.jsx, Settings.jsx
- **IMPLEMENT**: Chat model dropdown renders one group per provider key present in `models` (Ollama, Claude, OpenAI) and finds the selected model across all groups. Settings gets an OpenAI card (`ProviderKeyFields provider="openai"`, placeholder `sk-...`, help link to OpenAI's API keys page) with a status badge from `health.openai` and its model chips. The "Not Configured" badge shows when no key is available.
- **GOTCHA**: do not touch the profile/password handlers (known bug 11). No logging of response bodies.
- **VALIDATE**: `cd frontend && npm run lint && npm run build`
- **SATISFIES**: AC 7

### CREATE tests
- `test_openai_provider.py`: fake `AsyncOpenAI` whose `responses.create` returns an async iterator of event objects with the verified `type` strings; cases: text streaming and usage; `store=False` on every request and no `temperature`/`top_p`/`previous_response_id`; `reasoning` sent only when configured; instructions and history mapping; `response.incomplete` with `max_output_tokens` -> `truncated`; refusal deltas -> `provider_refusal`; `content_filter` -> refusal with category; `response.failed` and `error` events raise; stream ends with no terminal event -> error; `usage=None` handled; generate path; model list filtering and ordering, cache per credential (two keys never share), failure falls back to the default model; `resolve_model` accepts live and default ids and rejects others; `test_connection` for ok, 401, 429 quota, 429 rate limit, timeout, and a no-key case, each with a fixed safe detail and no key in the result; breaker is per credential (one user's failures do not open another's); real SDK exception classes built with `httpx2` responses.
- `test_llm_registry.py`: routing table (above), adapters registered for every id in `PROVIDER_IDS`, `resolve_model` per provider.
- `test_provider_boundary.py`: scans `app/api/v1/endpoints/*.py` (except `provider_settings.py`, whose path parameter is the provider id) and fails on the literals `claude-`, `"anthropic"`, `"openai"`, `"ollama"`.
- Retarget existing tests that reference moved privates (`_anthropic_client`, `_ollama_timeout`, `_failure_count`, `claude_model_catalog`, `configured_claude_models`, `allowed_claude_models`, `normalize_claude_model`); keep every assertion.
- `test_credential_service.py`: OpenAI resolves from the user's row, from `OPENAI_API_KEY` when allowed, and not when `ALLOW_SERVER_PROVIDER_KEYS=false`; status says `supported=true`.
- **VALIDATE**: `cd backend && ../.venv-be/bin/python -m pytest -q`
- **SATISFIES**: AC 1-7

### UPDATE README.md, spec.md, progress.md, docs
- **IMPLEMENT**: README provider section for OpenAI (key in Settings; what the app sends: `store=False`; no claim about OpenAI's training or retention policy, link only); spec 3.1 status; progress (item 3 done, bug 8 note, baseline, log); `.env.template` comments.
- **VALIDATE**: `grep -n "OpenAI" README.md progress.md spec.md | head`

---

## TESTING STRATEGY

### Unit Tests
As above. The OpenAI tests build events as `SimpleNamespace(type=..., ...)` objects using the exact field names verified in the SDK, and raise real `openai` exception classes so classification is tested against the library, not a stand-in.

### Integration
Run by hand (no Docker daemon in the cloud container): boot the app against local Postgres and Redis; point the OpenAI adapter at a stand-in server speaking the Responses streaming format by passing `base_url` (the SDK accepts it) to verify the full chat path, headers, `store: false` in the request body, and that a Chat page conversation with an `gpt-` model streams. A real OpenAI call needs the owner's key and `api.openai.com` reachable; not available here.

### Edge Cases
Model id that is both plausible for OpenAI and Ollama (`gpt-oss:20b`); user without a key selecting an OpenAI model (clear 400 or provider auth fallback, never a 500); key saved for one provider used for another (never); empty model list; a model with `shutdown_date`; stream that yields only a refusal; very long history (trimmed by existing code); two users with different keys hitting the same model cache; `OPENAI_REASONING_EFFORT` invalid -> startup error naming the allowed values.

---

## VALIDATION COMMANDS

Use the `piv-validate` skill. Native venv `.venv-be`.

### Level 1: `cd backend && ../.venv-be/bin/ruff check app tests` and `cd frontend && npm run lint`
### Level 2: `cd backend && ../.venv-be/bin/python -m pytest -q` (only the 4 known `postgres`-host failures allowed; at least 172 passed)
### Level 3: `cd frontend && npm run build`
### Level 4: Manual, as under Integration, plus headless Chromium on the Settings and Chat pages with a stand-in OpenAI server.
### Level 5: Mutation checks: each of (a) drop `store=False`, (b) add `temperature` to the request, (c) share the model cache across credentials, (d) breaker key ignores credentials, (e) `insufficient_quota` classified as plain rate limit, (f) route `gpt-oss:20b` to OpenAI, (g) lose usage on `response.incomplete`, (h) swallow `response.failed`, (i) leak the key in a test_connection detail, (j) add a provider literal to an endpoint, must fail a test.

---

## ACCEPTANCE CRITERIA

- [ ] AC 1: Endpoints and the credential service contain no provider-name branching; `LLMService` routes through the registry.
- [ ] AC 2: Anthropic and Ollama behave exactly as before (existing assertions unchanged apart from import targets).
- [ ] AC 3: OpenAI is selectable per conversation, appears in `/chat/models` and `/chat/providers/health` for users with a key, and `/settings/providers` reports `supported=true` with a working Test.
- [ ] AC 4: OpenAI streaming, history, system prompt, usage, truncation and refusal reporting match Anthropic's metadata keys.
- [ ] AC 5: Circuit breakers and model caches are per credential for every provider.
- [ ] AC 6: Every OpenAI request sends `store=False` and no sampling parameters; keys never appear in logs, results or errors.
- [ ] AC 7: Settings has an OpenAI card and the model dropdown has an OpenAI group; lint and build pass.
- [ ] No new failures; mutation checks all caught; docs updated.

## COMPLETION CHECKLIST

- [ ] Tasks done in order, each validated
- [ ] `piv-validate` run; "Not run" items listed honestly
- [ ] Review loop (`ocr-review-loop`) run, findings fixed
- [ ] Report written to `.claude/reports/llm-provider-interface-openai-report.md`
- [ ] Commit with `piv-commit`; no PR unless asked

---

## OPEN QUESTIONS / ASSUMPTIONS

The owner said to use defaults and not stop, so these are assumed and should be confirmed later:

- Assumed - OpenAI **Responses API**, not Chat Completions. The SDK README calls Responses the primary API and Chat Completions "supported indefinitely"; the official deprecation page could not be read (host blocked).
- Assumed - default model id `gpt-5.5`: it is in the SDK's model list and README examples, but the SDK does not say which model is the flagship. Users see the live list from their own key; `OPENAI_DEFAULT_MODEL` changes the fallback.
- Assumed - routing by model id (`:` means Ollama; `gpt-`, `o<digit>`, `chatgpt-` mean OpenAI). Collides only for an Ollama model with no tag whose name starts with `gpt-`/`o<digit>`; Ollama's own list always includes tags. A `provider` column on conversations is the robust fix if this bites.
- Assumed - `OPENAI_API_KEY` as an optional server-wide fallback, mirroring `CLAUDE_API_KEY`, governed by `ALLOW_SERVER_PROVIDER_KEYS`.
- Assumed - no `temperature`/`top_p` (reasoning models reject them; unverified per model) and no reasoning effort unless configured, because accepted levels differ by model and an unsupported level would fail every request.
- Assumed - chat-capable models are recognised by id pattern because `models.list()` carries no capability flags; an unusual new id family would not appear until the pattern is updated.
- **Unverified (docs blocked)** - OpenAI's data retention and training-use policy for API data, and whether `store=False` also disables abuse-monitoring retention. The app sends `store=False`; the README must not promise more. Read OpenAI's data controls page before relying on this for sensitive data.
- Assumed - OpenAI sees the same prompts Anthropic does. Until the privacy-policy control exists (spec 3.2), nothing stops a user from sending sensitive content to a cloud provider they chose; unchanged by this ticket.
- Risk - `openai` jumps from the unused 1.54.0 to 3.57.0; the plan relies on the installed SDK's types, not memory of older versions. Pin stays exact.

## NOTES

- Why a façade instead of calling adapters from endpoints: endpoints and about 40 tests already use `LLMService`; keeping its public names makes the refactor mechanical and keeps the breaker and fallback behavior in one place.
- Why Responses over Chat Completions: it is what the SDK calls primary, it has a first-class `instructions` field, explicit `store`, and a terminal event that carries usage and the incomplete reason, which maps cleanly onto `StreamOutcome`.
- Why generate reuses the stream: same reason as Anthropic (long answers and HTTP timeouts), and one code path to test.
- Why `store=False` is non-negotiable: the SDK docstring says the default is to keep responses for at least 30 days. A privacy-first app cannot leave that to defaults.
- Risks: breadth (about 15 files plus retargeted tests), the façade changing `list_models`/`provider_health` signatures (tests and two endpoints), and no real OpenAI call being possible in the cloud container.
- Confidence for one-pass success: 7/10.

## AMENDMENTS

- 2026-11-21 - Adapter modules are named `*_provider.py` (`anthropic_provider.py`, `ollama_provider.py`, `openai_provider.py`) so they do not share a name with the SDK packages they import.
- 2026-11-21 - The circuit breaker stays on the `LLMService` façade instead of moving to `common.py`: it is provider-agnostic, keyed by provider and credential, and tests assert on its state. Behaviour is unchanged.
- 2026-11-21 - Added `accepts_base_url` to the provider interface so the credential service no longer names Ollama; `_TEST_DETAIL` moved to `common.TEST_DETAIL` and gained `provider_quota_exceeded`.
- 2026-11-21 - The OpenAI adapter takes its key only from the credentials it is given (the server-wide key arrives through `server_credentials()`), so `ALLOW_SERVER_PROVIDER_KEYS=false` is honoured. The Anthropic adapter was left as it was and still falls back to `CLAUDE_API_KEY` (recorded as known bug 14).
- 2026-11-21 - `resolve_model` for OpenAI with no saved key raises a clear message ("Add one in Settings") instead of accepting the default id.
- 2026-11-21 - Found and fixed: Settings called `useProviderHealth()` with no token while the hook only ran when given one, so every provider badge read "not configured". The hook no longer waits for a token.
- 2026-11-21 - Provider status for OpenAI shows a "Key saved" badge (health reports that a key exists, not that it works; the Test button proves that).
