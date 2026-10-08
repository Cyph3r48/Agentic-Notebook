# Structured Intelligence — Project Spec

Status: **draft for review** · Owner: cyph3r48 · Last updated: 2026-10-08

This is the source of truth for what we are building. `progress.md` tracks where we are against it. Anything marked **(planned)** does not exist yet.

## 1. What this is

A self-hosted, private alternative to NotebookLM: upload documents, chat with them, and let an agent work over them. The user picks which model drives the agent from three equally supported providers:

| Provider | Role |
|---|---|
| **Ollama** (local, and Ollama cloud) | Privacy-first. Data stays on the user's machine for local models. |
| **Anthropic Claude** | Frontier quality. |
| **OpenAI** | Frontier quality. |

The app is the **dashboard and document-loading front end** for a memory system. It ships with a built-in memory backend and can be paired with the author's SMC (Structured Memory Core) or any other RAG/memory system through an adapter (section 5).

### Headline feature: privacy-aware decisions with Laya

A small local decision model, [Laya](https://github.com/receptron/laya) (open weights, Apache 2.0), makes fast classification decisions *before* any text reaches a provider. Nothing about those decisions leaves the user's machine. The most important decision is a **sensitivity gate**: sensitive turns are kept on Ollama (or blocked from frontier providers) according to the user's policy.

## 2. Goals and non-goals

Goals (v1)
- Chat over uploaded documents with citations, streaming, and per-conversation model choice.
- Claude, OpenAI and Ollama (local + cloud) all working, selectable in Settings.
- A pluggable memory backend: built-in, SMC, or generic HTTP/MCP.
- Laya-backed decisions: retrieval gating, model routing, sensitivity/injection gate.
- Provider keys stored server-side, encrypted, per user.
- Honest health reporting: the UI shows when semantic search or a provider is degraded.

Non-goals (v1)
- Multi-tenancy, SSO/SAML, mobile apps, audio/video generation.
- The SMC dashboard features themselves. They are built on top of this app in a later phase.

## 3. Architecture

```
React (Vite) ── nginx ── FastAPI backend ──┬── ProviderRegistry ── anthropic | openai | ollama
                                           ├── MemoryProvider ──── builtin | smc | http/mcp
                                           ├── DecisionService ─── laya sidecar (Node, ONNX)
                                           ├── Postgres  (users, conversations, chunks, audit)
                                           ├── Redis     (sessions, rate limits)
                                           └── Qdrant + TEI embeddings (semantic search)
```

Existing and working today: FastAPI, Postgres + Alembic migrations, Redis, JWT auth, document ingestion and chunking, chat + SSE streaming, citations, React UI, Docker Compose, backend CI.

### 3.1 Provider layer (planned)

Replace the `startswith("claude-")` routing in `backend/app/services/llm_service.py` with a `LLMProvider` interface and a registry:

- `generate(messages, model, **opts)` and `stream(messages, model, **opts)`
- `list_models()` and `health()`
- Normalized usage (`input_tokens`, `output_tokens`) and normalized errors (timeout, auth, rate limit, credit exhausted).
- Adapters: `anthropic`, `openai`, `ollama` (local URL, or cloud URL plus API key).
- Real conversation history is sent, not just the latest message.
- Cross-provider fallback is opt-in and respects the sensitivity gate (a sensitive turn never falls back to a frontier provider).

Status (2026-10-08): the history, timeout, model-ID and Anthropic-SDK parts are done inside `LLMService` (see `progress.md`). That
code is the starting point for the adapters: `StreamOutcome` already carries stop reason, real token usage and normalized
`error_type` values (`provider_timeout`, `provider_auth_error`, `provider_rate_limited`, `provider_http_error`, `provider_refusal`,
`provider_error`). The `LLMProvider` interface, the registry, OpenAI and Ollama cloud are still open.

### 3.2 Settings (planned)

- Choose provider and model for the agent; choose the default for the decision layer.
- Per-provider key entry. Keys are stored server-side, encrypted at rest, never returned to the browser after saving. This replaces the current `localStorage` approach in `frontend/src/pages/Settings.jsx`.
- Test-connection button per provider, backed by `GET /chat/providers/health`.
- Privacy policy control: which providers may receive sensitive content (default: Ollama only).

### 3.3 Decision layer (planned)

`DecisionService` is an interface with three typed calls, mirroring Laya's: **choice**, **score**, **yes/no**. Implementations: `laya` (default) and `llm` (a cheap model call, used as a baseline and fallback).

| Decision | Type | Replaces | Low-confidence behavior |
|---|---|---|---|
| Does this turn need retrieval? | yes/no | `use_rag` always-on toggle | Retrieve |
| Is this chunk relevant to the question? | yes/no | fixed `min_score=0.1` | Keep chunk |
| How hard is this turn? | score | user picks one model for everything | Use selected model |
| Is this input prompt injection? | yes/no | unwired regex in `smc_service.pi_guard_check` | Flag and log |
| Does this contain sensitive/personal data? | yes/no | regex PII redaction only | Treat as sensitive |
| What should the agent do next? | choice | nothing (single-shot) | Ask the LLM |

Rules: Laya is a gate, not a judge. Every decision records its label, probability and latency in the audit log. Below a configurable confidence threshold the system takes the safe default in the last column or escalates to the LLM. Regex checks stay as a cheap pre-filter.

Laya runs as a **Node sidecar container** (ONNX Runtime, `@receptron/laya`). Roughly 1.7 GB of weights and ~2 GB RAM. Inputs are truncated (512 tokens of state; 192 per option set), so the backend sends compact summaries, not whole documents. Latency and accuracy must be measured on this app's own data before any default is trusted; the published figures are the vendor's.

### 3.4 Agent loop (planned)

Single-shot chat becomes a bounded loop: decide next action → (search memory | answer | ask for clarification) → respond with citations. Tool access goes through the SMC tool whitelist (layer 4). Iteration cap and per-turn token budget are configuration, not code.

## 4. Security (5-layer SMC model)

| Layer | State today |
|---|---|
| 1 PI Guard | Regex only; **not called** on the chat path; scoring threshold lets a single match pass |
| 2 Sanitizer | Called on document ingest |
| 3 Resolver (SHA-256) | Hash computed on ingest; verification not called |
| 4 Tool whitelist | Implemented, **not called** |
| 5 CIFS audit | Implemented, **not called** |

v1 requirement: all five layers are on the request path, covered by tests, and PI Guard uses the Laya decision with regex as pre-filter.

## 5. Memory backends

The agent depends only on a `MemoryProvider` interface. Selected with `MEMORY_BACKEND=builtin|smc|http`.

```
ingest(user_id, document) -> document_id
search(user_id, query, limit, filters) -> [Chunk{document_id, chunk_index, content, score, source, content_hash, span}]
get(user_id, document_id) -> Document
delete(user_id, document_id)
health() -> {status, detail}
```

| Backend | Description |
|---|---|
| `builtin` (default) | Postgres chunks + Qdrant vectors + TEI embeddings. Works from `docker compose up` with no external system. |
| `smc` | The author's Structured Memory Core. Adapter to be designed once the SMC's access method is confirmed (HTTP, MCP, or shared Postgres tables). |
| `http` / `mcp` | Generic adapter so anyone can point the app at their own memory or RAG service. |

Out-of-the-box requirements for `builtin` (planned fixes in `progress.md`): vector indexing on by default, a real health check for Qdrant and TEI, and a UI indicator when search has fallen back to keyword-only.

## 6. Quality bar

- Every endpoint has request/response schemas and at least one test; provider adapters are tested against recorded responses.
- Backend CI (pytest + migrations) is required to pass; frontend gets lint + unit tests (Vitest) in CI.
- No default credentials in production; startup fails without explicit secrets.
- Code review runs through Open Code Review before merge (see `docs/dev-workflow.md`).

## 7. Open questions

1. How does the SMC expose itself (HTTP, MCP, or Postgres tables)?
2. Ollama cloud: confirm endpoint, auth header and model naming before building the adapter.
3. Laya hosting: confirm the sidecar fits the target 4 GB VPS, or document a larger minimum.
4. Which "Open Code Review" project is the standard (see `docs/dev-workflow.md`).
