# AGENTS.md

Shared instructions for any coding agent working in this repo (Claude Code, Codex, OpenCode, etc.). `CLAUDE.md` has the Claude-specific details; the rules below apply to everyone.

- **Source of truth:** `spec.md` (what we are building) and `progress.md` (where we are, what is next). Read both first; update `progress.md` before finishing.
- **Stack:** FastAPI + SQLAlchemy/Alembic + Postgres + Redis + Qdrant (backend); React + Vite + Tailwind (frontend); Docker Compose.
- **Test:** `make test-backend`; frontend `npm run lint` in `frontend/`.
- **Architecture rules:** providers behind `LLMProvider`; memory behind `MemoryProvider`; decisions behind `DecisionService`; endpoints stay thin.
- **Privacy rule:** content flagged sensitive never goes to a disallowed provider.
- **Git:** work on the branch you were given; small focused commits; no force-push; no PR unless asked.
- **Secrets:** never commit keys or `.env`; use `.env.template` for new variables.
- **Review:** run the review loop in `docs/dev-workflow.md` (Open Code Review rules, `ocr delegate`) before declaring work done.
- **Skills:** portable copies live in `.claude/skills/` (prime, piv-*, ocr-review-loop, unslop). Other agents: read the matching `SKILL.md` before that kind of work and say "use the X skill" instead of slash commands.
