# Backend

FastAPI backend for Agentic Notebook.

## LLM Provider Config

Backend supports local Ollama models and Anthropic Claude models.

Set in `.env`:

```powershell
OLLAMA_URL=http://host.docker.internal:11434
DEFAULT_MODEL=llama3.2:3b-instruct-q4_K_M

CLAUDE_API_KEY=your_anthropic_api_key
CLAUDE_SONNET_MODEL=claude-sonnet-4.6
CLAUDE_OPUS_MODEL=claude-opus-4.6
```

`/api/v1/chat/conversations` accepts `model` and enforces Anthropic model allowlist from
`CLAUDE_SONNET_MODEL` and `CLAUDE_OPUS_MODEL`.

## Chat Ops Endpoints

- `GET /api/v1/chat/models` returns detected Ollama models + configured Anthropic models
- `GET /api/v1/chat/providers/health` returns provider health and circuit state
- `POST /api/v1/chat/conversations/{conversation_id}/messages/stream` streams SSE events:
  `delta`, `message`, `done`

## Run

From repository root:

```powershell
docker compose up -d backend
```

## Test

No dependency startup (fastest):

```powershell
docker compose run --rm --no-deps backend python -m pytest -q tests
```

With dependency health gates (`postgres`, `redis`):

```powershell
docker compose run --rm backend python -m pytest -q tests
```

Run DB integration tests explicitly:

```powershell
docker compose run --rm -e RUN_DB_INTEGRATION_TESTS=1 backend python -m pytest -q tests/test_auth_integration.py tests/test_chat_integration.py tests/test_documents_integration.py
```

## Smoke Check

Run the backend smoke script from repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke-backend.ps1
```

This verifies `/health`, `/ready`, auth flow, chat provider/model endpoints, streaming chat, and document listing.

## Migration Strategy

This project currently has two schema bootstrap paths:

1. `backend/init-db.sql` (used by the Postgres container on first volume init)
2. Alembic migrations in `backend/alembic/`

Because `init-db.sql` pre-creates tables, auto-running Alembic against the same fresh DB can conflict.

### Current defaults

- `AUTO_RUN_MIGRATIONS=false`
- `FORCE_RUN_MIGRATIONS_IN_PRODUCTION=false`

### Recommended usage

- Local/dev with `init-db.sql`: keep `AUTO_RUN_MIGRATIONS=false`
- Environments managed by Alembic only: set `AUTO_RUN_MIGRATIONS=true`
- Production safety: auto migrations are skipped in production unless
  `FORCE_RUN_MIGRATIONS_IN_PRODUCTION=true`

### Manual migrations

```powershell
docker compose run --rm backend alembic upgrade head
```
