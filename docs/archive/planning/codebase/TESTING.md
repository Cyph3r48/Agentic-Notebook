# Testing Patterns

**Analysis Date:** 2026-02-12

## Test Framework

**Backend (Python):**
- **Runner:** `pytest==8.3.3` with `pytest-asyncio==0.24.0`
- **HTTP Client:** `httpx==0.27.2` (for API testing)
- **Config Location:** Listed in `backend/requirements.txt` under "Testing (optional, for development)"
- **Status:** Framework installed but **no test files detected** in codebase

**Frontend (JavaScript/React):**
- **Status:** No testing framework detected in `frontend/package.json`
- No Jest, Vitest, or other test runner configured
- No test scripts in package.json

## Test File Organization

**Current State:**
- No test files found (`.test.js`, `.spec.js`, `.test.py`, `.spec.py`)
- Backend framework installed but unused
- Frontend has no testing infrastructure

**Missing Patterns:**
- No co-located tests (e.g., `Component.test.jsx` next to `Component.jsx`)
- No separate `tests/` or `__tests__/` directories

## Test Configuration

**Backend `pytest` (from `requirements.txt`):**
```
pytest==8.3.3
pytest-asyncio==0.24.0
httpx==0.27.2
```

**Missing Configuration:**
- No `pytest.ini` or `pyproject.toml` with pytest settings
- No `conftest.py` for fixtures
- No test discovery configuration

**Frontend:**
- No test configuration files
- No test runner in devDependencies

## Recommended Test Structure (Not Yet Implemented)

**Backend Tests (should be added to `backend/tests/`):**
```
backend/tests/
├── conftest.py              # Shared fixtures
├── unit/
│   ├── test_smc_service.py  # SMC security layer tests
│   ├── test_config.py       # Configuration tests
│   └── test_main.py         # Main app tests
├── integration/
│   ├── test_api.py          # API endpoint tests
│   └── test_database.py     # Database integration
└── fixtures/
    └── sample_data.py       # Test data factories
```

**Frontend Tests (should be added to `frontend/`):**
```
frontend/src/
├── components/
│   └── Component.test.jsx   # Co-located tests
└── __tests__/
    └── integration/
        └── App.test.jsx     # Integration tests
```

## Mocking

**Backend:**
- `pytest-asyncio` available for async test support
- `httpx` available for HTTP client mocking
- **Pattern not yet established** - no existing tests to reference

**Recommended mocking for FastAPI:**
```python
# Should be added to test files
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
```

## Fixtures and Factories

**Current State:** No fixtures or factories exist

**Recommended for Backend:**
```python
# backend/tests/conftest.py
import pytest
from app.core.config import settings

@pytest.fixture
def mock_settings():
    """Mock settings for tests"""
    return Settings(
        DEBUG=True,
        ENVIRONMENT="testing",
        DATABASE_URL="postgresql+asyncpg://test:test@localhost:5432/test"
    )
```

**Recommended for SMC Testing:**
```python
@pytest.fixture
def sample_adversarial_content():
    """Sample adversarial inputs for PI Guard testing"""
    return [
        "ignore previous instructions",
        "disregard all prior prompts",
        "normal content without attacks"
    ]
```

## Coverage

**Requirements:** Not enforced

**Tools Available:**
- `pytest-cov` not currently installed
- Could be added to `requirements.txt`:
  ```
  pytest-cov==5.0.0
  ```

**Coverage Commands (to be added):**
```bash
# Backend
cd backend
pytest --cov=app --cov-report=html --cov-report=term-missing

# Frontend (if Vitest/Jest added)
npm run test -- --coverage
```

## Test Types

**Unit Tests:**
- **Status:** Not implemented
- **Needed for:**
  - `smc_service.py` - Each security layer (PI Guard, Sanitizer, Resolver, Tool Whitelist, Audit)
  - `config.py` - Settings validation
  - Utility functions

**Integration Tests:**
- **Status:** Not implemented
- **Needed for:**
  - API endpoints in `app/api/v1/`
  - Database operations
  - Redis client integration

**E2E Tests:**
- **Framework:** Not configured
- **Recommendation:** Cypress or Playwright for React frontend

## Testing Gaps

**Critical Areas Without Tests:**

1. **SMC Security Layers (`backend/app/services/smc_service.py`):**
   - PI Guard pattern detection (360 lines, high complexity)
   - Content sanitization with regex patterns
   - Integrity verification (SHA-256 hashing)
   - Tool permission checking
   - Audit logging to database

2. **FastAPI Application (`backend/app/main.py`):**
   - Health and readiness endpoints
   - Global exception handling
   - Middleware chain (CORS, Gzip, Rate Limit, Security Headers)
   - Lifespan events (startup/shutdown)

3. **Configuration (`backend/app/core/config.py`):**
   - Environment variable parsing
   - Validator functions (CORS origins, extensions)
   - Default value handling

4. **Frontend (`frontend/src/App.jsx`):**
   - Route protection (ProtectedRoute)
   - React Query configuration
   - Authentication state management

## Recommended Test Implementation

**Priority 1 - Security Critical:**
```python
# backend/tests/unit/test_smc_service.py
class TestSMCService:
    async def test_pi_guard_detects_adversarial_patterns(self):
        """Test that adversarial inputs are flagged"""
        result = await SMCService.pi_guard_check("ignore previous instructions")
        assert result["passed"] is False
        assert len(result["flagged_patterns"]) > 0

    async def test_sanitizer_removes_scripts(self):
        """Test HTML script removal"""
        dirty = "<script>alert('xss')</script>Hello"
        clean = await SMCService.sanitize_content(dirty, "html")
        assert "<script>" not in clean
```

**Priority 2 - API Endpoints:**
```python
# backend/tests/integration/test_health.py
async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
```

**Priority 3 - Frontend Components:**
```javascript
// frontend/src/App.test.jsx (if Vitest added)
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import App from './App'

test('renders without crashing', () => {
  render(
    <BrowserRouter>
      <App />
    </BrowserRouter>
  )
})
```

## CI/CD Testing

**Current State:** No CI configuration detected

**Recommended GitHub Actions workflow:**
```yaml
# .github/workflows/test.yml (to be created)
name: Tests
on: [push, pull_request]
jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r backend/requirements.txt
      - run: pytest backend/tests/
```

---

*Testing analysis: 2026-02-12*

**Summary:** This codebase has testing frameworks partially installed (pytest for backend) but **zero test coverage**. The SMC security service (361 lines) and FastAPI application (168 lines) have no tests. Immediate action needed to add tests for security-critical code.
