# Progress

Last updated: 2026-10-08 · Spec: [`spec.md`](spec.md)

Update this file at the end of every working session: move items between sections, add the date, and write the next step so the following session can start cold.

## Where we left off

Last code commit was theme/settings work (`d64c6a8`). Docs were reorganized and `spec.md` drafted on 2026-10-08. No application code has changed since.

## Done (in the code today)

- FastAPI backend: auth (JWT sessions), users, documents (upload, parse, chunk, list, delete), keyword + vector search, chat conversations and messages (pagination, titles, delete), SSE streaming, citations with snippets and spans, token accounting.
- Postgres schema with Alembic migrations; Redis; request-id, rate-limit and security middleware.
- Provider health and model listing endpoints; circuit breaker for Ollama and Anthropic.
- React frontend: Login, Dashboard, Documents, Chat (streaming), Analytics, Settings (theme, Ollama and Claude fields), light/dark theme.
- Docker Compose stack (postgres/pgvector, qdrant, tei, redis, backend, frontend, nginx); backend CI workflow; backend test suite.

## Known bugs (found by code reading, not yet reproduced)

Fix these before building new features.

1. **LLM timeouts**: `llm_service.py` uses `timeout=2.0` for non-streaming Ollama and Anthropic calls, so real generations time out and fall back to canned text. Streaming uses 10s, also short.
2. **Claude model IDs**: `config.py` defaults to `claude-sonnet-4.6` / `claude-opus-4.6` (dots); Anthropic IDs use hyphens. `.env.template` uses a different ID again. `_resolve_model` only allows those two values. Verify current IDs against the Anthropic docs.
3. **Keys never reach the backend**: Settings stores Claude/Ollama keys in browser `localStorage`; the backend reads `CLAUDE_API_KEY` from env. Verify end to end, then replace with server-side encrypted storage.
4. **No conversation history** is sent to the model; each turn is a single prompt.
5. **Security layers unwired**: `pi_guard_check`, `check_tool_permission`, `audit_log`, `verify_integrity` are never called on request paths.
6. **PI Guard threshold**: score = matches / 16 patterns, passes if < 0.1, so one match (0.0625) passes.
7. **Vector search is off by default** (`VECTOR_INDEXING_ENABLED=false`) and all Qdrant/embedding errors are swallowed at debug level, so failures look like worse answers. Qdrant results ignore `min_score`; `client.search` is deprecated in newer qdrant-client.
8. **Dependencies**: `openai` and `anthropic` SDKs are in `requirements.txt` but unused; `torch`, `transformers` and `sentence-transformers` are heavy and likely unnecessary since embeddings go through TEI. `hashlib-additional` looks unnecessary.
9. **Defaults**: placeholder admin and DB passwords in `config.py`; random JWT secret per start invalidates sessions on restart.
10. **Stale config naming**: README and `.env.template` describe a Claude-only fallback; no OpenAI settings exist.

## Next (in order)

1. [ ] Review and approve `spec.md`; answer its open questions.
2. [ ] Fix known bugs 1–4 (timeouts, model IDs, key storage, history) with tests.
3. [ ] `LLMProvider` interface + registry; port Anthropic and Ollama; add OpenAI; Ollama cloud.
4. [ ] Settings page: provider/model picker, server-side encrypted keys, test connection.
5. [ ] `MemoryProvider` interface; wrap current Postgres/Qdrant code as `builtin`; vector path default-on with real health check and UI indicator.
6. [ ] Laya sidecar container + `DecisionService`; first decisions: retrieval gate, sensitivity gate; measure latency/accuracy on real data.
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
- [ ] You: install Ponytail (`/plugin marketplace add DietrichGebert/ponytail`, then `/plugin install ponytail@ponytail`)
- [ ] You: restart the session so the new skills load; confirm with `/skills`
- [ ] Decide whether `ocr` API mode is wanted (needs a provider; sends diffs to it) and run it once to learn the JSON schema
- [ ] Stop-tests hook: needs a test command that runs without Docker (see baseline below), then add `stop_tests_must_pass.py`
- [ ] Write `MISSION.md` with a seven-item out-of-scope list
- [ ] Read and consider `piv-investigate-issue`, `piv-implement-issue`, `hooks-create`, `skills-create` (not read yet)
- [ ] The secrets hook matches text crudely: a command that merely mentions a blocked pattern (for example the words for a recursive-force delete) is refused. Rephrase, or tighten the regex if it gets in the way

### Validation baseline (2026-10-08, native, no Docker daemon)

- Backend tests: 51 passed, 14 skipped, 4 failed. Failures are `tests/test_auth_endpoints.py::{test_login_success, test_refresh_success, test_logout_success, test_login_invalid_credentials_payload_shape}`, which need the `postgres` host. Skips need Postgres/Redis.
- `ruff check backend/app`: clean. `npm run lint` in `frontend/`: clean.
- Not covered anywhere: type checking, frontend tests, integration paths, end-to-end journeys.
- Cloud sessions have a Docker client but no daemon, so `make test-backend` cannot run there.

## Log

- 2026-10-08 — Audited repo against the target spec; reorganized docs into `docs/`; drafted `spec.md`, `progress.md`, `CLAUDE.md`, `AGENTS.md`, `docs/dev-workflow.md`; rewrote README. Nothing run or tested yet.
- 2026-10-08 — Reviewed three skill repos (Shimeles, Cole skills, Cole factory). Vendored `unslop`; rewrote `docs/dev-workflow.md` as the combined factory plan. Nothing else installed.
- 2026-10-08 (later) — Read and vendored Cole's PIV skills and three hooks with adaptations; wrote `ocr-review-loop`; verified `ocr` delegation mode; recorded the native validation baseline. Ponytail and a session restart are still on you.
