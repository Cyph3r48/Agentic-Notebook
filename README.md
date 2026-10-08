# Structured Intelligence (Agentic Notebook)

A self-hosted, private alternative to NotebookLM. Upload documents, chat with them with citations, and let an agent work over them using the model you choose: **Ollama** (local or cloud), **Anthropic Claude**, or **OpenAI**.

> **Project status: in active rework.** The document, chat and auth foundations work. Multi-provider agent support, the memory-backend adapters and the Laya decision layer are being built. See [`spec.md`](spec.md) for the target and [`progress.md`](progress.md) for what is done, what is broken and what is next. Nothing below the "Planned" heading exists yet.

## What works today

- Sign in (JWT), upload `.md .pdf .docx .txt .html`, parse and chunk documents
- Keyword search over chunks; semantic search when vector indexing is enabled (see below)
- Chat over your documents with streaming and source citations
- Ollama and Claude model selection per conversation
- Postgres + Alembic migrations, Redis, Qdrant, TEI embeddings, Docker Compose, backend CI

Known problems (timeouts on real generations, Claude model IDs, API keys saved only in the browser) are listed in [`progress.md`](progress.md). Expect rough edges until those are fixed.

## Planned

- **All three providers, first-class.** Pick the provider and model for the agent in Settings. Keys stored server-side, encrypted.
- **Privacy-aware decisions with [Laya](https://github.com/receptron/laya).** A small local decision model (open weights) runs as a sidecar and decides, on your machine, whether to retrieve, which model to use, and whether content is sensitive or an injection attempt. Sensitive turns stay on Ollama. No text is sent anywhere to make those decisions.
- **Bring your own memory.** The app is the dashboard and document loader for a memory system. It ships with a built-in Postgres + Qdrant backend and will pair with the author's SMC or any HTTP/MCP memory service through a `MemoryProvider` adapter.
- **An agent loop** with a bounded number of steps and the SMC security layers on the request path.

## Quick start

Requirements: Docker with Compose v2, about 8 GB RAM, 10 GB disk. For local models, [Ollama](https://ollama.com) running on the host.

```bash
cp .env.template .env      # then edit: passwords, JWT_SECRET, admin account
docker compose up -d --build
docker compose logs -f backend
```

| Service | URL |
|---|---|
| App | http://localhost:3000 |
| API | http://localhost:8000 (docs at `/api/docs`) |
| Qdrant dashboard | http://localhost:6333/dashboard |

Sign in with `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env` and change the password.

### Providers

- **Ollama:** set `OLLAMA_URL` (default `http://host.docker.internal:11434`) and pull a model, e.g. `ollama pull llama3.2:3b-instruct-q4_K_M`.
- **Claude:** set `CLAUDE_API_KEY` in `.env`. Check the model IDs in `backend/app/core/config.py` against Anthropic's current model list; the defaults are suspect (see `progress.md`).
- **OpenAI:** not wired yet.

Never commit `.env`. API credits and keys belong to the provider account that issued them.

### Semantic search

Vector indexing is **off by default** (`VECTOR_INDEXING_ENABLED=false`), so out of the box search is keyword-only. To turn it on, set it to `true`; the TEI container downloads the `bge-large-en-v1.5` embedding model on first start, which takes a while. Qdrant or embedding failures currently fall back silently to keyword search.

## Repository layout

```
backend/    FastAPI app (api, services, repositories, models, schemas), Alembic, tests
frontend/   React + Vite + Tailwind
docs/       architecture, deployment, dev workflow, archive
scripts/    helper scripts
spec.md     what we are building
progress.md where we are and what is next
CLAUDE.md, AGENTS.md   instructions for coding agents
```

## Development

```bash
make test-backend                 # backend tests in Docker
cd frontend && npm install && npm run lint && npm run dev
```

Contributor and agent conventions: [`CLAUDE.md`](CLAUDE.md), [`AGENTS.md`](AGENTS.md), [`docs/dev-workflow.md`](docs/dev-workflow.md). More docs in [`docs/`](docs/README.md).

## License

MIT. See [`LICENSE`](LICENSE).
