# CLAUDE.md

Guidance for Claude Code in this repo. Also read `AGENTS.md` (shared rules for any agent).

## Start of every session
1. Read `progress.md` ("Where we left off", "Next").
2. Read the relevant part of `spec.md` before designing anything.
3. Run `git status` and `git log --oneline -5`.

## End of every session
Update `progress.md` (move items, add a Log line, write the next step). If behavior changed, update `spec.md`.

## Commands
- Run backend tests: `make test-backend` (Docker) — CI uses the same suite in `backend/tests`.
- Start everything: `docker compose up -d` (see `README.md`).
- Frontend: `cd frontend && npm install && npm run dev`; lint with `npm run lint`.
- Migrations: Alembic, in `backend/alembic/versions` (timestamped files).

## Layout
- `backend/app/api/v1/endpoints` — routes · `services` — logic (LLM, vector search, SMC, documents) · `repositories` — DB access · `models`, `schemas` — SQLAlchemy and Pydantic.
- `frontend/src` — `pages`, `components`, `api`, `hooks`, `store`.
- `docs/` — architecture, deployment, quick reference, workflow; `docs/archive/` is stale history.

## Factory workflow (skills in `.claude/skills/`, details in `docs/dev-workflow.md`)

`prime-*` → `piv-plan-implementation` → `piv-implement` → `piv-validate` → `ocr-review-loop` (uses `piv-review-changes`,
`piv-fix-review-findings`) → `piv-commit` → `piv-create-pr` / `piv-review-pr` **only when asked**.
Use `unslop` on anything a person will read. `piv-validate` always lists what it did not run; do not claim more than it proves.
Hooks in `.claude/hooks/` block reads of secrets and recursive-force deletes, inject git state at session start, and log tool calls to `logs/`.
Cloud sessions have no `gh` CLI; use the GitHub MCP tools. Skills never override the rules below.

## Architecture layering

Endpoints (`api/v1/endpoints`) validate input, check auth and ownership, call services, and map results to responses.
Services own reusable mechanics (provider calls, vector search, document processing) with explicit inputs and structured
results. Repositories own database access. Services do not reach into tables directly; endpoints do not branch on
provider names. Extract shared logic only when two or more callers need it.

## Rules
- Provider-specific code lives behind the provider interface; endpoints never branch on provider names.
- Memory access goes through `MemoryProvider`; never query Qdrant directly from endpoints.
- Sensitive content must never be sent to a provider the user's privacy policy disallows.
- Never commit secrets. No default credentials in production paths.
- Errors from providers, Qdrant or embeddings must be surfaced (logged at warning+ and reflected in health), not swallowed.
- Add or update tests with every behavior change; CI must stay green.
- Keep changes small and in scope; note unrelated problems in `progress.md` instead of fixing them in passing.
- Follow `docs/dev-workflow.md` for planning, review and PR conventions. Do not open a PR unless asked.
- Writing for people (commit messages, PR text, README/docs, replies): apply the `unslop` skill, but keep required attribution trailer lines as given.
