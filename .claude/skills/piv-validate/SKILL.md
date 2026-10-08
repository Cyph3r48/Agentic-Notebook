---
name: piv-validate
description: Runs this project's validation suite (backend tests, backend lint, frontend lint) and reports one PASS/FAIL verdict, including what it did not run. Use before committing, before opening a PR, or after finishing a chunk of work to confirm nothing regressed.
---

# Validate

Run every check this project has and report one verdict. Do not fix anything here; this skill reports.

Keep going after a failure so the report covers everything. Capture the output of any command that fails.

## 1. Backend tests

Preferred when a Docker daemon is available (CI runs the same suite):

```bash
make test-backend
```

Cloud sessions have a Docker client but no daemon. Use the native run:

```bash
# one-time setup (skips torch/transformers; embeddings go through the TEI service)
uv venv .venv-be && grep -vE "^(torch|transformers|sentence-transformers|hashlib-additional)" backend/requirements.txt \
  | sed 's/#.*//' | grep "==" > /tmp/req-lite.txt && uv pip install --python .venv-be/bin/python -r /tmp/req-lite.txt
# run
cd backend && ../.venv-be/bin/python -m pytest -q --no-header -p no:cacheprovider -W ignore
```

Native baseline recorded 2026-10-08: **51 passed, 14 skipped, 4 failed**. The 4 failures are in
`tests/test_auth_endpoints.py` (`test_login_success`, `test_refresh_success`, `test_logout_success`,
`test_login_invalid_credentials_payload_shape`) because they need the `postgres` host. The 14 skips are integration
tests that need Postgres/Redis. Report the numbers against that baseline: the same 4 failures are "known, environment",
any other failure is real. Under Docker all of them should run.

## 2. Backend lint

```bash
.venv-be/bin/ruff check backend/app      # baseline: All checks passed
```

## 3. Frontend lint

```bash
cd frontend && npm ci --no-audit --no-fund   # only if node_modules is missing
npm run lint                                  # baseline: clean, max-warnings 0
```

## 4. Not covered (always list these in the report)

- **No type checker** for the backend (no mypy/pyright config) or the frontend (plain JS).
- **No frontend tests** (no Vitest/Jest).
- **Integration paths** (Postgres, Redis, Qdrant, TEI, real providers) only run under Docker.
- **No end-to-end journeys** exist yet.

A PASS from this skill means "the checks that exist are green", not "the change works". Say that in the report.

## 5. Optional live smoke test

Only when the change touches routing, middleware, or startup, and a Docker daemon exists:
`docker compose up -d --build`, hit `GET http://localhost:8000/api/docs` and one authenticated endpoint, then
`docker compose down`. Prefer a second shell over background-and-kill.

## 6. Summary report

One line per check with a pass or fail mark, then **Overall: PASS or FAIL**. For every failure, give the failing
command and the relevant output. Then a "Not run" line from section 4.

## Notes

- Keep it fast: it runs before every commit.
- A checker that cannot fail is worthless. After changing the commands here, break something on purpose and confirm
  this skill reports a failure.
