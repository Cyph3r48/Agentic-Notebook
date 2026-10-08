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
