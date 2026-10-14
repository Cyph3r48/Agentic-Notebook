# Codebase Structure

**Analysis Date:** 2025-02-12

## Directory Layout

```
structured-intelligence/
├── .planning/                 # GSD planning documents
│   └── codebase/              # Codebase analysis docs
├── backend/                   # FastAPI Python backend
│   ├── app/
│   │   ├── core/              # Core utilities and config
│   │   ├── services/          # Business logic services
│   │   └── main.py            # FastAPI entry point
│   ├── Dockerfile             # Backend container image
│   ├── init-db.sql            # PostgreSQL schema
│   └── requirements.txt       # Python dependencies
├── frontend/                  # React frontend
│   ├── src/
│   │   ├── components/        # Reusable UI components
│   │   ├── pages/             # Route-level pages
│   │   ├── store/             # Zustand state stores
│   │   ├── hooks/             # Custom React hooks
│   │   ├── api/               # API client modules
│   │   ├── utils/             # Frontend utilities
│   │   ├── App.jsx            # Main app component
│   │   ├── main.jsx           # React entry point (referenced)
│   │   └── index.css          # Global styles (referenced)
│   ├── public/                # Static assets (referenced)
│   ├── Dockerfile             # Frontend container image
│   ├── package.json           # Node dependencies
│   ├── tailwind.config.js     # Tailwind CSS config
│   └── vite.config.js         # Vite bundler config (referenced)
├── docs/                      # Documentation (referenced)
├── nginx/                     # Nginx config (referenced)
├── logs/                      # Application logs (referenced)
├── docker-compose.yml         # Container orchestration
├── quick-start.sh             # Deployment script
├── .env.template              # Environment template
└── README.md                  # Main documentation
```

## Directory Purposes

**`.planning/codebase/`:**
- Purpose: GSD command workspace for planning and analysis
- Contains: Architecture docs, conventions, testing patterns, concerns
- Key files: `ARCHITECTURE.md`, `STRUCTURE.md` (this file)
- Generated: No - manually maintained

**`backend/app/core/`:**
- Purpose: Shared infrastructure and configuration
- Contains: Config management, database clients, Redis client, initialization
- Key files: `config.py` (Pydantic settings), database and Redis clients (referenced in main.py)
- Pattern: Core utilities imported by services and API layers

**`backend/app/services/`:**
- Purpose: Business logic implementation
- Contains: Service classes implementing domain operations
- Key files: `smc_service.py` (security), auth, document, vector, LLM, embedding, RAG services (referenced)
- Pattern: Static or instance-based service classes

**`backend/app/api/v1/`:**
- Purpose: HTTP API endpoint definitions
- Contains: FastAPI routers for different domains
- Key files: `__init__.py` (router assembly), auth, documents, chat, search, analytics, admin endpoints (referenced)
- Pattern: Router modules mounted in `main.py`

**`backend/app/middleware/`:**
- Purpose: Custom FastAPI middleware
- Contains: Rate limiting, security headers, request logging
- Key files: `rate_limit.py`, `security.py`, `logging.py` (referenced)
- Pattern: Middleware classes added to FastAPI app

**`backend/app/models/`:**
- Purpose: SQLAlchemy ORM models
- Contains: Database table definitions
- Key files: `user.py`, `document.py`, `conversation.py`, `message.py`, `smc.py` (canonical store), `audit.py` (referenced)
- Pattern: Model classes for SQLAlchemy

**`backend/app/utils/`:**
- Purpose: Utility functions
- Contains: Document parsers, text splitters, validators
- Key files: `pdf_parser.py`, `docx_parser.py`, `markdown_parser.py`, `text_splitter.py`, `validators.py` (referenced)
- Pattern: Pure functions for data processing

**`frontend/src/components/`:**
- Purpose: Reusable React UI components
- Contains: Layout, cards, forms, navigation, feedback components
- Key files: `Layout.jsx`, `Sidebar.jsx`, `Header.jsx`, `GlassCard.jsx`, `Logo.jsx`, `FileUpload.jsx`, `DocumentCard.jsx`, `ChatMessage.jsx`, `ChatInput.jsx`, `MarkdownRenderer.jsx`, `LoadingSpinner.jsx` (referenced)
- Pattern: Functional components with hooks

**`frontend/src/pages/`:**
- Purpose: Route-level page components
- Contains: Full page views for each route
- Key files: `Login.jsx`, `Dashboard.jsx`, `Documents.jsx`, `Chat.jsx`, `Analytics.jsx`, `Settings.jsx` (referenced)
- Pattern: Page components composed from smaller components

**`frontend/src/store/`:**
- Purpose: Zustand state management stores
- Contains: Global state for different domains
- Key files: `authStore.js`, `documentStore.js`, `chatStore.js`, `settingsStore.js` (referenced)
- Pattern: Zustand stores with actions and selectors

**`frontend/src/hooks/`:**
- Purpose: Custom React hooks
- Contains: Reusable logic abstracted as hooks
- Key files: `useAuth.js`, `useDocuments.js`, `useChat.js`, `useDebounce.js` (referenced)
- Pattern: Custom hooks wrapping React Query or other logic

**`frontend/src/api/`:**
- Purpose: API client modules
- Contains: Axios instances and API call functions
- Key files: `client.js` (axios config), `auth.js`, `documents.js`, `chat.js`, `search.js` (referenced)
- Pattern: Organized by domain, centralized client with interceptors

**`frontend/src/utils/`:**
- Purpose: Frontend utility functions
- Contains: Formatters, validators, constants
- Key files: `formatters.js`, `validators.js`, `constants.js` (referenced)
- Pattern: Pure utility functions

## Key File Locations

**Entry Points:**
- Backend: `backend/app/main.py`
- Frontend: `frontend/src/App.jsx` (root), `frontend/src/main.jsx` (mount point)
- Docker: `docker-compose.yml`

**Configuration:**
- Backend settings: `backend/app/core/config.py`
- Docker compose: `docker-compose.yml`
- Frontend Tailwind: `frontend/tailwind.config.js`
- Environment template: `.env.template`

**Core Logic:**
- Security service: `backend/app/services/smc_service.py`
- App factory: `backend/app/main.py`
- React app root: `frontend/src/App.jsx`

**Testing:**
- Not present in current codebase - test files should be added

## Naming Conventions

**Files:**
- Python: `snake_case.py` (e.g., `smc_service.py`, `config.py`)
- JavaScript/JSX: `PascalCase.jsx` for components (e.g., `App.jsx`), `camelCase.js` for utilities (e.g., `authStore.js`)
- Config: Standard names (e.g., `tailwind.config.js`, `docker-compose.yml`)

**Directories:**
- lowercase with underscores: `backend/`, `frontend/`, `core/`, `services/`

**Classes:**
- Python: `PascalCase` (e.g., `SMCService`, `Settings`)

**Functions:**
- Python: `snake_case` (e.g., `pi_guard_check`, `sanitize_content`)
- JavaScript: `camelCase` (e.g., `useAuth`, `formatDate`)

## Where to Add New Code

**New API Endpoint:**
- Implementation: `backend/app/api/v1/{domain}.py`
- Router registration: `backend/app/api/v1/__init__.py`
- Service logic: `backend/app/services/{domain}_service.py`
- Model: `backend/app/models/{domain}.py` (if needed)

**New Component:**
- Implementation: `frontend/src/components/{ComponentName}.jsx`
- Import and use in pages or other components
- Add to barrel export if creating shared component index

**New Page:**
- Implementation: `frontend/src/pages/{PageName}.jsx`
- Route registration: `frontend/src/App.jsx` in Routes
- Add to navigation in `frontend/src/components/Sidebar.jsx` (if needed)

**New Service:**
- Implementation: `backend/app/services/{name}_service.py`
- Import in API layer where needed
- Follow SMC pattern if handling user content

**New Store (Frontend):**
- Implementation: `frontend/src/store/{name}Store.js`
- Use Zustand pattern consistent with existing stores

## Special Directories

**`.planning/`:**
- Purpose: GSD command workspace
- Generated: No
- Committed: Yes (planning documents are part of repo)

**`backend/app/` (Python package):**
- Purpose: Main application package
- Note: Uses Python package structure with `__init__.py` files (implied by imports)
- Imports use absolute package paths: `from app.core.config import settings`

**External Service References:**
The codebase references external services in Docker Compose:
- PostgreSQL: Database persistence
- Qdrant: Vector database
- Redis: Session/cache store
- TEI: Embedding service
- Ollama: Local LLM inference

These are not in the codebase but are infrastructure dependencies.

---

*Structure analysis: 2025-02-12*
