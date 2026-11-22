# Progress

Last updated: 2026-10-08 · Spec: [`spec.md`](spec.md)

Update this file at the end of every working session: move items between sections, add the date, and write the next step so the following session can start cold.

## Where we left off

2026-10-14: bug 3 ticket (server-side encrypted provider keys + Settings page, also bugs 12 and 13) implemented on this branch, unit-tested only. Plan: `.claude/plans/server-side-provider-keys.md`. Owner still has to: clone, generate `SECRETS_ENCRYPTION_KEY` into the local env file, run with Docker (migration `20261012_000003`), save a key in Settings, press Test, and chat. Next ticket: `LLMProvider` interface + OpenAI adapter. Laya runs on the owner's VPS already; the `DecisionService` client needs its API shape, port, auth and TLS details.

2026-11-21: clean-clone check, run natively (no Docker daemon in the cloud container). Found and fixed two blockers a fresh download hit: the production frontend build failed (themed colours were plain CSS variables, so `bg-dark-elevated/40` could not compile) and a fresh stack had no tables (`AUTO_RUN_MIGRATIONS` defaulted to false). Verified on a fresh clone with real Postgres 16 + pgvector and Redis: all three migrations run, admin is created, login works, a key saves encrypted (`gAAAA...` in the row, hint shown), unauthenticated `/chat/models` returns 401, a document uploads and is found by keyword search, chat answers from it (canned excerpt, no LLM was reachable). In headless Chromium the Settings page showed the Saved badge, the Move-to-server banner deleted the browser copy, and the console was clean.

Still not run: `docker compose up` itself (image builds, nginx, TEI, Qdrant), a real Claude or Ollama reply, vector search (needs Qdrant + TEI), streaming in the browser. Known cosmetic issue: the Ollama card says "Using the server-wide key" even when no key is set, and the Claude badge says "Not Configured" after a saved key that fails its test.

The owner deleted their local copy of the repo; the only copy is on GitHub, branch `claude/festive-hamilton-e2cy6w` (not merged into `master`, no PR opened). To work locally: clone, check out that branch, copy the env template to a local env file (git-ignored) and fill it in there. No key is ever committed; a scan of every commit on every branch found no key-shaped strings.

2026-11-21 (later): `MemoryProvider` with a default-on `builtin` backend is implemented (plan: `.claude/plans/memory-provider-builtin.md`), unit-tested and run by hand against real Postgres, Redis and Qdrant with a stand-in embedding service. Not run: Docker, the real TEI image, a real Claude or Ollama reply. Next step: owner runs `docker compose up` on a clean clone, then the `LLMProvider` interface and OpenAI adapter.

2026-11-21 (latest): planned the `LLMProvider` interface and OpenAI adapter in `.claude/plans/llm-provider-interface-openai.md`. API facts came from the installed `openai` 3.57.0 SDK source because OpenAI's docs hosts were blocked; data-retention wording and the Chat Completions status are unverified (listed in the plan). Notable: OpenAI's `store` defaults to true (30+ days), so the adapter must always send `store=False`. Implemented 2026-11-21, see the next paragraph. Owner decision: the SMC adapter comes last.

2026-11-21 (model selection): owner wants OpenAI among the provider choices in Settings, a way to select the models in use, and embeddings served by Ollama (Cloud or local). Planned in `.claude/plans/model-selection-and-embeddings.md`: `ollama_cloud` provider, `provider` stored on conversations, per-user enabled models and default, admin-chosen embedding provider/model with a real probe, identity-named Qdrant collections and a re-index job. Unverified: whether Ollama Cloud serves embedding models (`ollama.com` blocked here). Order: LLMProvider/OpenAI plan, then Part 1, then Part 2.

2026-11-22 (model selection, Part 2): implemented: an admin chooses the embedding model (TEI, local Ollama, Ollama Cloud) in Settings > Memory; a choice is saved only after a real probe; each (provider, model, vector size) has its own Qdrant collection; **Re-index documents** re-embeds stored chunks in the background with progress. Unit-tested and run by hand against real Postgres 16, Qdrant 1.12.5 and stand-in embedding servers (TEI at 1024, local Ollama at 768, cloud at 512). The live run found and fixed a real bug: concurrent uploads racing to create the first collection got Qdrant's HTTP 409 and silently skipped vector indexing. Not run: a real Ollama Cloud embedding call (`ollama.com` unreachable here; it is still unverified that Cloud serves any embedding model), real TEI, Docker. Next step: owner tries Test with a real Ollama key; then the remaining roadmap (decision layer, SMC adapter last).

2026-11-22 (model selection, Part 1): implemented (plan: `.claude/plans/model-selection-and-embeddings.md`, Part 1): a `provider` stored on each conversation, Ollama Cloud as its own provider, per-user enabled models and default (`/settings/models`), a Models section in Settings and provider groups in the chat dropdown. Unit-tested and run by hand against real Postgres (migration up, down and up again on a database with existing conversations) with stand-in local and cloud Ollama servers that both list `gpt-oss:20b`. Not run: a real Ollama Cloud call (`ollama.com` is not reachable from the cloud container; needs the owner's key), Docker. Next step: owner tries Ollama Cloud with a real key, then Part 2 (embedding model selection and re-index).

2026-11-21 (OpenAI): the `LLMProvider` interface, registry and OpenAI adapter are implemented (plan: `.claude/plans/llm-provider-interface-openai.md`), unit-tested and run by hand against the real `openai` 3.57.0 SDK talking to a stand-in server that speaks the Responses streaming format. Not run: a real OpenAI call (needs the owner's key), Docker, Python 3.11 (tests ran on 3.13; the image uses 3.11 and both `openai` and `httpx2` allow it). Next step: owner tries a real OpenAI chat, then `.claude/plans/model-selection-and-embeddings.md` (Part 1, then Part 2).

## Done (in the code today)

- FastAPI backend: auth (JWT sessions), users, documents (upload, parse, chunk, list, delete), keyword + vector search, chat conversations and messages (pagination, titles, delete), SSE streaming, citations with snippets and spans, token accounting.
- Postgres schema with Alembic migrations; Redis; request-id, rate-limit and security middleware.
- Provider health and model listing endpoints; circuit breaker for Ollama and Anthropic.
- React frontend: Login, Dashboard, Documents, Chat (streaming), Analytics, Settings (theme, Ollama and Claude fields), light/dark theme.
- Docker Compose stack (postgres/pgvector, qdrant, tei, redis, backend, frontend, nginx); backend CI workflow; backend test suite.

## Known bugs (found by code reading, not yet reproduced)

Fix these before building new features. Struck-through items are fixed in code (see the Log); fixes were verified with unit tests only, not live providers.

1. ~~**LLM timeouts**~~ FIXED: `llm_service.py` uses `timeout=2.0` for non-streaming Ollama and Anthropic calls, so real generations time out and fall back to canned text. Streaming uses 10s, also short.
2. ~~**Claude model IDs**~~ FIXED: `config.py` defaults to `claude-sonnet-4.6` / `claude-opus-4.6` (dots); Anthropic IDs use hyphens. `.env.template` uses a different ID again. `_resolve_model` only allows those two values. Verify current IDs against the Anthropic docs.
3. ~~**Keys never reach the backend**~~ FIXED (unit tests only): keys are saved per user, Fernet-encrypted, through `/settings/providers`; Settings page rewritten; browser copies can be moved to the server.
4. ~~**No conversation history**~~ FIXED is sent to the model; each turn is a single prompt.
5. **Security layers unwired**: `pi_guard_check`, `check_tool_permission`, `audit_log`, `verify_integrity` are never called on request paths.
6. **PI Guard threshold**: score = matches / 16 patterns, passes if < 0.1, so one match (0.0625) passes.
7. ~~**Vector search is off by default**~~ MOSTLY FIXED (default-on, errors logged at warning and shown in Settings > Memory, `min_score` applied, newer Qdrant API; Qdrant point ids were also invalid and never worked). Original note: (`VECTOR_INDEXING_ENABLED=false`) and all Qdrant/embedding errors are swallowed at debug level, so failures look like worse answers. Qdrant results ignore `min_score`; `client.search` is deprecated in newer qdrant-client.
8. **Dependencies**: `openai` is now used (3.57.0, depends on `httpx2`); `anthropic` is 1.12.1; `torch`, `transformers` and `sentence-transformers` are heavy and likely unnecessary since embeddings go through TEI. `hashlib-additional` looks unnecessary.
9. **Defaults**: placeholder admin and DB passwords in `config.py`; random JWT secret per start invalidates sessions on restart.
10. **Stale config naming**: README and `.env.template` describe a Claude-only fallback; no OpenAI settings exist.
11. **Settings profile and password buttons are broken**: `Settings.jsx` calls `settingsAPI.updateProfile` and `settingsAPI.changePassword`, which are commented out in `frontend/src/api/settings.js`, and the backend has no endpoint for either (`auth.py` has only login, me, refresh, logout). Needs backend endpoints and the client functions.
12. ~~**Validation errors echo submitted values**~~ FIXED (422 handler drops `input`, `ctx`, `url`): `validation_error_handler` in `backend/app/main.py` returns `exc.errors()`, which includes each field's `input`. A rejected request that carries an API key would send the key back. Must be sanitized before any key endpoint ships (part of the bug 3 ticket).
13. ~~**Model list and provider health need no login**~~ FIXED (authenticated, per user): `GET /chat/models` and `GET /chat/providers/health` have no auth dependency. They must become authenticated and per-user once keys are per-user (part of the bug 3 ticket).

14. **`ALLOW_SERVER_PROVIDER_KEYS=false` does not stop Claude from using the server key**: `AnthropicProvider._api_key` falls back to `CLAUDE_API_KEY` when no credentials are passed, and the credential service passes none when the flag is off. The OpenAI adapter does not do this (covered by a test). Fixing Claude changes tests that rely on the fallback, so it was left for its own ticket.
15. **Rate-limit responses carry no CORS headers** (confirmed: a 429 has no `access-control-allow-origin`), so a browser shows a CORS error instead of "too many requests". The limit is 60 requests a minute per IP, which a busy page plus polling can reach. Fix the middleware order or add the headers to the 429.
18. **Integration tests cannot share a process**: the async database engine is created once, so running the integration files together fails with `MissingGreenlet` or "attached to a different loop". Run each file separately (or give each its own engine).
17. **Several popup menus use `bg-surface-card`, which is not defined** in the Tailwind config, so they are transparent (the conversation menu in `Chat.jsx` and the menu in `Documents.jsx`). The model list was fixed; these two were not.
16. **The OpenAI SDK reads `OPENAI_BASE_URL`, `OPENAI_ORG_ID` and `OPENAI_PROJECT_ID` from the environment.** If an operator sets them in the backend container they apply to every user's key. Fine for a private deployment; do not set them on a shared one.

## Next (in order)

1. [ ] Review and approve `spec.md`; answer its open questions. Approve `.claude/plans/server-side-provider-keys.md` so implementation can start.
2. [x] Fix known bugs 1, 2, 4 (timeouts, model IDs, history) with tests. [x] Bug 3 (plus 12, 13): server-side encrypted provider keys + Settings page; awaiting owner's manual test.
3. [x] `LLMProvider` interface + registry; Anthropic and Ollama ported; OpenAI and Ollama Cloud added.
4. [x] Settings page: server-side encrypted keys, Test, per-user model selection with a default, and the admin's embedding model choice with re-index.
5. [x] `MemoryProvider` interface; current Postgres/Qdrant code wrapped as `builtin`; vector path default-on with real health check and UI indicator. Left: re-index documents uploaded while vectors were off.
6. [ ] `DecisionService` client for the Laya service that already runs on the owner's VPS (no sidecar needed; see `spec.md` 3.3 and its open questions); first decisions: retrieval gate, sensitivity gate; measure latency/accuracy on real data.
7. [ ] Wire all five SMC layers into the chat and ingest paths with tests.
8. [ ] Model routing and agent loop.
9. [ ] SMC adapter (`MEMORY_BACKEND=smc`) once its access method is known.
10. [ ] Frontend tests + CI; dependency audit; production-config validation.

## Dev workflow setup (see `docs/dev-workflow.md`)

- [x] `unslop` vendored (MIT)
- [x] Cole's skills vendored and adapted (MIT): `prime-codebase/backend/frontend`, `piv-plan-implementation`, `piv-implement`, `piv-validate`, `piv-review-changes`, `piv-fix-review-findings`, `piv-commit`, `piv-create-pr`, `piv-review-pr`
- [x] `ocr-review-loop` written; Open Code Review (`ocr` v1.12.12) delegation mode verified: runs with no API key
- [x] Hooks installed and tested both directions: secrets guard, session start, action log (`.claude/settings.json`)
- [x] Conventions file for commit/PR (`.claude/references/conventions.md`)
- [x] Ponytail enabled in `.claude/settings.json`, pinned to tag `v5.2.0` (commit `2961b52`, hooks read first). You will be asked to trust it the next time the project opens locally; needs `node`
- [x] Session restarted; skills loaded and used
- [ ] Decide whether `ocr` API mode is wanted (needs a provider; sends diffs to it) and run it once to learn the JSON schema
- [ ] Stop-tests hook: needs a test command that runs without Docker (see baseline below), then add `stop_tests_must_pass.py`
- [ ] Write `MISSION.md` with a seven-item out-of-scope list
- [ ] Read and consider `piv-investigate-issue`, `piv-implement-issue`, `hooks-create`, `skills-create` (not read yet)
- [ ] The secrets hook matches text crudely: a command that merely mentions a blocked pattern (for example the words for a recursive-force delete) is refused. Rephrase, or tighten the regex if it gets in the way

### Validation baseline (native, no Docker daemon)

- 2026-11-22, after model selection Part 2: **385 passed, 16 skipped, 4 failed** in a clean shell (the 4 need the `postgres` host and pass when a database and Redis are reachable: 389 passed, 0 failed). 33 deliberate breaks of the new code, all caught. The 16 skips are the database integration tests: run with `RUN_DB_INTEGRATION_TESTS=1`, **one file per process** (together they share an async engine across event loops and fail), all 16 pass against real Postgres. One of them (`test_provider_credentials_integration`) had a bug in the test itself, fixed. `ruff`, `npm run lint`, `npm run build` pass.

- 2026-11-22, after model selection Part 1: **295 passed, 15 skipped, 4 failed** (same 4 env failures). 21 deliberate breaks of the new code, all caught. `ruff`, `npm run lint`, `npm run build` pass. Run by hand: real Postgres 16 (migration up/down/up), Redis, stand-in local and cloud Ollama servers, stand-in OpenAI server, headless Chromium. Not run: real Ollama Cloud, Docker.

- 2026-11-21, after the OpenAI ticket: **246 passed, 15 skipped, 4 failed** (same 4 env failures). 21 deliberate breaks of the new code, all caught. `ruff`, `npm run lint` and `npm run build` pass. Run by hand: real Postgres 16, Redis, the real `openai` SDK against a stand-in server, headless Chromium. Not run: a real OpenAI call, Docker, Python 3.11.

- 2026-11-21, after the memory ticket: **172 passed, 15 skipped, 4 failed** (same 4 env failures). 12 deliberate breaks, all caught. `ruff` and `npm run lint` clean; `npm run build` passes. Run by hand: real Postgres 16 + pgvector, Redis, Qdrant 1.12.5, a stand-in embedding server, headless Chromium. Not run: Docker, real TEI, real Claude/Ollama, frontend tests.

- 2026-10-14, after the keys ticket: **134 passed, 15 skipped, 4 failed** (same 4 env failures). Not run: Docker integration (`RUN_DB_INTEGRATION_TESTS=1`), live Claude/Ollama calls, type checking, frontend tests, `npm run build` (fails before this change).

- 2026-10-08, after the LLM ticket: **87 passed, 14 skipped, 4 failed**. The same 4 failures as before (`tests/test_auth_endpoints.py::{test_login_success, test_refresh_success, test_logout_success, test_login_invalid_credentials_payload_shape}`, they need the `postgres` host); 36 tests added (`test_llm_service.py`, `test_chat_history.py`). Skips need Postgres/Redis.
- Before the ticket: 51 passed, 14 skipped, 4 failed.
- `ruff check backend/app backend/tests`: clean. `npm run lint` in `frontend/`: clean.
- Not covered anywhere: type checking, frontend tests, Docker integration tests (including the new `list_recent_messages` query, only compiled to SQL), live Claude/Ollama calls, end-to-end journeys.
- Cloud sessions have a Docker client but no daemon, so `make test-backend` cannot run there. Local venv for validation: `.venv-be` (gitignored; see `piv-validate`).

## Log

- 2026-10-08 — Audited repo against the target spec; reorganized docs into `docs/`; drafted `spec.md`, `progress.md`, `CLAUDE.md`, `AGENTS.md`, `docs/dev-workflow.md`; rewrote README. Nothing run or tested yet.
- 2026-10-08 — Reviewed three skill repos (Shimeles, Cole skills, Cole factory). Vendored `unslop`; rewrote `docs/dev-workflow.md` as the combined factory plan. Nothing else installed.
- 2026-10-08 (later) — Read and vendored Cole's PIV skills and three hooks with adaptations; wrote `ocr-review-loop`; verified `ocr` delegation mode; recorded the native validation baseline. Ponytail and a session restart are still on you.
- 2026-10-08 (LLM ticket) — Planned (`.claude/plans/fix-llm-timeouts-model-ids-history.md`) and implemented bugs 1, 2, 4. Anthropic calls now use the official SDK (`anthropic` 1.12.1, `pydantic` 2.13.5); Ollama has 5s/120s timeouts and retries only connection errors and 5xx; Claude IDs are hyphenated and configured once (compose, `.env.template`, README in sync), listed live from the Models API with a static fallback; both chat endpoints send up to 12 prior messages plus the conversation system prompt; refusals and truncation are reported in metadata; `effort` is sent only to models that accept it. Review found one real issue (effort on older models), fixed with tests. Mutation checks: 7 deliberate breaks, all caught. Left for a human: try a real Claude and Ollama conversation, and run `make test-backend` where Docker works.
- 2026-10-12 — Started planning bug 3. Primed on models, migrations, security helpers, Settings page and API client. Found bugs 11 to 13 above. Paused at the question gate; nothing implemented. Also confirmed no secrets in git history.
- 2026-10-12 (later) — Owner accepted all six defaults. Wrote `.claude/plans/server-side-provider-keys.md` (Fernet-encrypted per-user keys, master key only in the local env file, per-credential caches and breakers, authenticated model list and health, sanitized 422 handler, Settings page rewrite). Checked Ollama Cloud auth in the docs (Bearer key on `https://ollama.com/api`, hosted model names without the `-cloud` suffix). Opened a PR from this branch into `master` for review; not merged.
- 2026-10-14 — Implemented the keys ticket: `SecretBox` (Fernet, owner-bound), `provider_credentials` table and migration, credential repository and service, `/settings/providers` (list, save, delete, test), per-credential breakers and model caches, authenticated models and health, sanitized 422, `ProviderKeyFields` on the Settings page with a Move-to-server banner. Mutation checks: 9 breaks, all caught. Review loop and commit follow.
- 2026-11-21 — Clean-clone verification (native, real Postgres/Redis, headless browser). Fixed the production frontend build and first-start migrations. Merged PR #1 into `master` after the check passed.
- 2026-11-21 — Memory ticket: `services/memory` (interface, `builtin`, registry), `GET /memory/health`, `/ready` vector status, `vector_indexed` on documents, `memory_mode` on chat replies, Settings > Memory card and a chat chip, vectors on by default. Found that Qdrant point ids were invalid (indexing never worked); fixed. Live run: vector search and the Qdrant-down fallback both behave as designed.
- 2026-11-21 — OpenAI ticket: moved Anthropic and Ollama behind `LLMProvider` (no behaviour change), added the OpenAI adapter (Responses API, streaming, `store=false`, per-credential breaker and model cache, quota errors), removed provider names from the endpoints and credential service, added the OpenAI card to Settings and an OpenAI group to the chat dropdown. Also fixed the Settings provider status badges, which never loaded. Found three issues (bugs 14 to 16).
- 2026-11-22 — Model selection Part 1: conversations store their provider (migration `20261122_000004`, reversible), `ollama_cloud` provider, per-user model preferences, `/settings/models`, `/chat/models?all=true`, Settings Models section and Ollama Cloud card, provider-aware chat dropdown. Fixed the clipped and transparent model dropdown. Confirmed bug 15 (429 has no CORS headers); logged bug 17.
- 2026-11-22 — Model selection Part 2: `EmbeddingProvider` (TEI, Ollama, Ollama Cloud), admin `/settings/embedding` with probe-before-save, identity-named Qdrant collections, `/memory/reindex` job with progress, health shows the active model and index counts, Settings embedding card. Fixed the first-collection race (HTTP 409). Added the settings integration test; fixed `test_provider_credentials_integration`.
