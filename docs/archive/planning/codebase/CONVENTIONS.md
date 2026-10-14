# Coding Conventions

**Analysis Date:** 2026-02-12

## Languages & Tech Stack

**Frontend:**
- JavaScript (React) - JSX files
- Tailwind CSS for styling
- Vite for build tooling

**Backend:**
- Python 3 (FastAPI)
- Pydantic for data validation
- SQLAlchemy for database ORM

## Naming Patterns

**Python (Backend):**
- Files: `snake_case.py` (e.g., `smc_service.py`, `config.py`)
- Functions: `snake_case` (e.g., `verify_integrity`, `pi_guard_check`)
- Classes: `PascalCase` (e.g., `SMCService`, `Settings`)
- Constants: `SCREAMING_SNAKE_CASE` (e.g., `ADVERSARIAL_PATTERNS`, `ALLOWED_TOOLS`)
- Private methods: `_leading_underscore` (e.g., `_log_security_event`)
- Class methods: `@classmethod` decorator with `cls` parameter

**JavaScript/React (Frontend):**
- Files: `PascalCase.jsx` for components, `camelCase.js` for utilities
- Components: `PascalCase` functions (e.g., `ProtectedRoute`, `App`)
- Functions: `camelCase` (e.g., `App`, standard React hooks)
- Hook files: `useAuthStore` pattern observed

## Code Style

**Formatting:**
- **Python:** `black` and `ruff` configured in `backend/requirements.txt` (development tools)
- **JavaScript/JSX:** ESLint configured in `frontend/package.json`
  - Plugins: `react`, `react-hooks`, `react-refresh`
  - Extensions: `.js`, `.jsx`

**Indentation:**
- Python: 4 spaces
- JavaScript: 2 spaces (React standard)

## Import Organization

**Python (observed in `backend/app/main.py`):**
1. Built-in imports (`from contextlib import asynccontextmanager`, `import time`)
2. Third-party libraries (`from fastapi import ...`, `from loguru import logger`)
3. Local application imports (`from app.core.config import settings`)
4. Blank line separation between groups

**JavaScript (observed in `frontend/src/App.jsx`):**
1. React and third-party libraries
2. Local imports (components, stores, pages)
3. Import specific components with destructuring where appropriate

## Path Aliases

**Backend Python:**
- Uses module imports: `from app.core.config import settings`
- Absolute imports from project root

## Error Handling

**Python (FastAPI):**
- Global exception handler in `backend/app/main.py`:
```python
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={...}
    )
```
- Use `loguru` logger for error logging
- Include `exc_info=True` for stack traces
- Return structured JSON error responses

**Patterns observed:**
- Consistent use of `try/except` blocks in async functions
- Error details only exposed in DEBUG mode
- Request IDs attached to error responses for tracking

## Logging

**Framework:** `loguru` (Python backend)

**Patterns:**
- Use emoji prefixes for different log levels/status:
  - `🚀` - Startup
  - `✅` - Success
  - `🔐` - Security-related
  - `🎯` - Ready state
  - `👋` - Shutdown
  - `⚠️` - Warnings (implied by security events)

```python
logger.info("🚀 Starting Structured Intelligence...")
logger.info("✅ Database initialized")
logger.warning(f"PI Guard flagged content from user {user_id}: {flagged}")
```

## Comments

**When to Comment:**
- Module-level docstrings explaining purpose
- Section headers for code organization (e.g., `# ============================================`)
- Layer comments in security services
- Inline comments for complex regex patterns or business logic

**Documentation patterns:**
```python
"""
SMC (Structured Memory Core) Integration Service
Implements the 5-layer security architecture:
1. PI Guard - Adversarial pattern detection
2. Sanitizer - Content cleaning
...
"""
```

**Section dividers:**
```python
# ============================================
# MIDDLEWARE
# ============================================
```

## Function Design

**Size:** Functions are generally focused (10-30 lines), with clear single responsibility

**Parameters:**
- Use type hints extensively in Python
- Use `Optional` for nullable parameters
- Default parameters with `Field()` for configuration

```python
async def pi_guard_check(cls, content: str, user_id: Optional[UUID] = None) -> Dict[str, Any]:
```

**Return Values:**
- Return structured dictionaries with typed values
- Use Pydantic models for complex returns
- Async functions return coroutines

## Module Design

**Exports:**
- Backend: Create singleton instances (e.g., `smc_service = SMCService()`)
- Frontend: Named exports for components (`export function App() {...}`)
- Default exports for main App component

**Barrel Files:**
- Not observed in current codebase
- Direct imports used throughout

## Configuration Patterns

**Environment Configuration:**
- Pydantic `BaseSettings` in `backend/app/core/config.py`
- Fields with `Field(default=...)` for default values
- Validators for complex parsing (e.g., CORS origins, extensions)

```python
class Settings(BaseSettings):
    ENVIRONMENT: str = Field(default="development")
    CORS_ORIGINS: List[str] = Field(default=[...])
```

**Security Layer Configuration:**
- Boolean flags for enabling/disabling features
- Separate toggles for each security layer

```python
SMC_PI_GUARD_ENABLED: bool = Field(default=True)
SMC_SANITIZER_ENABLED: bool = Field(default=True)
```

## Tailwind/Styling Conventions

**Color Naming:**
- Custom theme with semantic names: `dark-base`, `dark-surface`
- Brand colors: `blue-500`, `purple-500`, `claude-orange-500`
- Glass effects: `glass-white`, `glass-border`

**Animation Classes:**
- Custom animations in Tailwind config: `animate-fade-in`, `animate-float`
- Framer Motion for React animations

**Component Classes:**
- Extensive use of Tailwind utility classes
- Backdrop blur effects: `backdrop-blur-xl`
- Gradient backgrounds with opacity: `from-blue-500/10`

---

*Convention analysis: 2026-02-12*
