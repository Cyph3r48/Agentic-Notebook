# Progress

Last updated: 2026-10-08 · Spec: [`spec.md`](spec.md)

Update this file at the end of every working session: move items between sections, add the date, and write the next step so the following session can start cold.

## Where we left off

2026-10-12: first factory lap done and pushed (bugs 1, 2, 4: timeouts, Claude model IDs, conversation history). The next ticket, bug 3 (server-side encrypted provider keys + Settings page, also fixing bugs 12 and 13), is planned in `.claude/plans/server-side-provider-keys.md` using the owner's default answers. Nothing is implemented yet. Next step: owner approves the plan, then run `piv-implement` on it.

The owner deleted their local copy of the repo; the only copy is on GitHub, branch `claude/festive-hamilton-e2cy6w` (not merged into `master`, no PR opened). To work locally: clone, check out that branch, copy the env template to a local env file (git-ignored) and fill it in there. No key is ever committed; a scan of every commit on every branch found no key-shaped strings.

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
3. **Keys never reach the backend**: Settings stores Claude/Ollama keys in browser `localStorage`; the backend reads `CLAUDE_API_KEY` from env. Verify end to end, then replace with server-side encrypted storage.
4. ~~**No conversation history**~~ FIXED is sent to the model; each turn is a single prompt.
5. **Security layers unwired**: `pi_guard_check`, `check_tool_permission`, `audit_log`, `verify_integrity` are never called on request paths.
6. **PI Guard threshold**: score = matches / 16 patterns, passes if < 0.1, so one match (0.0625) passes.
7. **Vector search is off by default** (`VECTOR_INDEXING_ENABLED=false`) and all Qdrant/embedding errors are swallowed at debug level, so failures look like worse answers. Qdrant results ignore `min_score`; `client.search` is deprecated in newer qdrant-client.
8. **Dependencies**: `openai` is in `requirements.txt` but unused (`anthropic` is now used and bumped to 1.12.1); `torch`, `transformers` and `sentence-transformers` are heavy and likely unnecessary since embeddings go through TEI. `hashlib-additional` looks unnecessary.
9. **Defaults**: placeholder admin and DB passwords in `config.py`; random JWT secret per start invalidates sessions on restart.
10. **Stale config naming**: README and `.env.template` describe a Claude-only fallback; no OpenAI settings exist.
11. **Settings profile and password buttons are broken**: `Settings.jsx` calls `settingsAPI.updateProfile` and `settingsAPI.changePassword`, which are commented out in `frontend/src/api/settings.js`, and the backend has no endpoint for either (`auth.py` has only login, me, refresh, logout). Needs backend endpoints and the client functions.
12. **Validation errors echo submitted values**: `validation_error_handler` in `backend/app/main.py` returns `exc.errors()`, which includes each field's `input`. A rejected request that carries an API key would send the key back. Must be sanitized before any key endpoint ships (part of the bug 3 ticket).
13. **Model list and provider health need no login**: `GET /chat/models` and `GET /chat/providers/health` have no auth dependency. They must become authenticated and per-user once keys are per-user (part of the bug 3 ticket).

## Next (in order)

1. [ ] Review and approve `spec.md`; answer its open questions. Approve `.claude/plans/server-side-provider-keys.md` so implementation can start.
2. [x] Fix known bugs 1, 2, 4 (timeouts, model IDs, history) with tests. [ ] Bug 3: server-side encrypted provider keys + Settings page (next ticket: run `piv-plan-implementation`).
3. [ ] `LLMProvider` interface + registry; port Anthropic and Ollama; add OpenAI; Ollama cloud.
4. [ ] Settings page: provider/model picker, server-side encrypted keys, test connection.
5. [ ] `MemoryProvider` interface; wrap current Postgres/Qdrant code as `builtin`; vector path default-on with real health check and UI indicator.
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
