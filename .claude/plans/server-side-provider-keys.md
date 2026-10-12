# Feature: Server-side encrypted provider keys and a real Settings page

The plan should be complete, but validate every file reference and SDK or library call against the installed code before relying on it. Pay attention to the names of existing helpers and import from the right modules.

## Feature Description

Provider API keys (Claude now, OpenAI later, Ollama Cloud) are saved by the backend, encrypted at rest with a master key that lives only in the operator's local environment, and used for that user's requests. The Settings page stops writing keys to browser `localStorage` and talks to new `/settings/providers` endpoints. Known bug 3, plus bugs 12 and 13 from `progress.md`.

## User Story

As the owner of a self-hosted install, I want to enter my provider keys in the app and have them stored encrypted on my server, so that keys never sit in the repo, in my browser storage, or in a file I might commit by accident.

## Problem Statement

`Settings.jsx` saves the Claude and Ollama keys in `localStorage` and the backend never receives them; the backend only reads `CLAUDE_API_KEY` from its environment. Anyone wanting to use the app must put a key in a file, which is how secrets end up in git. In addition, validation errors echo submitted values (a rejected key submission would return the key), and `/chat/models` and `/chat/providers/health` need no login.

## Solution Statement

- A `provider_credentials` table holds one row per user and provider: the key encrypted with Fernet (via `cryptography`), a last-four hint for display, and an optional Ollama base URL.
- A `SecretBox` wraps `MultiFernet` using `SECRETS_ENCRYPTION_KEY` (comma-separated, newest first, so keys can rotate). Ciphertext is bound to its owner and provider, so a copied row will not decrypt in another place. If the master key is unset the app still starts and saving a key returns a clear 503.
- `CredentialService.resolve()` returns the user's own credentials, else the server-wide env key (unless `ALLOW_SERVER_PROVIDER_KEYS=false`), else nothing.
- `LLMService` takes an optional `ProviderCredentials` on every call. Model-catalog caches and circuit breakers are keyed per credential so one user's bad key cannot affect another.
- New endpoints list, save, delete and test a provider. Responses never contain a key or ciphertext.
- `/chat/models` and `/chat/providers/health` require login and use the caller's credentials.
- The 422 handler stops returning submitted values.
- The Settings page uses the endpoints, never shows a saved key, and offers a one-click move of any key found in browser storage.

## Out of Scope / Non-Goals

- Not included: the profile and password buttons on Settings (known bug 11, needs backend endpoints; separate ticket).
- Not included: the `LLMProvider` interface and the OpenAI adapter. The table and API accept `openai`, but no OpenAI card is shown and `test` returns "not supported yet".
- Not included: a key-rotation command that re-encrypts existing rows. Rotation is supported by key order; re-encrypting is manual or a later ticket.
- Not included: HTTPS enforcement or TLS setup. Docs will say to use HTTPS on anything but localhost.
- Not included: wiring the SMC audit log (known bug 5). Credential changes are logged as structured log lines without secrets.
- Not changing: auth, sessions, conversation and message schemas, RAG, existing chat endpoint contracts other than the two that gain authentication.

## Feature Metadata

**Feature Type**: New Capability + Security Fix  
**Estimated Complexity**: High (new table, crypto, per-credential service plumbing, frontend)  
**Primary Systems Affected**: `core/config.py`, new `core/secret_box.py`, `models`, `alembic`, `repositories`, `services/credential_service.py`, `services/llm_service.py`, `api/v1/endpoints/chat.py` and new `provider_settings.py`, `main.py`, `frontend/src/pages/Settings.jsx` and `api/settings.js`  
**Dependencies**: `cryptography` (already installed transitively as 50.0.2; pin it explicitly)

## Related Work

**Implements**: `progress.md` known bugs 3, 12, 13. **Spec**: `spec.md` section 3.2 (Settings).

**Back-references**:
- `.claude/plans/fix-llm-timeouts-model-ids-history.md` - Why: this builds on `LLMService`, `StreamOutcome`, the model catalog and effort handling from that ticket.

**Forward-references**:
- `LLMProvider` interface and OpenAI adapter (will read credentials through `CredentialService`).
- Profile and password endpoints (bug 11).

---

## CONTEXT REFERENCES

### Relevant Codebase Files (read before implementing)

- `backend/app/services/llm_service.py` (whole file) - class-level state to change: `_failure_count` and `_circuit_open_until` (keyed by provider today), `_model_cache` (global today), `_anthropic_client`, `_ollama_client`, `claude_model_catalog`, `allowed_claude_models`, `provider_health`, `list_models`.
- `backend/app/api/v1/endpoints/chat.py:43-55` `_resolve_model`; `:176-186` create_conversation caller; the `generate_chat_reply` and `stream_chat_reply` call sites in `_process_chat_turn` and `stream_message`; `list_chat_models` and `provider_health` routes at the end of the file.
- `backend/app/api/deps.py` - `db_session`, `get_current_user`, `require_roles` patterns to mirror for a credential-service dependency.
- `backend/app/main.py` `validation_error_handler` (near the end, before the root route) - returns `exc.errors()`.
- `backend/app/models/user.py`, `models/base.py` (`TimestampMixin`), `models/__init__.py` - model pattern.
- `backend/alembic/versions/20260217_000002_sessions_token_text.py` - latest revision (`down_revision` for the new one); `20260213_000001_initial_schema.py` - table and index style (`op.create_table`, `postgresql.UUID(as_uuid=True)`).
- `backend/app/repositories/user_repository.py` and `repositories/__init__.py` - repository pattern and export list.
- `backend/app/api/v1/endpoints/users.py` - router and `Depends` style; `backend/app/api/v1/__init__.py` - router registration.
- `backend/app/schemas/user.py` - schema style.
- `frontend/src/pages/Settings.jsx:85-110` (state), `:181-200` (the two localStorage handlers), `:325-470` (provider cards); `frontend/src/api/settings.js`; `frontend/src/api/client.js` (axios + auth interceptor); `frontend/src/store/authStore.js` (user role).
- `backend/tests/test_chat_endpoints.py` (dependency-override pattern and the autouse history fixture), `tests/test_llm_service.py` (fakes for the Anthropic client and Ollama `MockTransport`), `tests/test_chat_integration.py:1-31` (Docker-only integration pattern guarded by `RUN_DB_INTEGRATION_TESTS`).

### New Files to Create

- `backend/app/core/secret_box.py`
- `backend/app/models/provider_credential.py`
- `backend/alembic/versions/20261012_000003_provider_credentials.py`
- `backend/app/repositories/credential_repository.py`
- `backend/app/schemas/provider_settings.py`
- `backend/app/services/credential_service.py`
- `backend/app/api/v1/endpoints/provider_settings.py`
- Tests: `test_secret_box.py`, `test_credential_service.py`, `test_provider_settings_endpoints.py`, `test_key_hygiene.py`, `test_provider_credentials_integration.py` (Docker-only)

### Relevant Documentation

- Fernet and MultiFernet (`cryptography.fernet`): token format, `Fernet.generate_key()`, `MultiFernet([...]).decrypt()` tries keys in order, `rotate()` re-encrypts under the first key. Read the installed package docstrings.
- Ollama Cloud auth (checked 2026-10-12, docs.ollama.com): direct access to `https://ollama.com/api` needs an API key sent as `Authorization: Bearer <key>`; hosted model names drop the `-cloud` suffix (for example `gpt-oss:120b`). A local Ollama signed in with `ollama signin` needs no key. Re-check before implementing the Ollama request headers.
- Anthropic SDK (installed `anthropic==1.12.1`): `AsyncAnthropic(api_key=..., timeout=..., max_retries=...)`; `client.models.list()` is a cheap authenticated call, usable as the connection test; typed errors `AuthenticationError`, `PermissionDeniedError`, `RateLimitError`, `APIConnectionError`, `APITimeoutError`.

### Patterns to Follow

**Dependency override in endpoint tests**: `app.dependency_overrides[db_session]` and `[get_current_user]`; add one for the new credential-service dependency.

**Logging**: loguru with `logger.bind(request_id=..., action=..., user_id=...)`. Never log a key, ciphertext, or request body. Log provider, source (`user` or `server`) and fingerprint prefix only.

**Errors**: `HTTPException` with a plain `detail`; provider errors keep the `error_type` vocabulary from `LLMService._error_type`.

**Migrations**: timestamped file names, explicit `revision` and `down_revision`, `upgrade` and `downgrade` both written.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation (crypto, config, table)

`SecretBox`, settings, model, migration, repository, schemas. No behavior change yet.

### Phase 2: Service and LLM plumbing

**Depends on:** Phase 1. `CredentialService`; `ProviderCredentials` threaded through `LLMService` with per-credential caches and breakers; `test_connection`.

### Phase 3: Endpoints and hardening

**Depends on:** Phase 2. New settings endpoints, authenticated per-user chat model/health routes, sanitized 422 handler.

### Phase 4: Frontend

**Depends on:** Phase 3 (endpoint contract). **Independent of:** none after that; backend tests do not need it.

### Phase 5: Docs, hygiene checks, validation

---

## STEP-BY-STEP TASKS

### UPDATE backend/requirements.txt

- **IMPLEMENT**: add `cryptography==<installed version>` (confirm with `python -c "import cryptography; print(cryptography.__version__)"`, currently 50.0.2). Keep `python-jose[cryptography]`.
- **VALIDATE**: `uv pip install --dry-run -r` on the filtered requirements resolves; suite unchanged.
- **SATISFIES**: AC 1

### UPDATE backend/app/core/config.py

- **IMPLEMENT**: `SECRETS_ENCRYPTION_KEY: str = ""` (comma-separated Fernet keys, newest first), `ALLOW_SERVER_PROVIDER_KEYS: bool = True`. A `field_validator` checks each non-empty part is a valid Fernet key and raises a `ValueError` that never includes the value.
- **PATTERN**: existing validators in the same file.
- **GOTCHA**: do not print or repr the key anywhere; pydantic error output includes `input_value`, so the validator must raise without echoing it and the test must prove it.
- **VALIDATE**: `cd backend && SECRETS_ENCRYPTION_KEY=not-a-key ../.venv-be/bin/python -c "from app.core.config import settings" 2>&1 | grep -c not-a-key` prints 0.
- **SATISFIES**: AC 1, 9

### CREATE backend/app/core/secret_box.py

- **IMPLEMENT**: `SecretBox(keys: str)` built on `MultiFernet`; `is_configured`; `encrypt(value, *, context)` and `decrypt(token, *, context)` where the plaintext is a small JSON envelope `{"c": context, "v": value}` and decrypt rejects a context mismatch; exceptions `SecretsNotConfigured` and `SecretDecryptError` (messages never include the value). `get_secret_box()` returns a module-level instance built from settings (re-built when settings change, for tests).
- **GOTCHA**: `context` is `f"{user_id}:{provider}"`.
- **VALIDATE**: `pytest tests/test_secret_box.py -q`
- **SATISFIES**: AC 1, 2

### CREATE backend/app/models/provider_credential.py, UPDATE backend/app/models/__init__.py

- **IMPLEMENT**: `ProviderCredential(Base, TimestampMixin)`, table `provider_credentials`: `id` UUID pk, `user_id` FK `users.id` ondelete CASCADE (index), `provider` String(20), `api_key_encrypted` Text nullable, `key_hint` String(8) nullable, `base_url` String(500) nullable; `UniqueConstraint("user_id", "provider")`. Export it.
- **PATTERN**: `models/conversation.py`.
- **VALIDATE**: `python -c "from app.models import ProviderCredential"`

### CREATE backend/alembic/versions/20261012_000003_provider_credentials.py

- **IMPLEMENT**: `revision = "20261012_000003"`, `down_revision = "20260217_000002"`; `upgrade` creates the table, the unique constraint and the `user_id` index; `downgrade` drops them.
- **GOTCHA**: match model column types exactly (`postgresql.UUID(as_uuid=True)`, `server_default=sa.text("now()")` for timestamps).
- **VALIDATE**: `ScriptDirectory.from_config(...).get_heads() == ["20261012_000003"]` (extend `tests/test_migrations.py`); under Docker, `alembic upgrade head` then `downgrade -1`.
- **SATISFIES**: AC 3

### CREATE backend/app/repositories/credential_repository.py, UPDATE repositories/__init__.py

- **IMPLEMENT**: `CredentialRepository(session)`: `get(user_id, provider)`, `list_for_user(user_id)`, `upsert(user_id, provider, *, api_key_encrypted, key_hint, base_url, replace_key: bool)` (only touches the key fields when `replace_key`), `delete(user_id, provider) -> bool`.
- **PATTERN**: `UserRepository`.
- **SATISFIES**: AC 3

### CREATE backend/app/schemas/provider_settings.py

- **IMPLEMENT**: `ProviderName = Literal["anthropic", "openai", "ollama"]`; `ProviderSaveRequest` with `api_key: SecretStr | None` (strip, 8 to 512 chars, no whitespace or control characters) and `base_url: str | None` (http or https only, host required, no embedded credentials, max 500); `ProviderStatus` (`provider`, `configured`, `key_hint`, `base_url`, `source: "user"|"server"|"none"`, `updated_at`); `ProviderTestResult` (`ok`, `error_type`, `detail`).
- **GOTCHA**: use `SecretStr` so a stray `repr` or log of the model cannot leak the key. Validator error messages must not include the input.
- **SATISFIES**: AC 4, 9

### CREATE backend/app/services/credential_service.py

- **IMPLEMENT**: `CredentialService(session, secret_box)`. `status(user_id)` returns a `ProviderStatus` for each provider (never decrypts; uses the stored hint). `resolve(user_id, provider) -> ProviderCredentials | None`: user row decrypted, else server key from settings when `ALLOW_SERVER_PROVIDER_KEYS`, else `None`. A row that fails to decrypt (rotated-out master key) logs a warning, and `status` reports `configured=false` with `needs_reentry=true` instead of raising. `save(user, provider, api_key, base_url)`: 503-style `SecretsNotConfigured` when a key is supplied and the box is unset; base URL accepted only for `ollama` and only when `user.role == "admin"` (else `PermissionError`). `delete`. `test(user_id, provider)` resolves and calls `LLMService.test_connection`.
- **GOTCHA**: `ProviderCredentials` is defined in `llm_service.py` and imported here (no reverse import).
- **VALIDATE**: `pytest tests/test_credential_service.py -q` with an in-memory fake repository.
- **SATISFIES**: AC 2, 5, 6

### UPDATE backend/app/services/llm_service.py

- **IMPLEMENT**: add `@dataclass(frozen=True) ProviderCredentials(api_key: str | None, base_url: str | None, source: str, owner: str | None)` with a `fingerprint()` method (first 12 hex of SHA-256 of the key, or `"server"`), and a `__repr__` that hides the key. Add optional `credentials` to `generate_chat_reply`, `stream_chat_reply`, `claude_model_catalog`, `allowed_claude_models`, `list_models`, `provider_health`. `_anthropic_client` uses `credentials.api_key` when given, else the server key. `_ollama_client` and the probe client use `credentials.base_url` or `settings.OLLAMA_URL` and send `Authorization: Bearer <key>` when an Ollama key exists. `_model_cache` becomes a dict keyed by fingerprint. `_failure_count` and `_circuit_open_until` are keyed `f"{provider}:{fingerprint}"` through one `_breaker_key` helper; the public breaker functions take the credentials. Add `async test_connection(provider, credentials) -> dict` (Claude: `models.list` with a 10 s timeout and no retries; Ollama: `GET /api/tags`; OpenAI: `{"ok": false, "error_type": "provider_not_supported"}`); it never raises and never includes the key in `detail`.
- **GOTCHA**: when credentials are `None`, behavior must equal today's, so existing tests pass. Do not put a key in any log line, exception message, or cache key. Re-verify the Ollama Cloud header and model-name rule before coding.
- **VALIDATE**: `pytest tests/test_llm_service.py -q` (existing plus new).
- **SATISFIES**: AC 5, 6, 7

### CREATE backend/app/api/v1/endpoints/provider_settings.py, UPDATE api/v1/__init__.py, api/deps.py

- **IMPLEMENT**: dependency `get_credential_service` in `deps.py`. Router prefix `/settings/providers`: `GET ""` (statuses), `PUT "/{provider}"`, `DELETE "/{provider}"` (204), `POST "/{provider}/test"`. All require `get_current_user`. Responses set `Cache-Control: no-store`. Map `SecretsNotConfigured` to 503 with a message saying how to set the master key, `PermissionError` to 403, unknown provider to 404. Log `provider_credential_saved` / `_deleted` with user id and provider only.
- **PATTERN**: `endpoints/users.py`, router registration in `api/v1/__init__.py`.
- **SATISFIES**: AC 4, 5, 8

### UPDATE backend/app/api/v1/endpoints/chat.py

- **IMPLEMENT**: inject the credential service; resolve credentials per provider for the conversation's model and pass them to `generate_chat_reply` and `stream_chat_reply`; `_resolve_model` takes the caller's Anthropic credentials for the catalog check; `list_chat_models` and `provider_health` gain `Depends(get_current_user)` and the caller's credentials.
- **GOTCHA**: keep the 400 text "Unsupported Anthropic model. Allowed: ..." and the response shapes. Update fakes in `test_chat_endpoints.py` and `test_chat_history.py` to accept `credentials`.
- **SATISFIES**: AC 7, 8

### UPDATE backend/app/main.py

- **IMPLEMENT**: `validation_error_handler` returns each error without `input`, `ctx` and `url`.
- **VALIDATE**: `pytest tests/test_key_hygiene.py -q`
- **SATISFIES**: AC 9

### Tests (backend)

- `test_secret_box.py`: round trip; ciphertext does not contain the plaintext; wrong context rejected; rotation (token made with the old key decrypts when the new key is first, old key second; fails when old key removed); unset box raises `SecretsNotConfigured`; invalid configured key error text does not contain the key.
- `test_credential_service.py`: resolve order user, server, none; `ALLOW_SERVER_PROVIDER_KEYS=false`; hint is the last four characters; non-admin base URL rejected; undecryptable row reported as needs re-entry.
- `test_provider_settings_endpoints.py`: GET and PUT responses contain no key or ciphertext; PUT with the box unset returns 503; non-admin base URL returns 403; invalid URL scheme returns 422 and the body does not contain the submitted key; DELETE then GET shows unconfigured; `test` maps results; every route returns 401 without a token.
- `test_llm_service.py` additions: user key reaches the Anthropic client factory; two keys get separate catalogs; user A's failures do not open user B's circuit; Ollama request carries the Bearer header and the custom base URL; `test_connection` for Claude and Ollama, including auth failure, with no key in `detail`.
- `test_key_hygiene.py`: with a sentinel key, capture every loguru message and every response body across save, test and a failing chat turn, and assert the sentinel never appears; assert `repr()` of `ProviderCredentials` and the save request hides it; `/chat/models` and `/chat/providers/health` return 401 without a token.
- `test_migrations.py`: single head equals the new revision.
- `test_provider_credentials_integration.py` (Docker-only, `RUN_DB_INTEGRATION_TESTS=1`): real DB round trip and the unique constraint.

### UPDATE frontend/src/api/settings.js and frontend/src/pages/Settings.jsx

- **IMPLEMENT**: API functions `listProviders`, `saveProvider(provider, { apiKey, baseUrl })`, `deleteProvider`, `testProvider`. In `Settings.jsx` remove the Claude and Ollama `localStorage` reads and writes. Key inputs start empty and are never filled from the server; a saved key shows its hint (`••••abcd`) and a Saved badge, with Save, Test and Remove buttons. The Ollama URL field renders only for `user.role === "admin"`. When a provider's `source` is `server`, show "Using the server-wide key". A banner appears if `localStorage` still holds `claude_api_key`, `ollama_api_key` or `ollama_url`: "Move to server" saves them, then removes the browser copies; after any successful save the matching browser keys are removed anyway.
- **GOTCHA**: the profile and password handlers are broken (bug 11); do not touch or "fix" them here. Keep the Ollama "Default Models" field behavior as is. Do not log a key in the console.
- **PATTERN**: existing `toast`, `FormField`, `StatusBadge` components in `Settings.jsx`.
- **VALIDATE**: `cd frontend && npm run lint && npm run build`
- **SATISFIES**: AC 10

### UPDATE docs, .env.template, docker-compose.yml, README.md, progress.md, spec.md

- **IMPLEMENT**: `.env.template` and compose pass-through for `SECRETS_ENCRYPTION_KEY` and `ALLOW_SERVER_PROVIDER_KEYS`, with the one-line generator `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` in a comment. README section "Where your API keys live": the master key goes in the local env file (git-ignored), provider keys are entered in the app and stored encrypted in the database, back up the master key (losing it means re-entering keys), use HTTPS off localhost. Update `progress.md` (bug 3, 12, 13) and `spec.md` 3.2.
- **VALIDATE**: `docker compose config >/dev/null`; `git grep` shows no key-shaped strings.
- **SATISFIES**: AC 11

---

## TESTING STRATEGY

### Unit Tests
The files listed above; all use fakes and in-memory repositories, no network and no database.

### Integration Tests
`test_provider_credentials_integration.py` and `alembic upgrade head` / `downgrade -1` under Docker; not runnable in cloud sessions, so they are reported as not run.

### Edge Cases
Master key unset; master key rotated (old key second); master key removed (undecryptable row); same user saving twice (upsert); PUT with only a base URL; PUT with an empty or too-short key; very long key; unknown provider name; viewer role; key with surrounding whitespace; two users with different Claude keys using the model list at once; server key present and user key absent; `ALLOW_SERVER_PROVIDER_KEYS=false` with only a server key.

---

## VALIDATION COMMANDS

### Level 1: Syntax and style
`.venv-be/bin/ruff check backend/app backend/tests` and `cd frontend && npm run lint && npm run build`

### Level 2: Unit tests
`cd backend && ../.venv-be/bin/python -m pytest -q --no-header -p no:cacheprovider -W ignore` (baseline 87 passed, 14 skipped, the same 4 environment failures)

### Level 3: Integration tests
`make test-backend` and `alembic upgrade head` where a Docker daemon exists; otherwise recorded as not run.

### Level 4: Manual validation (owner, on a machine with Docker)
Generate a master key, put it in the local env file, `docker compose up -d --build`, log in as admin, save a Claude key in Settings, press Test, start a Claude conversation, then confirm: the key is absent from the browser's `localStorage`, from `GET /settings/providers`, from the compose logs, and appears in the database only as ciphertext.

### Level 5: Review and hygiene
`ocr-review-loop` on the diff; `git grep` for key-shaped strings across all commits.

---

## ACCEPTANCE CRITERIA

- [ ] AC 1: Keys are encrypted with Fernet under `SECRETS_ENCRYPTION_KEY`; plaintext keys are never stored, logged, cached or returned.
- [ ] AC 2: With the master key unset the app starts and saving a key returns 503 with instructions; an undecryptable row is reported as needing re-entry, not as a crash.
- [ ] AC 3: A migration creates `provider_credentials` with a unique (user, provider) constraint and the head is the new revision.
- [ ] AC 4: No API response, validation error or `repr` contains a key or ciphertext, including the 422 for a rejected key.
- [ ] AC 5: Resolution order is user key, then server key (if allowed), then none; chat uses the caller's credentials.
- [ ] AC 6: Only admin users can set an Ollama base URL; others get 403.
- [ ] AC 7: Model catalogs and circuit breakers are per credential; one user's failures do not affect another.
- [ ] AC 8: `/chat/models`, `/chat/providers/health` and all `/settings/providers` routes return 401 without a token.
- [ ] AC 9: Master-key configuration errors do not echo the key.
- [ ] AC 10: Settings no longer reads or writes provider keys in browser storage; a "Move to server" path clears old browser copies.
- [ ] AC 11: Docs, env template and compose describe where keys live; no secret is committed.
- [ ] Suite: no new failures beyond the 4 known environment failures; ruff, eslint and `npm run build` pass.
- [ ] `ocr-review-loop` reports nothing at or above medium, or remaining items are listed.

## COMPLETION CHECKLIST

- [ ] Tasks completed in order, each validated
- [ ] `piv-validate` run and "Not run" items listed honestly
- [ ] `progress.md` and `spec.md` updated; plan amendments recorded below
- [ ] Commit with `piv-commit`; PR only if asked

---

## OPEN QUESTIONS / ASSUMPTIONS

- Assumed (owner chose defaults on 2026-10-12): OpenAI accepted by the API but no card yet; Fernet with a local master key; server env key as fallback; admin-only Ollama URL; per-user model list, health and a Test button; "Move to server" for browser-stored keys.
- Assumed: Ollama Cloud accepts `Authorization: Bearer <key>` at `https://ollama.com/api` and hosted model names have no `-cloud` suffix (docs.ollama.com, 2026-10-12). Verify before coding; adjust headers if the docs differ.
- Assumed: `cryptography` 50.0.2 provides `MultiFernet` with the same API as earlier versions.
- Assumed: showing the last four characters of a key is acceptable. If not, drop `key_hint` and show only "Saved".
- Not decided: whether non-admin users should be able to use Ollama Cloud (needs the server URL to point there, or a per-user URL). Deferred; today only admins set a URL.
- Risk: the Settings page has no frontend tests; correctness there rests on eslint, `npm run build` and the owner's manual check.
- Privacy: this change moves secrets, not document content; no new data goes to any provider.

## NOTES

- Why Fernet and a context envelope: Fernet gives authenticated encryption with rotation support through `MultiFernet`, no new dependency, and no custom crypto. It has no associated-data field, so the owner and provider go inside the encrypted envelope and are checked on decrypt; this stops a database-level row copy from being replayed under another user.
- Why a key is never returned: even the owner's browser should not be able to read back a stored key; rotating means re-entering it. The cost is one extra paste; the benefit is that a stolen session token cannot exfiltrate provider keys.
- Why per-credential breakers: today one circuit per provider would let a single bad key lock out every user.
- Confidence for one-pass success: 6/10. Largest risks are the breadth (about 20 files), the `LLMService` signature changes touching many tests, and frontend changes without a test runner.

## AMENDMENTS

- (none yet)
