# Architecture

**Analysis Date:** 2025-02-12

## Pattern Overview

**Overall:** Modular Monolith with Clean Architecture Layers

**Key Characteristics:**
- Backend: FastAPI with layered architecture (core, services, API)
- Frontend: React with modern stack (Vite, Zustand, TanStack Query)
- Containerized: Docker Compose orchestration
- Security-First: 5-Layer SMC security architecture integrated throughout

## Layers

**Frontend Layer:**
- Purpose: User interface and state management
- Location: `frontend/src/`
- Contains: React components, pages, stores, API clients
- Depends on: Backend API at `localhost:8000`
- Used by: End users via web browser

**API Layer:**
- Purpose: HTTP endpoints and request routing
- Location: `backend/app/api/v1/`
- Contains: FastAPI routers for auth, documents, chat, search, analytics, admin
- Depends on: Service layer, SMC security layer
- Used by: Frontend, external clients

**Service Layer:**
- Purpose: Business logic implementation
- Location: `backend/app/services/`
- Contains: SMC service, auth service, document service, vector service, LLM service, embedding service, RAG service
- Depends on: Core utilities, database clients
- Used by: API layer

**Core Layer:**
- Purpose: Shared utilities and infrastructure
- Location: `backend/app/core/`
- Contains: Config, database, Redis client, initialization
- Depends on: Environment variables, external services
- Used by: All other backend layers

**Security Layer (SMC):**
- Purpose: 5-layer security validation
- Location: `backend/app/services/smc_service.py`
- Contains: PI Guard, Sanitizer, Resolver, Tool Whitelist, CIFS Audit
- Depends on: Database for audit logging
- Used by: API layer, service layer (called before sensitive operations)

**Data Layer:**
- Purpose: Persistence and caching
- Location: External services (PostgreSQL, Qdrant, Redis)
- Contains: Users, documents, conversations, vectors, audit logs, sessions
- Depends on: N/A (external)
- Used by: Core layer, service layer

## Data Flow

**Document Upload Flow:**

1. User uploads file via `FileUpload` component in `frontend/src/components/FileUpload.jsx`
2. Frontend validates file type (.md, .pdf, .docx, .txt)
3. POST to `/api/v1/documents/upload`
4. **SMC Layer 1 (PI Guard)**: Scan filename for adversarial patterns
5. **SMC Layer 2 (Sanitizer)**: Clean metadata
6. `DocumentService` saves file and extracts text
7. Text is chunked (CHUNK_SIZE=1000, OVERLAP=200)
8. **SMC Layer 3 (Resolver)**: Compute SHA-256 hash for integrity
9. `EmbeddingService` generates embeddings via TEI
10. Store vectors in Qdrant with metadata linking to PostgreSQL
11. **SMC Layer 5 (CIFS Audit)**: Log upload event with hash

**Chat Query Flow:**

1. User asks question via `ChatInput` in `frontend/src/pages/Chat.jsx`
2. POST to `/api/v1/chat/conversations/{id}/messages`
3. **SMC Layer 1 (PI Guard)**: Scan for prompt injection
4. **SMC Layer 2 (Sanitizer)**: Clean user input
5. `RAGService` embeds query (same model: bge-large-en-v1.5)
6. Qdrant semantic search for top 5 similar chunks
7. **SMC Layer 3 (Resolver)**: Verify chunk integrity via SHA-256
8. Build context: system prompt + retrieved chunks + user query
9. **SMC Layer 4 (Tool Whitelist)**: Check user permission to chat
10. `LLMService` streams response from Ollama or Claude API
11. Extract citations mapping to source documents
12. **SMC Layer 5 (CIFS Audit)**: Log interaction with request_id

**State Management:**
- Frontend uses Zustand stores (`frontend/src/store/`)
- Server state via TanStack Query (React Query)
- Sessions in Redis (JWT tokens)

## Key Abstractions

**SMCService:**
- Purpose: Centralized security validation (5 layers)
- Location: `backend/app/services/smc_service.py`
- Pattern: Static class methods with async context
- Layer 1: `pi_guard_check()` - adversarial pattern detection
- Layer 2: `sanitize_content()` - content cleaning
- Layer 3: `verify_integrity()` / `compute_hash()` - SHA-256 integrity
- Layer 4: `check_tool_permission()` - RBAC enforcement
- Layer 5: `audit_log()` / `_log_security_event()` - comprehensive logging

**Settings:**
- Purpose: Configuration management
- Location: `backend/app/core/config.py`
- Pattern: Pydantic Settings with env var support
- Sections: App, Database, Vector DB, LLM, Auth, SMC, CORS, Documents, Rate Limiting

**FastAPI App:**
- Purpose: Web framework entry point
- Location: `backend/app/main.py`
- Pattern: Lifespan context manager for startup/shutdown
- Middleware: CORS, Gzip, Security Headers, Rate Limiting, Request Timing
- Routes: Health check, API router (v1), root endpoint
- Error Handling: Global exception handler

## Entry Points

**Backend Entry Point:**
- Location: `backend/app/main.py`
- Triggers: Uvicorn server or `python -m app.main`
- Responsibilities:
  - Initialize FastAPI app
  - Configure middleware stack
  - Register API routes
  - Handle lifespan events (init DB, Redis, SMC)
  - Global error handling

**Frontend Entry Point:**
- Location: `frontend/src/main.jsx` (referenced but not present in file scan)
- Actual entry in: `frontend/src/App.jsx`
- Triggers: Vite dev server or build
- Responsibilities:
  - React Query client setup
  - React Router configuration
  - Protected route handling
  - Toast notifications
  - Glass morphism theme application

**Docker Entry Points:**
- Backend: `backend/Dockerfile` (references `app.main:app`)
- Frontend: `frontend/Dockerfile` (likely nginx-served build)
- Orchestration: `docker-compose.yml`

## Error Handling

**Strategy:** Centralized with layered fallback

**Patterns:**
- Global exception handler in `main.py` catches all unhandled exceptions
- Returns JSON with error message (sanitized in production)
- Includes request_id for tracing
- Loguru for structured logging
- SMC audit log for security violations

**Frontend Error Handling:**
- React Query handles API errors with retry logic
- Toast notifications via Sonner for user feedback
- Protected routes redirect to login on auth failure

## Cross-Cutting Concerns

**Logging:** Loguru with structured output, file logging to `/app/logs/si.log`

**Validation:** Pydantic models for request/response validation

**Authentication:** JWT tokens with bcrypt password hashing, role-based access

**Rate Limiting:** Custom middleware with Redis backend

**Security Headers:** Custom middleware adding security headers

---

*Architecture analysis: 2025-02-12*
