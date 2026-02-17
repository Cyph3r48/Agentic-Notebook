# Backend

FastAPI backend for Agentic Notebook.

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

