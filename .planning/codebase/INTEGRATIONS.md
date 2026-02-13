# External Integrations

**Analysis Date:** 2025-02-12

## APIs & External Services

**LLM Providers:**
- **Ollama** (Primary) - Local/on-premise LLM inference
  - SDK/Client: `openai` 1.54.0 (OpenAI-compatible API)
  - Endpoint: `OLLAMA_URL` env var (default: `http://host.docker.internal:11434`)
  - Default model: `llama3.2:3b-instruct-q4_K_M`
  - Config: `backend/app/core/config.py` lines 52-55

- **Claude (Anthropic)** (Optional/Fallback) - Premium cloud LLM
  - SDK/Client: `anthropic` 0.39.0
  - Auth: `CLAUDE_API_KEY` env var
  - Default model: `claude-sonnet-4-20250514`
  - Config: `backend/app/core/config.py` lines 57-59

**Embeddings Service:**
- **TEI (Text Embeddings Inference)** - Hugging Face embedding server
  - Client: HTTP via `httpx` 0.27.2
  - Endpoint: `EMBEDDING_URL` env var (default: `http://tei:80`)
  - Model: `BAAI/bge-large-en-v1.5` (1024-dimensional embeddings)
  - Config: `backend/app/core/config.py` lines 40-41

**HTTP Client:**
- **httpx** 0.27.2 - Async HTTP client for external API calls
- **axios** 1.7.7 - Frontend HTTP client

## Data Storage

**Primary Database:**
- **PostgreSQL** with pgvector extension
  - Driver: `asyncpg` 0.30.0 (async)
  - ORM: SQLAlchemy 2.0.35 with asyncio support
  - Migrations: Alembic 1.14.0
  - Connection: `DATABASE_URL` env var (asyncpg DSN format)
  - Config: `backend/app/core/config.py` lines 25-27
  - Fallback sync driver: `psycopg2-binary` 2.9.10

**Vector Database:**
- **Qdrant** - Vector similarity search
  - Client: `qdrant-client` 1.12.0
  - Endpoint: `QDRANT_URL` env var (default: `http://qdrant:6333`)
  - Collection: `si_documents` (configurable via `QDRANT_COLLECTION`)
  - Optional API key: `QDRANT_API_KEY`
  - Embedding dimension: 1024 (configurable via `EMBEDDING_DIM`)
  - Config: `backend/app/core/config.py` lines 32-35

**Cache & Session Store:**
- **Redis** - Session management and caching
  - Client: `redis` 5.2.0 with `hiredis` 3.0.0 parser
  - Connection: `REDIS_URL` env var (default: `redis://:change_me_too@redis:6379/0`)
  - Password: `REDIS_PASSWORD` env var
  - Initialization: `backend/app/main.py` lines 32-33, 47

**File Storage:**
- Local filesystem only (no cloud storage integration detected)
- Document upload limits: `MAX_UPLOAD_SIZE_MB` (default: 100MB)
- Allowed extensions: `.md`, `.pdf`, `.docx`, `.txt`, `.html`
- Config: `backend/app/core/config.py` lines 103-108

## Authentication & Identity

**Auth Provider:**
- Custom JWT-based authentication (no external auth provider)
- Library: `python-jose[cryptography]` 3.3.0 + `pyjwt` 2.9.0
- Password hashing: `passlib[bcrypt]` 1.7.4 + `bcrypt` 4.2.1
- Algorithm: HS256 (HMAC with SHA-256)
- Config: `backend/app/core/config.py` lines 63-71

**Security Layers (SMC - Structured Memory Core):**
- Custom security framework implemented in `backend/app/services/smc_service.py`
- Features:
  - PI Guard (adversarial pattern detection)
  - Sanitizer (content cleaning)
  - Resolver (SHA-256 integrity verification)
  - Tool Whitelist (access control)
  - CIFS Audit (comprehensive logging)
- Admin token: `SMC_ADMIN_TOKEN` env var
- Config: `backend/app/core/config.py` lines 76-85

## Monitoring & Observability

**Logging:**
- **Loguru** 0.7.2 - Structured logging with rotation
- Log level: `LOG_LEVEL` env var (default: INFO)
- Log file: `LOG_FILE` env var (default: `/app/logs/si.log`)
- Config: `backend/app/core/config.py` lines 125-126
- Usage: `backend/app/main.py` imports and uses logger throughout

**Metrics:**
- **Prometheus Client** 0.21.0 - Metrics export
- Usage: Available but not explicitly configured in viewed files

**Error Tracking:**
- None detected (no Sentry, Rollbar, etc.)
- Custom global exception handler in `backend/app/main.py` lines 128-140

## CI/CD & Deployment

**Containerization:**
- Docker implied by service URLs (`http://qdrant:6333`, `http://tei:80`, `http://redis:6379`)
- Docker Compose likely used for local development
- No explicit Dockerfiles detected in exploration

**Hosting:**
- Not specified
- CORS origins configurable via `CORS_ORIGINS` (default: localhost ports 3000, 5173)
- HTTPS support available via env vars (commented in template)

**CI Pipeline:**
- None detected

## Environment Configuration

**Required env vars (from `.env.template`):**
- `DATABASE_URL` or `PGDATABASE` + `PGUSER` + `PGPASSWORD` + `PGHOST` + `PGPORT`
- `QDRANT_URL`
- `REDIS_URL` or `REDIS_PASSWORD`
- `JWT_SECRET` (auto-generated if not provided)
- `OLLAMA_URL` (for LLM)
- `EMBEDDING_URL` (for TEI)
- `VITE_API_URL` (frontend backend URL)

**Optional env vars:**
- `CLAUDE_API_KEY` (for premium LLM)
- `QDRANT_API_KEY` (if Qdrant requires auth)
- `SMC_ADMIN_TOKEN` (for admin operations)
- `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_NAME` (initial admin user)

**Secrets location:**
- Environment variables only
- `.env` file (gitignored, loaded via python-dotenv)
- No secrets management service detected (AWS Secrets Manager, Vault, etc.)

## Webhooks & Callbacks

**Incoming:**
- None detected

**Outgoing:**
- None detected

## Document Processing Integrations

**PDF:**
- Library: `pypdf` 5.1.0
- No external PDF service (cloud-based OCR, etc.)

**Word Documents:**
- Library: `python-docx` 1.1.2

**HTML:**
- Parser: `beautifulsoup4` 4.12.3 with `lxml` 5.3.0

**Markdown:**
- Parser: `markdown` 3.7

---

*Integration audit: 2025-02-12*
