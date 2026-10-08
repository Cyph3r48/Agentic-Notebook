# Technology Stack

**Analysis Date:** 2025-02-12

## Languages

**Primary:**
- **Python** 3.x - Backend API and services (`backend/`)
- **JavaScript** (ES6+/JSX) - Frontend UI components (`frontend/`)

**Secondary:**
- **HTML** - Document processing support
- **Markdown** - Document parsing and storage

## Runtime

**Backend Environment:**
- Python 3.x with asyncio
- ASGI server: Uvicorn 0.32.0 (`uvicorn[standard]==0.32.0`)
- Entry point: `backend/app/main.py`

**Frontend Environment:**
- Node.js (implied by Vite)
- Development server: Vite 5.4.10
- Module system: ES Modules (`"type": "module"` in package.json)

**Package Manager:**
- **pip** - Python dependencies (requirements.txt)
- **npm/yarn** - Node dependencies (lockfile not detected)

## Frameworks

**Backend Core:**
- **FastAPI** 0.115.0 - Main web framework
  - `app.main:app` is the ASGI application entry point
  - Auto-generated OpenAPI docs at `/api/docs` (dev only)
  - Pydantic for request/response validation

**Frontend Core:**
- **React** 18.3.1 - UI framework
  - Functional components with hooks
  - `frontend/src/App.jsx` is the root component
- **React Router** 6.26.2 - Client-side routing
- **TanStack Query** 5.59.16 - Server state management
- **Zustand** 5.0.1 - Client state management

**UI/Styling:**
- **Tailwind CSS** 3.4.14 - Utility-first CSS framework
- **Framer Motion** 11.11.7 - Animations
- **Lucide React** 0.454.0 - Icon library

**Development Tools:**
- **Vite** 5.4.10 - Build tool and dev server
- **ESLint** 8.57.1 - Linting (React, React Hooks, React Refresh plugins)

## Key Dependencies

**Backend - Critical:**
- **fastapi** 0.115.0 - API framework
- **uvicorn[standard]** 0.32.0 - ASGI server with WebSocket support
- **pydantic** 2.10.2 + pydantic-settings 2.6.1 - Configuration and validation
- **python-multipart** 0.0.17 - File upload handling
- **asyncpg** 0.30.0 + **sqlalchemy[asyncio]** 2.0.35 + **alembic** 1.14.0 - Async PostgreSQL ORM and migrations
- **redis** 5.2.0 + **hiredis** 3.0.0 - Session/cache storage
- **qdrant-client** 1.12.0 - Vector database client

**Security & Auth:**
- **python-jose[cryptography]** 3.3.0 - JWT token handling
- **passlib[bcrypt]** 1.7.4 + **bcrypt** 4.2.1 - Password hashing
- **pyjwt** 2.9.0 - JWT implementation
- **slowapi** 0.1.9 - Rate limiting middleware

**LLM Integration:**
- **openai** 1.54.0 - Compatible with Ollama API
- **anthropic** 0.39.0 - Claude API client
- **httpx** 0.27.2 - Async HTTP client
- **sentence-transformers** 3.3.1 + **torch** 2.5.1 + **transformers** 4.46.3 - Local embeddings

**Document Processing:**
- **pypdf** 5.1.0 - PDF parsing
- **python-docx** 1.1.2 - Word documents
- **markdown** 3.7 - Markdown processing
- **beautifulsoup4** 4.12.3 + **lxml** 5.3.0 - HTML/XML parsing

**Monitoring:**
- **loguru** 0.7.2 - Structured logging
- **prometheus-client** 0.21.0 - Metrics export
- **tenacity** 9.0.0 - Retry logic

**Frontend - Critical:**
- **axios** 1.7.7 - HTTP client
- **react-dropzone** 14.2.9 - File upload handling
- **react-markdown** 9.0.1 + **remark-gfm** 4.0.0 - Markdown rendering
- **react-syntax-highlighter** 15.5.0 - Code syntax highlighting
- **sonner** 1.7.0 - Toast notifications
- **date-fns** 4.1.0 - Date formatting
- **nanoid** 5.0.8 - Unique ID generation
- **clsx** 2.1.1 + **tailwind-merge** 2.5.4 - CSS class utilities

## Configuration

**Environment Management:**
- `.env.template` provides reference for all environment variables
- `backend/app/core/config.py` - Pydantic Settings class validates and loads env vars
- `python-dotenv` 1.0.1 for local development

**Key Configuration Categories:**
- Database (PostgreSQL with asyncpg)
- Vector Database (Qdrant)
- Redis (sessions/cache)
- LLM endpoints (Ollama primary, Claude optional)
- Authentication (JWT settings)
- SMC (Structured Memory Core) security layers
- Document processing limits
- Rate limiting
- Logging

**Build Configuration:**
- `frontend/vite.config.js` - Vite configuration (implied)
- `frontend/tailwind.config.js` - Tailwind CSS configuration
- `frontend/postcss.config.js` - PostCSS with autoprefixer

## Platform Requirements

**Development:**
- Docker Compose for service orchestration (inferred from service URLs like `http://qdrant:6333`)
- Local Ollama instance for LLM (`http://host.docker.internal:11434`)
- PostgreSQL with pgvector extension
- Qdrant vector database
- Redis for caching/sessions

**Production:**
- Containerized deployment
- Optional HTTPS with SSL certificates
- Configurable via environment variables
- No hardcoded secrets (secrets generated via `secrets.token_urlsafe()`)

**External Service Dependencies:**
- Ollama (local or remote) for primary LLM
- Optional: Claude API for premium LLM features
- TEI (Text Embeddings Inference) for embeddings (`http://tei:80`)

---

*Stack analysis: 2025-02-12*
