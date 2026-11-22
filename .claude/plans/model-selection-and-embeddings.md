# Feature: Model selection in Settings, Ollama Cloud, and selectable embedding models

Builds on `.claude/plans/llm-provider-interface-openai.md` (ticket A) and `.claude/plans/memory-provider-builtin.md`.
Recommended order: A, then Part 1, then Part 2. Part 2 does not depend on Part 1 and can be done first if embeddings matter more.

## Feature Description

The owner wants to choose, in Settings, which models the system uses:

1. **Agent models**: OpenAI, Claude, Ollama (local) and Ollama Cloud as provider choices; a per-user list of models to show and a default model.
2. **Embedding model**: the model that turns documents into vectors, served by the bundled TEI container, a local Ollama, or Ollama Cloud, chosen by an admin and applied to the whole system, with a re-index step when it changes.

## User Story

As the owner (and, for embeddings, an admin)
I want to pick my agent models and my embedding model in Settings, using local Ollama or Ollama Cloud where I like
So that the system uses exactly the models I chose and my documents are embedded where I decided.

## Problem Statement

- Model choice is a flat dropdown of whatever each provider lists; there is no default and no way to hide the many OpenAI models.
- Ollama Cloud cannot be used by regular users: the Ollama URL is admin-only and global, and the cloud URL needs a key plus a different base URL.
- A conversation stores only a model string. Local and cloud Ollama share model names (for example `gpt-oss`), and `gpt-` also prefixes OpenAI models, so the provider cannot be told from the name (ticket A's routing heuristic is a stop-gap; its plan lists this as a risk).
- Embeddings are hard-wired to TEI (`EMBEDDING_URL`) and one collection with a fixed `EMBEDDING_DIM`. Changing the model silently breaks search: vectors from different models are not comparable, and Ollama's own docs say to "use the same embedding model for both indexing and querying".

## Solution Statement

**Part 1: model selection**
- New provider id `ollama_cloud`: fixed base URL `https://ollama.com`, per-user API key, no editable URL (so no server-side request forgery risk), `Authorization: Bearer <key>`. The existing `ollama` provider stays local (`OLLAMA_URL`, admin-set).
- Conversations store `provider` (new nullable column). The model dropdown sends provider and model. Old rows with no provider use ticket A's routing heuristic.
- New table `user_model_preferences` (`user_id`, `default_provider`, `default_model`, `enabled_models` JSON, nullable = all). `GET/PUT /settings/models` returns the user's live catalog grouped by provider plus preferences; saving validates against the catalog.
- Settings gets a "Models" section: provider connection cards (existing, plus OpenAI and Ollama Cloud), then a checklist of models per provider and a default model.

**Part 2: embeddings**
- `EmbeddingProvider` interface in `services/memory/embeddings.py` with `tei`, `ollama` and `ollama_cloud` implementations (`embed(texts)`, `probe()` returns the vector size, `health()`), used by `BuiltinMemoryProvider` instead of its inline TEI call.
- New table `system_settings` (`key`, `value` JSON, `secret_encrypted`, `updated_by`, `updated_at`) holding `embedding` config: provider, model, base URL (local Ollama only, admin), optional key (encrypted with `SecretBox`, context `system:embedding`). Admin-only `GET/PUT /settings/embedding`, `POST /settings/embedding/test`. Environment variables remain the bootstrap defaults (`EMBEDDING_PROVIDER=tei`).
- The active vector collection is named from the embedding identity: `<QDRANT_COLLECTION>__<provider>__<model-slug>__<dim>`. The dimension comes from a real probe, not a setting. Switching models points search at a new, empty collection until documents are re-indexed; the old collection is left alone.
- Re-index: admin `POST /memory/reindex` runs a background job that re-embeds the stored chunks from Postgres (no re-parsing) into the active collection, with progress in `system_settings` and in `GET /memory/health`. It also fixes the known gap of documents uploaded while vectors were off.
- Documents record which embedding identity indexed them (`metadata.vector_index`); health says how many documents are not yet in the active index.

## Out of Scope / Non-Goals

- Not included: the SMC adapter, Laya, the sensitivity gate and the privacy-policy control (spec 3.2). Until the gate exists, nothing stops a user from sending sensitive text to a cloud provider they enabled; the UI says plainly when a choice sends document text off the machine.
- Not included: multiple embedding models at once, per-user embedding models, deleting old collections (shown in health as unused; manual cleanup).
- Not included: OpenAI embeddings (can be added as another `EmbeddingProvider` later), image/audio embeddings.
- Not included: a model benchmark or automatic model recommendations.
- Not changing: `MemoryProvider` interface shape, keyword search, chunking, the SMC sanitizer step, the secret box, existing key storage.

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: High
**Primary Systems Affected**: LLM registry (new provider id), conversations (column), credentials, memory (embeddings and re-index), new settings endpoints, Settings and Chat pages, 2 migrations (or 1 with three changes)
**Dependencies**: none new (Ollama is plain HTTP through `httpx`)

## Related Work

**Implements**: owner request 2026-11-21 (models chosen in Settings; embeddings via Ollama Cloud or local Ollama)   ·   **Epic**: `spec.md` 3.1, 3.2, 5

**Back-references**:
- `.claude/plans/llm-provider-interface-openai.md` - registry and adapters this extends
- `.claude/plans/memory-provider-builtin.md` - `BuiltinMemoryProvider`, health, status record
- `.claude/plans/server-side-provider-keys.md` - `SecretBox`, `ProviderCredentials`, `/settings/providers`

**Forward-references**:
- 2026-11-22 - Part 1 uses its own migration `20261122_000004` (provider on conversations, `user_model_preferences`). `system_settings` moves to Part 2's migration, because nothing in Part 1 needs it.
- 2026-11-22 - Preferences live in `model_preference_repository.py` and `model_settings_service.py` (not a shared `settings_repository.py`). Adapters gained a `label` so the Settings list needs no provider names.
- 2026-11-22 - `/chat/models` returns only enabled models and `?all=true` everything; the Settings provider cards use the full list. A provider with every model on is omitted from the saved state, so models it lists later are on by default.
- 2026-11-22 - Ollama Cloud models are validated against the live list, except when the list comes back empty (a failed listing), where the chat call reports the real error.
- 2026-11-22 - The chat dropdown's popup was clipped by the composer card and transparent (`bg-surface-card` is undefined); fixed for the model list only.
- 2026-11-22 - Part 2: re-index state lives in `system_settings["reindex"]` through `put_value`; a job with no progress for 5 minutes is reported `stalled` and may be taken over; a job where nothing succeeded ends `failed`; three failures in a row stop it early.
- 2026-11-22 - Part 2: the 64 to 8192 vector-size check applies when choosing a model (probe), not to everyday health checks. A model's size is part of the index identity and is measured, never configured (TEI's `EMBEDDING_DIM` only seeds the environment default).
- 2026-11-22 - Part 2: `vector_id` on chunks is not updated by re-indexing: point ids are deterministic (uuid5 of document and chunk), so nothing reads it.
- 2026-11-22 - Part 2: found by the live run and fixed: concurrent first uploads raced to create the collection and the losers got HTTP 409; a 409 on create now means "use it" (after the size check).
- 2026-11-22 - Live runs had to point the cloud address at a stand-in server by patching the module constant in the test runner; the address is deliberately not configurable in the app.

---

## CONTEXT REFERENCES

### Relevant Codebase Files (read before implementing)

- `backend/app/services/memory/builtin.py` - `_embed_texts` (TEI call), `_ensure_collection`, `_probe_embeddings`, status record, `_describe` error vocabulary
- `backend/app/core/config.py` (lines 33-55) - `QDRANT_COLLECTION`, `EMBEDDING_*`
- `backend/app/services/llm/` (from ticket A) - registry, `ollama.py` (`_ollama_base_url`, headers, tags listing)
- `backend/app/services/credential_service.py`, `schemas/provider_settings.py`, `endpoints/provider_settings.py` - provider ids and key storage
- `backend/app/models/conversation.py`, `repositories/chat_repository.py`, `endpoints/chat.py` (`create_conversation`, `_resolve_model`)
- `backend/app/core/secret_box.py` - encryption with a context string
- `backend/alembic/versions/20261012_000003_provider_credentials.py` - migration pattern; `tests/test_migrations.py`
- `backend/app/api/deps.py` - dependencies; admin check pattern in `provider_settings.py`
- `frontend/src/pages/Settings.jsx`, `components/ProviderKeyFields.jsx`, `components/MemoryStatusCard.jsx`, `pages/Chat.jsx` (dropdown), `api/chat.js`, `api/settings.js`

### New Files to Create

- `backend/app/models/system_setting.py`, `backend/app/models/user_model_preference.py`
- `backend/alembic/versions/20261121_000004_model_selection_and_embedding_settings.py`
- `backend/app/services/memory/embeddings.py`, `backend/app/services/memory/reindex.py`
- `backend/app/repositories/settings_repository.py` (system settings and preferences)
- `backend/app/services/model_settings_service.py`, `backend/app/services/embedding_settings_service.py`
- `backend/app/schemas/model_settings.py`, `backend/app/schemas/embedding_settings.py`
- `backend/app/api/v1/endpoints/model_settings.py`, `embedding_settings.py`; reindex route in `endpoints/memory.py`
- `frontend/src/components/ModelSelection.jsx`, `EmbeddingSettingsCard.jsx`, `api/models.js`, hooks
- Tests: `test_embedding_providers.py`, `test_embedding_settings.py`, `test_reindex.py`, `test_model_settings.py`, `test_ollama_cloud.py`, migration additions

### Relevant Documentation

Read from Ollama's own docs in its GitHub repository (`docs/api.md`, `docs/api/authentication.mdx`, `docs/capabilities/embeddings.mdx`, `docs/cloud/faq.mdx`), because `ollama.com` was not reachable from the planning environment:
- `POST /api/embed` with `{"model", "input": string | [string]}` returns `{"model", "embeddings": [[...]], ...}`. Optional `truncate` (default true), `dimensions`, `keep_alive`. Vectors are L2-normalized. Vector length depends on the model (typically 384 to 1024).
- Cloud: direct inference at `https://ollama.com/api` needs an API key sent as `Authorization: Bearer <key>`; the local API at `http://localhost:11434` needs none. API keys do not expire.
- "Use the same embedding model for both indexing and querying."
- `POST /api/show` returns `capabilities` (the docs example shows `["completion", "vision"]`) and `model_info` with an `*.embedding_length` entry. Model names are `model:tag`; the tag is optional and defaults to `latest`.
- Ollama cloud data handling (cloud FAQ): "Ollama operates with a zero data retention (ZDR) policy... does not store or log that content and never trains on it." This is Ollama's statement; the UI may quote the policy's existence, not guarantee it.
- **Not verified**: whether Ollama Cloud serves any embedding models (the cloud docs do not mention them), the exact capability string for embedding models in `/api/show`, and whether cloud supports the `dimensions` parameter. The design therefore proves a choice by really embedding a test string (`probe`) instead of trusting names or capability flags.

### Patterns to Follow

- Interface plus registry plus structured outcome (`memory/base.py`, `llm/base.py`); fixed safe error strings (`_describe`, `_TEST_DETAIL`); no keys in logs or results.
- Secrets: encrypt with `SecretBox.encrypt(value, context=...)`; return only a hint (last four characters); never echo a key.
- Admin-only routes: same check as `provider_settings` (role == "admin" -> 403 otherwise).
- Status and progress shown through `GET /memory/health` (extend, do not fork).

---

## IMPLEMENTATION PLAN

### Part 1: Model selection

#### Phase 1.1: Provider `ollama_cloud` and `conversations.provider`
Depends on ticket A. Add the adapter (a thin subclass or configuration of the Ollama adapter with fixed base URL and bearer key), register it, flip it supported, migration for `conversations.provider`.

#### Phase 1.2: Preferences and catalog endpoint
**Depends on:** 1.1. `user_model_preferences`, `ModelSettingsService`, `GET/PUT /settings/models`.

#### Phase 1.3: Chat integration and UI
**Depends on:** 1.2. Create/send use the stored provider; dropdown filtered by enabled models; Settings "Models" section.

### Part 2: Embeddings (independent of Part 1)

#### Phase 2.1: `EmbeddingProvider` implementations and identity
`tei`, `ollama`, `ollama_cloud`; probe; collection naming.

#### Phase 2.2: System settings storage and endpoints
**Depends on:** 2.1. `system_settings`, admin endpoints, test (probe) and apply.

#### Phase 2.3: `BuiltinMemoryProvider` uses the active embedding config; re-index job; health
**Depends on:** 2.2.

#### Phase 2.4: Settings UI (embedding card, re-index button and progress)

### Phase 3: Tests, docs, validation (both parts)

---

## STEP-BY-STEP TASKS

### CREATE migration 20261121_000004 and models
- **IMPLEMENT**: add `conversations.provider String(20) NULL`; create `user_model_preferences(user_id PK FK users on delete cascade, default_provider String(20) NULL, default_model String(100) NULL, enabled_models JSONB NULL, updated_at)`; create `system_settings(key String(64) PK, value JSONB, secret_encrypted Text NULL, updated_by UUID NULL FK users on delete set null, updated_at)`. Register models in `app/models/__init__.py`.
- **PATTERN**: `20261012_000003_provider_credentials.py` and `tests/test_migrations.py` (add the new revision to the chain test).
- **GOTCHA**: backfill is not needed (NULL means "infer from the model name"). Do not add a server default.
- **VALIDATE**: `cd backend && ../.venv-be/bin/python -m pytest tests/test_migrations.py -q`, and apply on the local Postgres 16 + pgvector used in `progress.md` (2026-11-21): `AUTO_RUN_MIGRATIONS=true` boot, then `\d conversations`.
- **SATISFIES**: AC 1, 6

### CREATE ollama_cloud adapter and register it (Part 1)
- **IMPLEMENT**: provider id `ollama_cloud`; base URL constant `https://ollama.com` (not configurable); credentials require an API key; every request sends `Authorization: Bearer <key>`; model list from `/api/tags`; chat and streaming reuse the Ollama adapter code via composition. Add to `PROVIDER_IDS`, `SUPPORTED_PROVIDERS`, `ProviderName` literal, the health and model dicts, `credential_service` status (never "always available": source is `none` until a key is saved). Per-credential breaker and model cache like the others.
- **GOTCHA**: the key must never be sent to any host other than `ollama.com`; test that a custom base URL on a stored `ollama_cloud` row is ignored. Hosted model names have no `-cloud` suffix (recorded 2026-10-12); a local Ollama may list `*-cloud` names that proxy to the cloud; leave those as local entries.
- **VALIDATE**: `cd backend && ../.venv-be/bin/python -m pytest tests/test_ollama_cloud.py -q`
- **SATISFIES**: AC 2, 5

### UPDATE chat endpoints, chat repository, schemas for `provider`
- **IMPLEMENT**: `ConversationCreateRequest` accepts `provider` (optional). `_resolve_model(provider, model, credentials)` validates the pair via the registry. The conversation row stores `provider`; `LLMService.provider_for_conversation(conversation)` uses the column, falling back to ticket A's name heuristic when NULL. Responses include `provider`. When `model` is omitted, use the user's default preference, else `DEFAULT_MODEL`.
- **GOTCHA**: still no provider-name literals in endpoints (the boundary test from ticket A must stay green). A provider/model pair the user's catalog does not contain is a 400 with the allowed list, never a 500.
- **VALIDATE**: `cd backend && ../.venv-be/bin/python -m pytest tests/test_chat_endpoints.py tests/test_chat_history.py -q`
- **SATISFIES**: AC 1, 3

### CREATE model settings service and endpoints
- **IMPLEMENT**: `GET /settings/models` returns `{providers: [{id, label, configured, models: [{id, name, enabled}]}], default: {provider, model} | null}` built from `LLMService.list_models` for this user plus their preference row; `PUT /settings/models` takes `{enabled_models: {provider: [ids]} | null, default: {provider, model} | null}`, validates every id against the live catalog (unknown ids dropped with a 400 naming them), requires the default to be enabled. OpenAI is a provider entry whenever it is supported, `configured: false` with no models until a key exists.
- **GOTCHA**: a catalog fetch failure must not wipe saved preferences: keep saved ids that are not currently listed but mark them `unavailable`. Preferences are per user; never leak another user's catalog or keys.
- **VALIDATE**: `cd backend && ../.venv-be/bin/python -m pytest tests/test_model_settings.py -q`
- **SATISFIES**: AC 2, 3

### CREATE embedding providers (Part 2)
- **IMPLEMENT**: `EmbeddingConfig(provider, model, base_url, api_key)` and `EmbeddingProvider` Protocol (`async embed(texts) -> list[list[float]]`, `async probe() -> ProbeResult(dim, latency_ms)`). `TeiEmbeddings` (existing `/embed` call and `/health`), `OllamaEmbeddings` (local: `POST {base}/api/embed` with `{"model", "input": [...]}`; no key), `OllamaCloudEmbeddings` (same call to `https://ollama.com/api/embed` with the Bearer key). Batch size 32, timeouts from `EMBEDDING_TIMEOUT_SECONDS`, response validated (list of equal-length float lists, count matches input), `truncate` left at its default (true). `config.identity()` -> `"<provider>__<slug(model)>__<dim>"`; `collection_name()` appends it to `QDRANT_COLLECTION`.
- **PATTERN**: current `_embed_texts` and `_describe` in `memory/builtin.py`; move them, do not duplicate.
- **GOTCHA**: the probe embeds a fixed short string and reports the vector length; accept 64 to 8192, else a clear error. Error strings stay fixed (`Embeddings: could not connect`, `... returned HTTP 401`, `... model not found`) and never include the URL, key or text. An HTTP 404 from Ollama for the model means "model not available"; say so (this is also how a cloud account without embedding models will show up).
- **VALIDATE**: `cd backend && ../.venv-be/bin/python -m pytest tests/test_embedding_providers.py -q`
- **SATISFIES**: AC 4, 5

### CREATE system settings repository and embedding settings service/endpoints
- **IMPLEMENT**: `EmbeddingSettingsService.get()` (config without the key, plus `key_hint`, `source: "settings" | "environment"`, last probe result), `test(candidate)` (probe without saving; returns `ok`, `dim`, `latency_ms`, safe detail), `apply(candidate)` (probe first; only a successful probe is saved; encrypts the key with context `system:embedding`; records `updated_by`; returns the new identity and how many documents are not in that index). Routes `GET/PUT /settings/embedding` and `POST /settings/embedding/test`, admin only (403 otherwise). Environment bootstrap: with no saved row, `EMBEDDING_PROVIDER` (default `tei`), `EMBEDDING_URL`, `OLLAMA_EMBED_MODEL`/`EMBEDDING_MODEL`.
- **GOTCHA**: base URL is accepted only for provider `ollama` and only from an admin, validated like the Ollama URL (http/https, host, no credentials). The key is write-only. Saving a config that fails its probe must leave the old config active. `SecretsNotConfigured` -> 503 with the existing message.
- **VALIDATE**: `cd backend && ../.venv-be/bin/python -m pytest tests/test_embedding_settings.py -q`
- **SATISFIES**: AC 4, 5, 6

### UPDATE services/memory/builtin.py and health
- **IMPLEMENT**: resolve the active `EmbeddingConfig` once per call from settings (short in-process cache invalidated on apply); use its provider for ingest, query embedding and the health probe; use `collection_name()` for every Qdrant call; replace the `EMBEDDING_DIM` mismatch check with the identity (collection size is checked against the probed dimension). Ingest records `metadata.vector_index = identity` on the document. Search uses only the active collection. Health adds `embedding: {provider, model, dim}`, `documents_total`, `documents_in_index`, and the re-index job state.
- **GOTCHA**: a query must be embedded with the same config as the active collection, or results are meaningless; if the active config cannot be loaded, fall back to keyword search with `keyword_fallback`. Keep point ids as uuid5 of document and chunk (identical across collections, so re-indexing is idempotent).
- **VALIDATE**: `cd backend && ../.venv-be/bin/python -m pytest tests/test_memory_provider.py -q` (existing 32 tests stay, retargeted to the new embedder seam)
- **SATISFIES**: AC 4, 7

### CREATE re-index job
- **IMPLEMENT**: `POST /memory/reindex` (admin) starts a background task: for each completed document (ordered by id), read its chunks from Postgres, embed in batches, upsert into the active collection, update `metadata.vector_index`; progress `{state: idle|running|done|failed, total, done, failed, started_at, finished_at}` in `system_settings["reindex"]`, updated per document. One job at a time: a second `POST` while running returns 409; a `running` state with no update for 5 minutes counts as dead and may be restarted. Continue past a failed document and count it; surface the first safe error string.
- **GOTCHA**: runs in the API process (single worker today); say so in the notes. Keep a user's chunks and vectors together (payload `user_id` from the document owner). Never log chunk text. Cancel is out of scope.
- **VALIDATE**: `cd backend && ../.venv-be/bin/python -m pytest tests/test_reindex.py -q`
- **SATISFIES**: AC 7

### UPDATE frontend: Settings and Chat
- **IMPLEMENT**: `ModelSelection.jsx`: per-provider groups with checkboxes and a default selector, OpenAI and Ollama Cloud included with "Add a key" prompts when not configured; saves through `PUT /settings/models`. `EmbeddingSettingsCard.jsx`: provider (TEI / Ollama / Ollama Cloud), model (typed, with suggestions from the provider's list), URL (local Ollama, admin), key (write-only), **Test** (shows dimension and latency), **Apply**, **Re-index documents** with a progress bar from health; non-admins see the current choice read-only. A visible notice when the choice sends document text off the machine: "Document text is sent to Ollama Cloud to be embedded" (cloud) and none for TEI/local. Chat dropdown shows enabled models, grouped by provider, sends `provider` and `model`, and new conversations start on the default.
- **GOTCHA**: no key prefill, ever; do not touch the profile/password handlers (bug 11). Keep existing `ProviderKeyFields` for the provider cards. No console logging of response bodies.
- **VALIDATE**: `cd frontend && npm run lint && npm run build`
- **SATISFIES**: AC 2, 3, 4, 8

### UPDATE config, compose, env template, README, spec, progress
- **ADD**: `EMBEDDING_PROVIDER=tei|ollama|ollama_cloud`, `OLLAMA_EMBED_MODEL`; document that the cloud key is entered in Settings (not the environment). README: model selection, embedding choices, what leaves the machine for each, re-index after changing the model, "Ollama's cloud docs state zero data retention; read them yourself" (a pointer, not a promise). `spec.md` 3.1/3.2/5 and `progress.md`.
- **VALIDATE**: `grep -n "ollama_cloud\|EMBEDDING_PROVIDER" README.md .env.template docker-compose.yml`

### CREATE tests
- Embedding providers: request bodies and headers for each provider (`/embed` for TEI; `/api/embed` with `model` and `input` list for Ollama; Bearer only on the cloud host), batching, response validation (wrong count, ragged vectors, non-floats), probe dimension and range, error strings with no URL/key/text.
- Embedding settings: admin only (403 for users), failed probe keeps the old config, key encrypted (ciphertext differs from the key; hint is last four), key never in any response or log, base URL rules, environment bootstrap, identity/collection naming (slug safe characters, dimension included).
- Memory: after switching identity, old vectors are not returned; search embeds with the active config; health counts documents not in the index.
- Re-index: processes all documents, idempotent re-run, failure of one document counted and skipped, 409 on a concurrent start, stale `running` restartable, per-user payloads preserved.
- Model settings: catalog grouping, OpenAI entry without a key, validation of unknown ids, default must be enabled, saved ids kept as `unavailable` when the catalog call fails, user isolation.
- Ollama Cloud: key sent only to `ollama.com`, stored base URL ignored, per-credential breaker and cache.
- Migrations: new revision chain; **integration** (run by hand against local Postgres) for the three schema changes.
- **VALIDATE**: `cd backend && ../.venv-be/bin/python -m pytest -q`

---

## TESTING STRATEGY

### Unit
As above, with fake HTTP transports (`httpx.MockTransport`) and the real in-memory Qdrant client used in the memory provider tests.

### Integration (by hand, no Docker daemon here)
Local Postgres 16 + pgvector, Redis, Qdrant 1.12.5 and a stand-in embedding server that speaks both TEI (`/embed`) and Ollama (`/api/embed`). Walk: save an embedding config (probe reports a dimension), upload, search (vector), switch to a second model with a different dimension (search falls back until re-index), run re-index, search again; stop the embedding server and confirm the fallback and health text. Headless Chromium on the Settings page for the embedding card and the model checklist. A real Ollama Cloud call needs the owner's key and `ollama.com` reachable; not possible in the cloud container.

### Edge Cases
Embedding model returns a different dimension than the probe; a model that exists locally but is not an embedding model (the probe error is clear); non-admin opens the embedding card; two admins save at once (last write wins, `updated_by` recorded); switching back to a previous identity reuses its old collection; a document with zero chunks; re-index while uploads arrive (new uploads index into the active collection directly); the cloud key revoked mid-job (job fails fast with `provider_auth_error`, counted, state `failed`).

---

## VALIDATION COMMANDS

Use the `piv-validate` skill. Native venv `.venv-be`.

### Level 1: `ruff check app tests`; `npm run lint`
### Level 2: `python -m pytest -q` (only the 4 known `postgres`-host failures allowed)
### Level 3: `npm run build`; migrations on real Postgres
### Level 4: manual walk above
### Level 5: Mutation checks: (a) Bearer key sent to a non-cloud host, (b) stored cloud base URL honoured, (c) key echoed in a response, (d) non-admin allowed to apply, (e) failed probe still saved, (f) collection name ignores dimension, (g) query embedded with a different config than the collection, (h) re-index skips the user filter, (i) concurrent re-index allowed, (j) catalog failure wipes preferences, (k) default model not required to be enabled, (l) provider literal added to an endpoint; each must fail a test.

---

## ACCEPTANCE CRITERIA

- [ ] AC 1: Conversations store their provider; old rows still work; migration applies on a clean and an existing database.
- [ ] AC 2: Settings shows OpenAI, Claude, Ollama and Ollama Cloud as provider choices; each user chooses which models are enabled and a default; the chat dropdown honours it.
- [ ] AC 3: A provider/model pair outside the user's catalog is a 400 with a clear message; a conversation always runs on the provider it was created with.
- [ ] AC 4: An admin can choose TEI, local Ollama or Ollama Cloud for embeddings, test the choice (real probe with dimension), and apply it; a failing choice is never saved.
- [ ] AC 5: The Ollama Cloud key is sent only to `ollama.com`, stored encrypted, write-only, never logged or returned.
- [ ] AC 6: Non-admins cannot change system settings; keys and settings are never exposed to other users.
- [ ] AC 7: Changing the embedding model never returns mismatched results: search uses the active index only, health reports documents not yet in it, and re-index brings them in; progress is visible.
- [ ] AC 8: The UI says when a choice sends document text off the machine; the default stays local (TEI).
- [ ] No new test failures; mutation checks all caught; docs updated.

## COMPLETION CHECKLIST

- [ ] Tasks done in order, each validated
- [ ] `piv-validate` run; "Not run" listed honestly
- [ ] Review loop (`ocr-review-loop`) run, findings fixed
- [ ] Report written to `.claude/reports/model-selection-and-embeddings-report.md`
- [ ] Commit with `piv-commit`; no PR unless asked

---

## OPEN QUESTIONS / ASSUMPTIONS

Defaults assumed (owner said not to stop for questions); confirm later:

- **Unverified and important**: that Ollama Cloud serves an embedding model. Ollama's cloud docs do not mention embeddings and `ollama.com` was blocked from the planning environment. The design does not depend on it: the Test button really embeds a string and reports the result, and local Ollama and TEI remain choices. If cloud has no embedding model, the owner's plan becomes "embeddings on local Ollama or TEI, agent on Ollama Cloud".
- Assumed - embeddings are a system-wide, admin-only choice (one vector space for all users), stored in the database with an encrypted key; environment variables only bootstrap it. A per-user embedding model would need one collection per user; out of scope.
- Assumed - Ollama Cloud is a separate provider id from local Ollama, because the two share model names and need different base URLs and keys; users cannot set a URL for it (no request forgery surface).
- Assumed - a `provider` column on conversations replaces name-based routing; the name heuristic from ticket A remains only for old rows.
- Assumed - enabled-model lists are per user and default to "all"; a long OpenAI list is the reason this exists.
- Assumed - the default embedding choice stays TEI (local, works from `docker compose up`); cloud embedding is opt-in and clearly labelled.
- Assumed - re-index runs inside the API process (single uvicorn worker), with progress in the database. If workers are added, use a real task queue.
- Assumed - the cloud embedding key is entered separately from the user's own Ollama Cloud key, because background indexing cannot use one specific user's key.
- Assumed - the vector size must be 64 to 8192; Ollama's docs say 384 to 1024 is typical.
- Not decided - what to do with abandoned collections after a model switch (kept; shown in health). A cleanup action is a follow-up.

## NOTES

- Why probe instead of trusting model names or `capabilities`: the docs example for `/api/show` does not show an embedding capability, and cloud availability is unverified. A real call is the only proof.
- Why identity-named collections: Qdrant fixes vector size per collection and vectors from different models are not comparable, so mixing them in one collection produces silent nonsense. Separate collections make a switch safe and reversible.
- Why re-index from stored chunks: the text is already in Postgres, so changing models costs embedding time, not parsing or SMC sanitizing again.
- Risks: breadth (three schema changes, two admin surfaces, a background job), no real Ollama Cloud call possible here, and the interplay with ticket A's refactor (do A first).
- Confidence for one-pass success: Part 1 7/10, Part 2 6/10.

## AMENDMENTS

- (none yet)
