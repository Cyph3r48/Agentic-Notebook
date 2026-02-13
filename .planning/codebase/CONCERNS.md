# Codebase Concerns

**Analysis Date:** 2026-02-12

## Tech Debt

### Incomplete Backend Implementation
- **Issue:** The backend implementation is skeletal with many missing critical components
- **Files:** `backend/app/main.py`, `backend/app/services/smc_service.py`, `backend/app/core/config.py`
- **Impact:** Backend cannot function without API routes, models, database layer, and authentication implementation
- **Fix approach:** Implement the missing modules following the architecture in ARCHITECTURE.md

### Hardcoded SQL in SMC Service
- **Issue:** `smc_service.py` uses raw SQL strings instead of SQLAlchemy ORM for database operations
- **Files:** `backend/app/services/smc_service.py` (lines 82-84, 182-207, 294-321, 335-356)
- **Impact:** SQL injection risk, reduced maintainability, bypasses ORM benefits
- **Fix approach:** Replace raw SQL with SQLAlchemy ORM queries and proper model classes

### Incomplete Readiness Check
- **Issue:** The `/ready` endpoint has a TODO comment for actual health checks but returns hardcoded "connected" status
- **Files:** `backend/app/main.py` (lines 109-118)
- **Impact:** Container orchestration may think service is ready when dependencies are not actually connected
- **Fix approach:** Implement actual connectivity checks for database, Redis, and vector DB

### Missing Core Backend Modules
- **Issue:** Referenced modules don't exist: `app.core.database`, `app.core.redis_client`, `app.api.v1`, `app.middleware.rate_limit`, `app.middleware.security`, `app.models.smc`
- **Files:** `backend/app/main.py` (lines 15-19)
- **Impact:** Application will fail to start with ImportError
- **Fix approach:** Create all missing core modules with proper implementations

## Security Considerations

### Default Credentials in Config
- **Risk:** Default passwords for admin user and database are hardcoded in config
- **Files:** `backend/app/core/config.py` (lines 27, 46-47, 70)
- **Values:** `change_me`, `change_me_too`, `change_me_immediately`
- **Current mitigation:** Template exists to override via environment variables
- **Recommendations:** Remove all default credentials, require explicit configuration, add startup validation

### JWT Secret Auto-Generation
- **Risk:** JWT secret auto-generates if not provided, causing token invalidation on restart
- **Files:** `backend/app/core/config.py` (line 64)
- **Current mitigation:** Uses `secrets.token_urlsafe(32)` for fallback
- **Recommendations:** Fail startup if JWT_SECRET not explicitly provided in production

### CORS Allowing All Methods/Headers
- **Risk:** Overly permissive CORS configuration allows any method and header
- **Files:** `backend/app/main.py` (lines 66-72)
- **Current mitigation:** Limited to specific origins via settings
- **Recommendations:** Restrict to specific required methods and headers

### SQL Injection Potential
- **Risk:** Raw SQL in `smc_service.py` with string interpolation for content_hash lookup
- **Files:** `backend/app/services/smc_service.py` (lines 182-184)
- **Current mitigation:** Parameterized queries used in inserts
- **Recommendations:** Replace all raw SQL with ORM, add SQL injection testing

### Missing Input Validation
- **Risk:** No visible Pydantic models for API input validation
- **Files:** Backend API layer (missing)
- **Current mitigation:** None - validation layer not implemented
- **Recommendations:** Implement comprehensive Pydantic schemas for all endpoints

## Performance Bottlenecks

### No Database Connection Pooling Config
- **Problem:** Database URL configured but no connection pool settings visible
- **Files:** `backend/app/core/config.py` (line 25-27)
- **Cause:** Missing asyncpg pool configuration
- **Improvement path:** Add pool_size, max_overflow, pool_timeout settings

### Synchronous Hash Computation
- **Problem:** SHA-256 hashing in `compute_hash` uses synchronous `hashlib`
- **Files:** `backend/app/services/smc_service.py` (lines 132-134)
- **Cause:** CPU-bound operation blocks event loop for large content
- **Improvement path:** Use `asyncio.to_thread()` or `run_in_executor` for hash computation

### No Caching Strategy
- **Problem:** No caching layer implemented for expensive operations
- **Files:** Redis client referenced but not implemented
- **Impact:** Repeated expensive queries will hit database/vector DB every time
- **Improvement path:** Implement Redis caching for user sessions, document metadata, and vector search results

### Large File Upload Handling
- **Problem:** 100MB upload limit with no chunking or streaming visible
- **Files:** `backend/app/core/config.py` (line 103)
- **Impact:** Large uploads may timeout or consume excessive memory
- **Improvement path:** Implement chunked upload endpoint with streaming processing

## Fragile Areas

### Frontend Missing Core Files
- **Files:** `frontend/src/` - Referenced components don't exist
- **Files referenced:** `authStore`, `Layout`, `Login`, `Dashboard`, `Documents`, `Chat`, `Settings`, `Analytics`
- **Why fragile:** App.jsx imports components that are not implemented
- **Safe modification:** Implement all missing pages following the route structure
- **Test coverage:** No tests exist for frontend

### Backend Import Chain
- **Files:** `backend/app/main.py` imports 6 modules that don't exist
- **Why fragile:** Any startup will immediately fail with ImportError
- **Safe modification:** Implement modules in order: config → database → redis → middleware → api → main
- **Test coverage:** None - no test files exist

### Docker Compose Dependencies
- **Problem:** All services depend_on with condition: service_healthy, but health checks may fail on first run
- **Files:** `docker-compose.yml` (lines 137-145)
- **Why fragile:** TEI service downloads model on first start, causing long startup and health check timeouts
- **Safe modification:** Add init container or increase TEI health check timeout for first run

### Model Initialization Race Condition
- **Problem:** TEI service downloads `BAAI/bge-large-en-v1.5` model on startup
- **Files:** `docker-compose.yml` (line 52)
- **Why fragile:** Backend may start before model is ready, causing embedding failures
- **Safe modification:** Add model warmup check before marking TEI healthy

## Scaling Limits

### Single Database Instance
- **Current capacity:** Single PostgreSQL container
- **Limit:** Vertical scaling only, no read replicas
- **Scaling path:** Implement read replicas for queries, connection pooling with PgBouncer

### Vector Search Limitations
- **Current capacity:** Single Qdrant instance
- **Limit:** In-memory HNSW index may not fit large datasets
- **Scaling path:** Qdrant clustering mode for distributed search

### Session Storage
- **Current capacity:** Redis single instance with PostgreSQL backup
- **Limit:** Redis memory bound
- **Scaling path:** Redis Cluster or external session store

### LLM Throughput
- **Current capacity:** Single Ollama instance (local GPU/CPU)
- **Limit:** Cannot scale horizontally without multiple Ollama instances
- **Scaling path:** Ollama model replication or switch to API-based LLM (Claude)

## Dependencies at Risk

### PyTorch + Transformers for Embeddings
- **Risk:** Heavy dependencies (torch 2.5.1 + transformers 4.46.3) may conflict with FastAPI async
- **Files:** `backend/requirements.txt` (lines 35-36)
- **Impact:** Memory bloat, potential event loop blocking
- **Migration plan:** Offload embeddings to TEI service exclusively, remove from backend deps

### FastAPI Version Pin
- **Risk:** FastAPI pinned to 0.115.0 may have security vulnerabilities
- **Files:** `backend/requirements.txt` (line 2)
- **Impact:** Missing security patches
- **Migration plan:** Update to latest FastAPI version, test compatibility

### Frontend Dependency Age
- **Risk:** React 18.3.1 and related packages may have unpatched issues
- **Files:** `frontend/package.json`
- **Impact:** Security vulnerabilities in frontend dependencies
- **Migration plan:** Run `npm audit`, update packages, test thoroughly

## Missing Critical Features

### Authentication System
- **Problem:** JWT configuration exists but no authentication endpoints implemented
- **Blocks:** All protected routes in frontend
- **Priority:** Critical - blocks all user functionality

### Database Layer
- **Problem:** `get_db_session` referenced but not implemented
- **Files:** `backend/app/main.py` (line 16), `backend/app/services/smc_service.py` (lines 78, 178, 291, 334)
- **Blocks:** All database operations including user management, documents, audit logs
- **Priority:** Critical

### API Routes
- **Problem:** `api_router` imported but not implemented
- **Files:** `backend/app/main.py` (line 17)
- **Blocks:** All API functionality
- **Priority:** Critical

### Document Processing Pipeline
- **Problem:** Document upload, parsing, chunking, and embedding not implemented
- **Blocks:** Core document management feature
- **Priority:** High

### LLM Integration
- **Problem:** Ollama and Claude clients referenced but not implemented
- **Blocks:** Chat functionality
- **Priority:** High

### Vector Search
- **Problem:** Qdrant client referenced but query implementation missing
- **Blocks:** Document search and RAG functionality
- **Priority:** High

## Test Coverage Gaps

### No Test Files
- **What's not tested:** Everything - no test files exist in codebase
- **Files:** Zero `*.test.*` or `*.spec.*` files found
- **Risk:** No automated verification of functionality, regressions likely
- **Priority:** Critical - testing framework exists (pytest) but no tests written

### SMC Security Layer Testing
- **What's not tested:** PI Guard patterns, Sanitizer rules, Resolver integrity checks
- **Files:** `backend/app/services/smc_service.py`
- **Risk:** Security vulnerabilities may go undetected
- **Priority:** High - security features need comprehensive testing

### API Endpoint Testing
- **What's not tested:** All API endpoints (not yet implemented)
- **Risk:** Contract violations, error handling gaps
- **Priority:** High - implement tests alongside endpoint development

### Frontend Component Testing
- **What's not tested:** All React components (not yet implemented)
- **Risk:** UI regressions, accessibility issues
- **Priority:** Medium - can use React Testing Library + Vitest

## Configuration Issues

### Environment Variable Confusion
- **Issue:** Multiple variable formats (PGDATABASE vs DATABASE_URL components)
- **Files:** `backend/app/core/config.py` (lines 25-27), `.env.template` (lines 13-17)
- **Impact:** Configuration complexity, potential for mismatched settings
- **Fix approach:** Standardize on single format, add validation

### Hardcoded Constants in Code
- **Issue:** Risk score threshold (0.1), max upload size, rate limits in code
- **Files:** `backend/app/services/smc_service.py` (line 71), `backend/app/core/config.py` (line 103)
- **Impact:** Requires code changes to tune, cannot adjust per environment
- **Fix approach:** Move all tunables to configuration

### Missing Environment Validation
- **Issue:** No validation that required environment variables are set
- **Files:** `backend/app/core/config.py`
- **Impact:** Runtime errors when required vars missing
- **Fix approach:** Add Pydantic validators for critical settings

---

*Concerns audit: 2026-02-12*
