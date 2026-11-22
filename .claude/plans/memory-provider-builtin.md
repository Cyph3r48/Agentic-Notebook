# Feature: MemoryProvider interface with a default-on `builtin` backend

The plan below is meant to be complete, but check the file names and signatures against the code before you start.
Import from the files named here; do not invent new helpers when one exists.

## Feature Description

Chat, search and document ingest reach memory only through a `MemoryProvider` interface. The first implementation,
`builtin`, wraps today's Postgres keyword search and Qdrant vector search. Vector indexing is on by default. Qdrant and
embedding errors are logged at warning or above and reflected in a real health check, and the UI shows whether search is
running on vectors or has fallen back to keywords. `MEMORY_BACKEND=smc|http` are recognised names that fail fast with a
clear message until their adapters exist.

## User Story

As someone running the notebook (with or without an SMC)
I want document search to work from `docker compose up` and to tell me when it is degraded
So that bad answers are never a silent symptom of a down vector store.

## Problem Statement

- `VectorSearchService` is called directly by two endpoints and the document service, so no seam exists for another backend (`spec.md` section 5).
- `VECTOR_INDEXING_ENABLED` defaults to false, so a fresh stack never uses Qdrant or TEI.
- Every Qdrant and embedding failure is swallowed at `logger.debug` (`vector_search_service.py` lines 79, 108, 143). Failures look like worse answers. This is known bug 7.
- Qdrant results ignore `min_score`, `client.search` is the older API, and the client is not closed when a call raises.
- `/ready` reports `"vector_db": "unknown"`.

## Solution Statement

- New package `app/services/memory/` holding the interface and result types (`base.py`), the `builtin` backend (`builtin.py`) and a selector (`registry.py`).
- `BuiltinMemoryProvider` takes over all logic from `VectorSearchService`, which is then deleted. Keyword search stays in `SearchRepository` (services do not touch tables).
- `search()` returns a `SearchOutcome(results, mode, degraded_reason)` where `mode` is `vector`, `keyword` (vectors on, no hits) or `keyword_fallback` (vector path errored).
- `health()` really probes Qdrant (collection exists, vector size equals `EMBEDDING_DIM`) and TEI (`GET /health` plus a one-word embedding of the right length), and also reports the last recorded failure.
- New authenticated `GET /api/v1/memory/health`. `/ready` reports the same state in `vector_db` without failing readiness (keyword fallback keeps the app usable).
- Ingest records `vector_indexed` (true/false/"disabled") in document metadata and warns when indexing fails; the document still completes.
- Frontend: a Memory card in Settings and a "keyword search only" chip on chat messages whose metadata says `memory_mode == "keyword_fallback"`.

## Out of Scope / Non-Goals

- Not included: the `smc` and `http`/`mcp` adapters (names are reserved; selecting them fails at startup). SMC access method is still an open question in `spec.md`.
- Not included: `MemoryProvider.get()` from the spec. Documents live in Postgres and nothing needs a provider-level read yet; drop it from the spec in this change.
- Not included: re-indexing existing documents when vectors are turned on later (follow-up; the `vector_indexed` flag makes it findable).
- Not included: wiring PI Guard, audit or the other SMC layers (known bug 5), or the Laya retrieval gate.
- Not changing: the `/search` request/response shapes (add fields only), chunking, the SMC sanitizer call, auth.
- Not changing: the `document_chunks` schema; no migration in this ticket.

## Feature Metadata

**Feature Type**: Refactor + Enhancement (fixes known bug 7; partly 8: no new dependency)
**Estimated Complexity**: Medium
**Primary Systems Affected**: `services/memory` (new), `document_service`, `chat` and `search` endpoints, config, compose, Settings and Chat pages
**Dependencies**: `qdrant-client==1.12.0` (already pinned), `httpx`, no new packages

## Related Work

**Implements**: `progress.md` Next item 5 and known bug 7   ·   **Epic**: `spec.md` sections 3, 5

**Back-references**:
- `.claude/plans/server-side-provider-keys.md` - same endpoint/service/dependency layering and test style
- `.claude/plans/fix-llm-timeouts-model-ids-history.md` - error surfacing pattern (`StreamOutcome`, metadata)

**Forward-references**:
- 2026-11-21 - Found while implementing: Qdrant accepts only UUID or integer point ids, and the old code used `"<document_id>:<chunk_index>"`. A real Qdrant rejects that, so vector indexing could never have worked. Point ids are now `uuid5` of that string (stable, so re-ingest replaces). Confirmed against a real Qdrant 1.12.5 binary.
- 2026-11-21 - Dropped `test_memory_integration.py`. The provider tests already run a real in-memory Qdrant client (local mode supports `query_points`, filtered delete and size checks), and the full path (real Postgres, real Qdrant, stand-in embedding server, real app) was run by hand instead; results are in the report.
- 2026-11-21 - `/ready` caps the vector check at 5 seconds and reports `unknown` on timeout, so a slow embedding service cannot stall readiness probes.
- 2026-11-21 - Existing document-service tests now stub the memory backend so they never reach Qdrant or the embedding service.

---

## CONTEXT REFERENCES

### Relevant Codebase Files (read before implementing)

- `backend/app/services/vector_search_service.py` (all) - logic to move; note `_embed_texts`, `_ensure_collection`, payload shape
- `backend/app/repositories/search_repository.py` - keyword search, returns dicts with `span_start`/`span_end`; keep
- `backend/app/services/document_service.py` (lines 140-160, 175-190) - the two ingest/delete call sites
- `backend/app/api/v1/endpoints/chat.py` (lines 73-105 `_retrieve_sources`, 137, 387) - chat call sites; metadata built near line 160
- `backend/app/api/v1/endpoints/search.py` - search endpoint; `backend/app/schemas/search.py`
- `backend/app/api/deps.py` - dependency pattern (`get_credential_service`)
- `backend/app/main.py` (lines 29-70 lifespan, 133-146 `/ready`)
- `backend/app/core/config.py` (lines 33-46) - Qdrant/TEI settings
- `backend/tests/test_vector_search_service.py`, `test_search_endpoints.py` (line 33), `test_chat_endpoints.py` (line 182) - monkeypatch targets to update
- `backend/tests/conftest.py` - shared fixtures
- `frontend/src/pages/Settings.jsx` (AI Providers section), `frontend/src/hooks/useChatModels.js`, `frontend/src/api/chat.js`, the chat message component (find with `grep -rn "sources" frontend/src/components`)

### New Files to Create

- `backend/app/services/memory/__init__.py`, `base.py`, `builtin.py`, `registry.py`
- `backend/app/schemas/memory.py` - `MemoryHealthResponse`
- `backend/app/api/v1/endpoints/memory.py` - `GET /memory/health`
- `backend/tests/test_memory_provider.py`, `test_memory_endpoints.py`, `test_memory_integration.py` (Qdrant local mode)
- `frontend/src/components/MemoryStatusCard.jsx`, `frontend/src/api/memory.js`, `frontend/src/hooks/useMemoryHealth.js`

### Relevant Documentation

- [qdrant-client local mode and `query_points`](https://python-client.qdrant.tech/) - `AsyncQdrantClient(":memory:")` runs without a server, usable in tests; `query_points(..., score_threshold=)` replaces `search`. Verify both exist in 1.12.0 before coding (`python -c "import qdrant_client; ..."`).
- [TEI API](https://huggingface.github.io/text-embeddings-inference/) - `GET /health`, `POST /embed` returning a list of vectors.

### Patterns to Follow

**Layering** (`CLAUDE.md`): endpoints validate, check auth, call services, map results. Services own mechanics with explicit inputs and structured results. Repositories own DB access. Endpoints never branch on backend names; they depend on `get_memory_provider`.

**Error surfacing** (`CLAUDE.md`): provider/Qdrant/embedding errors are logged at warning or above and reflected in health. Log error class and a short safe message only; never the query text or document content.

**Structured results**: mirror `StreamOutcome` and `ProviderTestResult` (dataclass / pydantic with fixed safe detail strings).

**Logging**: `logger.bind(...).warning("...", ...)` with loguru named placeholders, as in `endpoints/search.py`.

**Tests**: pytest with `monkeypatch`, `FastAPI` app with `dependency_overrides` (see `test_chat_history.py` lines 17-34).

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation
Interface, result types, config, registry.

### Phase 2: Core implementation
**Depends on:** Phase 1
`BuiltinMemoryProvider` (ingest, search, delete, health) with surfaced errors and the status record.

### Phase 3: Integration
**Depends on:** Phase 2
Switch the three call sites, add the health endpoint and `/ready` field, compose and env defaults, startup check.

### Phase 4: Frontend
**Depends on:** Phase 3 (needs the health endpoint). **Independent of:** Phase 5 docs.

### Phase 5: Tests, docs, validation

---

## STEP-BY-STEP TASKS

### CREATE backend/app/services/memory/base.py
- **IMPLEMENT**: `MemoryChunk` (dataclass: `document_id: str, original_filename: str, chunk_index: int, content: str, score: float, content_hash: str | None, span_start: int | None, span_end: int | None`; method `as_dict()` giving the same keys the endpoints already read). `SearchOutcome(results: list[MemoryChunk], mode: Literal["vector","keyword","keyword_fallback"], degraded_reason: str | None)`. `MemoryHealth(status: Literal["ok","degraded","down","disabled"], backend: str, vector_enabled: bool, components: dict[str, ComponentHealth], detail: str, last_error: str | None, last_error_at: datetime | None)` with `ComponentHealth(ok: bool, detail: str)`. `MemoryProvider` as a `typing.Protocol` with `async ingest(*, user_id, document_id, original_filename, chunks) -> IngestOutcome`, `async search(*, user_id, query, limit, offset=0, min_score=0.1) -> SearchOutcome`, `async delete(*, user_id, document_id) -> None`, `async health() -> MemoryHealth`. `IngestOutcome(id_map: dict[int, str], vector_indexed: bool | Literal["disabled"], error: str | None)`.
- **PATTERN**: dataclasses like `StreamOutcome` in `llm_service.py`.
- **GOTCHA**: `as_dict()` must keep `document_id` as `str`; the chat endpoint does `UUID(source["document_id"])`.
- **VALIDATE**: `cd backend && python -c "from app.services.memory.base import MemoryProvider, SearchOutcome"`
- **SATISFIES**: AC 1

### UPDATE backend/app/core/config.py
- **ADD**: `MEMORY_BACKEND: Literal["builtin","smc","http"] = "builtin"`; change `VECTOR_INDEXING_ENABLED` default to `True`; add `QDRANT_TIMEOUT_SECONDS: float = 5.0`, `EMBEDDING_TIMEOUT_SECONDS: float = 15.0` (first TEI call after a cold start is slow; the old 2s/5s limits are too short), `VECTOR_MIN_SCORE: float = 0.0` is NOT added (use the request's `min_score`).
- **GOTCHA**: `Literal` import; keep the file's existing comment banner style.
- **VALIDATE**: `cd backend && python -c "from app.core.config import settings; print(settings.MEMORY_BACKEND, settings.VECTOR_INDEXING_ENABLED)"`
- **SATISFIES**: AC 2

### CREATE backend/app/services/memory/builtin.py
- **IMPLEMENT**: `BuiltinMemoryProvider(session)` moving logic from `vector_search_service.py`:
  - one private `_qdrant()` async context manager that builds `AsyncQdrantClient(url, api_key, timeout=settings.QDRANT_TIMEOUT_SECONDS)` and always closes it (`finally`);
  - `ingest`: no-op returning `IngestOutcome({}, "disabled", None)` when vectors are off; otherwise embed, ensure collection, upsert with `wait=True` (so failures surface now, not later), return the id map. On any exception: `logger.warning`, record failure in the status record, return `IngestOutcome({}, False, safe_message)`. Do not re-raise: the document still completes on keyword search.
  - `search`: vectors off -> keyword, mode `keyword`. Otherwise `query_points(..., score_threshold=min_score)` filtered by `user_id`. Results non-empty -> mode `vector`. Empty -> keyword, mode `keyword`. Exception -> `logger.warning`, record failure, keyword, mode `keyword_fallback`, `degraded_reason` = safe message.
  - `delete`: same filter delete, `wait=True`, failure logged at warning and recorded (do not raise: Postgres delete must still proceed).
  - `health`: if vectors off -> status `disabled`. Else check (a) Qdrant reachable and collection exists with vector size == `EMBEDDING_DIM` (a missing collection is OK: it is created on first ingest; report "collection will be created on first upload"), (b) TEI `GET /health` then embed `"ping"` and compare length to `EMBEDDING_DIM`. Both ok -> `ok`; one failing -> `degraded` (keyword search still works); both failing -> `down`. Include `last_error` from the status record.
  - Module-level `_status` record (last error string, time, last success time) guarded by nothing fancy (single-process, plain dataclass). Per-process is acceptable; see Assumptions.
- **PATTERN**: `_embed_texts` response handling moves unchanged; safe messages follow `test_connection` in `llm_service.py` (fixed strings keyed by exception class: connect error, timeout, HTTP status, other).
- **IMPORTS**: `httpx`, `qdrant_client.AsyncQdrantClient`, `qdrant_client.http.models`, `SearchRepository`.
- **GOTCHA**: never log or return the raw exception text if it can contain the URL with credentials or the query; map to fixed strings. `recreate_collection` is deprecated: use `collection_exists` + `create_collection`. Batch embeddings in groups of 32 so a large document does not exceed TEI limits. Payload keys must stay identical so existing indexed data keeps working.
- **VALIDATE**: `cd backend && python -m pytest tests/test_memory_provider.py -q`
- **SATISFIES**: AC 2, 3, 4

### CREATE backend/app/services/memory/registry.py and __init__.py
- **IMPLEMENT**: `get_memory_provider(session) -> MemoryProvider` returns `BuiltinMemoryProvider(session)` for `builtin`; for `smc` or `http` raise `MemoryBackendUnavailable("MEMORY_BACKEND=smc is not implemented yet")`. `validate_memory_backend()` called at startup raises the same.
- **GOTCHA**: endpoints must not import `BuiltinMemoryProvider` directly.
- **VALIDATE**: `cd backend && python -c "from app.services.memory import get_memory_provider"`
- **SATISFIES**: AC 1, 5

### UPDATE backend/app/api/deps.py
- **ADD**: `get_memory_provider` dependency (takes `db_session`, returns `registry.get_memory_provider(session)`); map `MemoryBackendUnavailable` to HTTP 503 with the safe message.
- **PATTERN**: `get_credential_service` in the same file.
- **VALIDATE**: `cd backend && python -c "from app.api.deps import get_memory_provider"`

### UPDATE backend/app/api/v1/endpoints/search.py and chat.py
- **IMPLEMENT**: replace `VectorSearchService(session).search(...)` with the injected provider; chat `_retrieve_sources(memory, *, user_id, query, use_rag)` returns `(sources, context_lines, outcome_mode)`; store `memory_mode` and, when degraded, `memory_degraded_reason` in assistant message metadata. Search response adds `mode` and `degraded_reason`.
- **GOTCHA**: `_retrieve_sources` is called in two places (send and stream, lines 137 and 387); update both. Keep source dict keys unchanged. For streaming, `memory_mode` goes in the final stored metadata like `rag_used`.
- **VALIDATE**: `cd backend && python -m pytest tests/test_chat_endpoints.py tests/test_chat_history.py tests/test_search_endpoints.py -q`
- **SATISFIES**: AC 1, 3

### UPDATE backend/app/services/document_service.py
- **IMPLEMENT**: take a `MemoryProvider` (constructor arg defaulting via registry so existing callers keep working); `process_document` uses `memory.delete` then `memory.ingest`, sets `chunk["vector_id"]` from `id_map`, and writes `vector_indexed` and `vector_index_error` into the document's `metadata_json`. `delete_document_for_user` uses `memory.delete`.
- **GOTCHA**: ingestion must still complete when `vector_indexed` is False. A background task may build the service without a request; check how `documents.py` constructs `DocumentService` and keep that path working.
- **VALIDATE**: `cd backend && python -m pytest tests -q -k "document"`
- **SATISFIES**: AC 2, 4

### DELETE backend/app/services/vector_search_service.py
- **REMOVE** after all references are gone (`grep -rn vector_search_service backend` must be empty). Move or rewrite `tests/test_vector_search_service.py` into `test_memory_provider.py`.
- **VALIDATE**: `cd backend && ! grep -rn "vector_search_service\|VectorSearchService" app tests`

### CREATE backend/app/schemas/memory.py, backend/app/api/v1/endpoints/memory.py; UPDATE api/v1/__init__.py
- **IMPLEMENT**: `GET /memory/health` (authenticated) returns `MemoryHealthResponse`. Register the router like `provider_settings`.
- **GOTCHA**: no secrets or raw URLs in the response; component details are fixed strings.
- **VALIDATE**: `cd backend && python -m pytest tests/test_memory_endpoints.py -q`
- **SATISFIES**: AC 3

### UPDATE backend/app/main.py
- **IMPLEMENT**: call `validate_memory_backend()` in `lifespan` before migrations; in `/ready`, set `vector_db` from `provider.health()` status (`ok`/`degraded`/`down`/`disabled`) but do not make readiness fail because of it.
- **VALIDATE**: `cd backend && python -m pytest tests -q -k "ready or health"`

### UPDATE docker-compose.yml, .env.template, README.md
- **IMPLEMENT**: `VECTOR_INDEXING_ENABLED: ${VECTOR_INDEXING_ENABLED:-true}`, `MEMORY_BACKEND: ${MEMORY_BACKEND:-builtin}`; document both and the first-start TEI model download (several minutes, search falls back to keywords meanwhile). Do not add `depends_on` health gates for tei/qdrant (a slow model download must not block the backend).
- **VALIDATE**: `grep -n "VECTOR_INDEXING_ENABLED\|MEMORY_BACKEND" docker-compose.yml .env.template`

### CREATE frontend memory status
- **IMPLEMENT**: `api/memory.js` (`getHealth`), `hooks/useMemoryHealth.js` (React Query, 30s stale time, mirrors `useProviderHealth`), `components/MemoryStatusCard.jsx` (status badge, per-component rows, last error, plain-language hint such as "Search is using keywords only; document search still works"). Render it in `Settings.jsx` below AI Providers. In the chat message component, show a small chip when `metadata.memory_mode === "keyword_fallback"`.
- **PATTERN**: `StatusBadge` and `SettingsSection` in `Settings.jsx`.
- **GOTCHA**: do not touch the profile/password handlers (known bug 11). No console logging of response bodies.
- **VALIDATE**: `cd frontend && npm run lint && npm run build`
- **SATISFIES**: AC 3

### UPDATE spec.md, progress.md
- **IMPLEMENT**: spec section 5: drop `get`, state the `SearchOutcome` modes and the health endpoint; progress: bug 7 partly fixed (errors surfaced, min_score applied, newer Qdrant API, default-on), Next item 5 done, log line, validation baseline.
- **VALIDATE**: `grep -n "memory" progress.md | head`

---

## TESTING STRATEGY

### Unit Tests (`test_memory_provider.py`)
Fake Qdrant client via monkeypatch and `httpx.MockTransport` for TEI (mirror the existing tests in `test_vector_search_service.py`):
- vectors disabled: ingest returns "disabled", no client built, search is keyword, health `disabled`
- ingest ok returns the id map with identical payload keys; embeddings batched at 32
- ingest failure: returns `vector_indexed=False`, logs a warning (assert with loguru sink), does not raise, records last error
- search: vector hit -> mode `vector`; empty -> `keyword`; Qdrant raises -> `keyword_fallback` with reason and a warning logged; `min_score` reaches `score_threshold`
- client is closed when a call raises
- health: ok; Qdrant down -> `degraded`; TEI down -> `degraded`; both -> `down`; wrong vector size -> `degraded` with a clear detail; missing collection -> ok with hint
- raw exception text, URLs and the query never appear in results or log output
- registry: `smc` and `http` raise `MemoryBackendUnavailable`

### Endpoint tests (`test_memory_endpoints.py`)
Authenticated 200 shape; unauthenticated 401; `/search` and chat responses carry `mode` and `memory_mode`.

### Integration (`test_memory_integration.py`)
Skipped unless `RUN_DB_INTEGRATION_TESTS=1`; uses `AsyncQdrantClient(":memory:")` (if local mode works for the used calls) and a fake embedder: ingest, search, delete round trip, per-user isolation (a second user never sees the first user's chunks).

### Edge Cases
Empty query result, offset beyond results, a user with no documents, document re-ingest replaces old points, Qdrant returns payload-less points, collection size mismatch, TEI returns an unexpected shape.

---

## VALIDATION COMMANDS

Use the `piv-validate` skill; native venv because the cloud container has no Docker daemon.

### Level 1: `cd backend && ruff check app tests` and `cd frontend && npm run lint`
### Level 2: `cd backend && python -m pytest -q` (expect only the 4 known `postgres`-host failures)
### Level 3: Integration: start Postgres + pgvector and Redis locally as in `progress.md` (2026-11-21), run `RUN_DB_INTEGRATION_TESTS=1 python -m pytest tests/test_memory_integration.py tests/test_provider_credentials_integration.py -q`
### Level 4: Manual: boot the backend against local Postgres with no Qdrant running. Upload a document; confirm the warning in the log, `GET /memory/health` = `degraded` or `down`, chat still answers with `memory_mode: keyword_fallback`, and the Settings card and chat chip show it. If a Qdrant binary can be installed here, repeat with it and confirm `vector`.
### Level 5: Mutation checks: break each of (a) warning log removed, (b) `keyword_fallback` mode set to `keyword`, (c) user filter removed from the Qdrant query, (d) vector size check removed, (e) client close removed; each must fail a test.

---

## ACCEPTANCE CRITERIA

- [ ] AC 1: No endpoint or service outside `services/memory` imports Qdrant or embedding code; chat, search and document ingest use `MemoryProvider`.
- [ ] AC 2: Vector indexing is on by default (config and compose); a failed index never fails a document upload and is recorded as `vector_indexed: false`.
- [ ] AC 3: A vector-path failure is logged at warning, returned as `mode`/`degraded_reason`, visible through `GET /memory/health`, and shown in Settings and chat.
- [ ] AC 4: Health really probes Qdrant and TEI including the embedding size.
- [ ] AC 5: `MEMORY_BACKEND=smc|http` fail at startup with a clear message; `builtin` is the default.
- [ ] Per-user isolation covered by a test. No query text, document text or secrets in logs or responses.
- [ ] `ruff`, `npm run lint`, `npm run build` clean; the suite shows no new failures.
- [ ] `spec.md`, `progress.md`, README and env template updated.

## COMPLETION CHECKLIST

- [ ] Tasks done in order, each validated
- [ ] `piv-validate` run; "Not run" items listed honestly
- [ ] Review loop (`ocr-review-loop`) run, findings fixed
- [ ] Report written to `.claude/reports/memory-provider-builtin-report.md`
- [ ] Commit with `piv-commit`; no PR unless asked

---

## OPEN QUESTIONS / ASSUMPTIONS

The owner said to use defaults and not stop, so these are assumed and should be confirmed later:

- Assumed - vectors on by default is fine on machines without enough RAM for TEI (about 2 GB for the CPU image); the fallback keeps the app usable and health says so. Confirm before execution if the target is small hardware.
- Assumed - no `depends_on` health gates for Qdrant and TEI, so a slow first model download never blocks the backend.
- Assumed - the status record of last errors is per process (one uvicorn worker today). With multiple workers each reports its own last error; the live probes in `health()` are still accurate. Move to Redis if workers are added.
- Assumed - the failure to index at upload is not an upload error. Confirm: should the user see a warning on the Documents page? (not in this ticket)
- Assumed - `score_threshold=min_score` (default 0.1) is a safe vector cutoff for `bge-large-en-v1.5` cosine scores; tune later with real data.
- Assumed - `MemoryProvider.get()` is dropped from the spec for now.
- Assumed - Qdrant local mode (`:memory:`) supports `query_points`, `upsert` and filtered `delete` in 1.12.0. If not, the integration test stays skipped and a real Qdrant is the manual check.
- Privacy: document text goes to the embedding service at `EMBEDDING_URL` (a local TEI container by default). Pointing it at a third party sends all documents there; add this to the README.

## NOTES

- Why a `SearchOutcome` instead of raising: a degraded search is still a useful answer, but the caller must know. Raising would break chat for a Qdrant blip; returning bare lists (today) hides it.
- Why not a circuit breaker for Qdrant now: timeouts are 5s, and a down Qdrant adds 5s to every chat turn. If that hurts in testing, reuse the breaker idea from `llm_service.py` (per backend, not per user) as a follow-up; recorded as a risk.
- Confidence for one-pass success: 7/10. Risks: the document service's background-task construction path, Qdrant local mode coverage, and frontend changes without a test runner.

## AMENDMENTS

- (none yet)
