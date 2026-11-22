# Structured Intelligence (Agentic Notebook)

A self-hosted, private alternative to NotebookLM. Upload documents, chat with them with citations, and let an agent work over them using the model you choose: **Ollama** (local or cloud), **Anthropic Claude**, or **OpenAI**.

> **Project status: in active rework.** The document, chat and auth foundations work. Multi-provider agent support, the memory-backend adapters and the Laya decision layer are being built. See [`spec.md`](spec.md) for the target and [`progress.md`](progress.md) for what is done, what is broken and what is next. Nothing below the "Planned" heading exists yet.

## What works today

- Sign in (JWT), upload `.md .pdf .docx .txt .html`, parse and chunk documents
- Keyword search over chunks; semantic search when vector indexing is enabled (see below)
- Chat over your documents with streaming and source citations
- Ollama and Claude model selection per conversation
- Postgres + Alembic migrations, Redis, Qdrant, TEI embeddings, Docker Compose, backend CI

Earlier known problems (timeouts, Claude model IDs, API keys saved only in the browser) are fixed on this branch but only unit-tested; the rest are in [`progress.md`](progress.md). Expect rough edges.

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
- **Claude:** paste your key in Settings (see below), or set a server-wide `CLAUDE_API_KEY` in `.env`. The default models are `claude-sonnet-5-5`, `claude-opus-5-5` and `claude-haiku-5-5` (hyphens, no date suffix). With a key set, the model list also comes live from the Anthropic Models API. Tune `CLAUDE_EFFORT` (`low` to `max`) for speed versus depth.
- **Ollama Cloud:** paste your Ollama API key in Settings. It is a separate provider from the local Ollama above, because the two can list models with the same name; each conversation remembers which one it uses. The address is fixed to `ollama.com`, so your key can only ever be sent there. Prompts and document excerpts for these models are processed on Ollama's servers; read Ollama's privacy policy and cloud FAQ before sending sensitive documents.
- **OpenAI:** paste your key in Settings (or set a server-wide `OPENAI_API_KEY`). The model list comes live from your key; `OPENAI_DEFAULT_MODEL` is the fallback if it cannot be read. Chat uses OpenAI's Responses API, and every request asks OpenAI not to store the response (`store=false`, since OpenAI's default is to keep responses for at least 30 days). The app makes no other claim about how OpenAI handles your data; read OpenAI's data controls documentation before sending sensitive documents. Sensitive-content controls (which providers may see what) are not built yet.

### Choosing your models

**Settings > Models** lists every model each provider returns for your keys. Tick the ones you want in your chat list and pick a default for new conversations. This is per user, and a model you switch off is hidden from the dropdown, not removed from the provider. The choices survive a provider being temporarily unreachable (they show as "not listed"). Conversations created before this feature keep working: their provider is worked out from the model name.

Never commit `.env`. API credits and keys belong to the provider account that issued them.

### Document memory

Search works from the first start. Uploads are indexed in Postgres (keyword search) and, by default, in Qdrant with embeddings from the bundled TEI service (vector search). The first start downloads the embedding model, which can take a few minutes; until it is ready, search uses keywords only. **Settings > Memory** shows which mode you are in and why. Chat answers that fell back to keywords say so.

- `VECTOR_INDEXING_ENABLED=false` turns vector search off (about 2 GB less memory).
- Documents are sent to whichever embedding service is active (see below). The default is the local container; the other choices are listed there with what each one sends where.
- Documents uploaded while vectors were off, or before you changed the embedding model, are brought in with **Re-index documents** (Settings > Memory, admin only).
- `MEMORY_BACKEND` accepts `builtin` only for now; `smc` and `http` are reserved and stop the app at startup with a clear message.

#### Choosing the embedding model

An admin picks the embedding model in **Settings > Memory**. There is one choice for the whole system, because vectors made by different models cannot be compared.

| Choice | Where document text goes | Notes |
|---|---|---|
| Bundled TEI (default) | Stays on your machine | One model, set by `EMBEDDING_MODEL`; the address is `EMBEDDING_URL` |
| Ollama (local) | Your own Ollama server | Any embedding model you have pulled, for example `embeddinggemma` |
| Ollama Cloud | Sent to ollama.com | Needs an Ollama API key, entered in Settings and stored encrypted. Whether your account offers an embedding model is something the **Test** button tells you; this has not been confirmed from outside an Ollama account |

- **Test** really embeds a short string and reports the vector size. **Save** only works if that succeeds, so a model that cannot embed never becomes the active one.
- Each choice (provider, model and vector size) gets its own Qdrant collection. After a change, documents are not in the new index until you press **Re-index documents**; until then search uses keywords for them, and Settings says how many documents are missing. The old index is kept (it uses disk) so you can switch back; delete unused collections in Qdrant yourself.
- Re-indexing reads the text already stored in Postgres, so it costs embedding time only. It runs in the background with a progress bar, one job at a time, and stops early with an error if the embedding service keeps failing.
- Environment variables (`EMBEDDING_PROVIDER`, `OLLAMA_EMBED_MODEL`) set the starting choice until an admin saves one. An Ollama Cloud key is never read from the environment.

### Where your API keys live

- The master key, `SECRETS_ENCRYPTION_KEY`, goes in your local env file only. Generate it with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Back it up: if you lose it, saved keys cannot be read and must be entered again.
- Provider keys are entered on the Settings page. The server stores them encrypted, tied to your account, and never sends one back to the browser. Only the last four characters are shown.
- Keys an older version saved in your browser can be moved to the server from Settings; the browser copy is then deleted.
- Without a master key the Settings page cannot save keys, and the server-wide `CLAUDE_API_KEY` is used if `ALLOW_SERVER_PROVIDER_KEYS=true`.
- Outside localhost, serve the app over HTTPS, since keys travel from your browser to the server once when you save them.

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
