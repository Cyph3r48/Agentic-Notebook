# Feature: wire the SMC security layers into requests, fix profile and password

Fixes known bugs 5, 6, 9 and 11 in `progress.md`. Inherits `spec.md` section 4 (five layers on the request path, covered by tests) and the `CLAUDE.md` rules (no default credentials in production paths; errors surfaced, not swallowed).

## Problem

- Layers 1 (PI Guard), 3 (Resolver), 4 (tool whitelist) and 5 (audit) exist in `smc_service.py` but nothing calls them on a request. Only layer 2 (sanitizer) runs, at upload.
- The PI Guard threshold (`matches / 16 < 0.1`) lets a single explicit injection pass.
- Nothing records logins, uploads, deletes or chats; a failed login leaves no trace.
- Defaults are unsafe: compose falls back to a known JWT secret and placeholder passwords, and nothing stops a production start with them (bug 9).
- Settings profile and password buttons call endpoints that do not exist (bug 11). There is also no limit on failed logins beyond a per-IP request cap.

## Decisions (defaults; owner said not to stop for questions)

- **PI Guard, retrieved text (indirect injection, the real risk):** a flagged chunk is dropped from the model context and from the citations, audited, and counted in the reply metadata (`memory_quarantined`). Uploads are not blocked: the document is the user's own and only the chunk is withheld.
- **PI Guard, the user's own message:** flagged and audited, still answered, because it is the user's own conversation. `SMC_PI_GUARD_BLOCK_USER_INPUT=true` turns it into a 400.
- **Scoring:** patterns split into strong (explicit injection: ignore/disregard instructions, reveal system prompt, jailbreak, bypass security, forget everything, system tags) and weak (`you are now`, `new instructions`, `pretend you are`, `roleplay as`, `show prompt`). One strong match flags; two different weak matches flag; one weak match does not (benign text says "new instructions" all the time).
- **Resolver:** every retrieved chunk's text is hashed and compared with the hash stored at ingest. A mismatch is dropped, audited and counted.
- **Tool whitelist:** the app has no model-callable tools yet. `search_memory` is gated by the whitelist before retrieval (deny means no retrieval, audited). The agent loop must send every tool through the same check; recorded in the spec.
- **Audit:** logins (success, failure, lockout), logout, password change, profile change, document upload and delete, chat messages (sizes and flags only), security flags. Never message text, document text, passwords or keys. Written in its own session so a failed request is still recorded; an audit failure is logged at error level and never breaks the request.
- **Throttle:** 5 failed logins per email and IP, or 5 failed current-password checks per user, locks that key for 15 minutes (429). In memory, one worker; noted.
- **Startup checks:** `ENVIRONMENT=production` refuses to start without an explicit `JWT_SECRET` of 32+ characters, a non-placeholder admin password, database password and Redis password. Other environments log a loud warning per placeholder.
- **Password:** new password 10+ characters, different from the current one, not a known placeholder. Changing it deletes every refresh session and returns fresh tokens for this device. Email and username stay fixed (the page already says so).

## Out of scope

Laya-based PI decision (spec 3.3, on hold), roles beyond today's three, an audit viewer UI, email verification, multi-worker throttling, agent loop.

## Tasks

1. Config + `core/startup_checks.py`; call at startup. VALIDATE: unit tests.
2. `SMCService`: weighted PI scan, audit with flag/reason/request id/valid IP, audit failures swallowed and logged. Conftest captures audit events.
3. `services/security_gate.py`: filter retrieved chunks (integrity + PI Guard), check user message, whitelist gate, audit.
4. Chat endpoints: use the gate in `_retrieve_sources`, check the message, audit the turn, metadata.
5. Auth/documents endpoints: audit events, login throttle.
6. `PATCH /users/me`, `POST /auth/change-password` (+ schemas, `SessionRepository.delete_all_for_user`).
7. Frontend: `settingsAPI.updateProfile/changePassword`, store update, handlers.
8. Tests, live run (real Postgres), mutation checks, docs, report.

## Acceptance criteria

- A chunk containing an explicit injection never reaches the model or the citations; a benign "new instructions" chunk does.
- A tampered chunk is dropped; the event is audited.
- Failed and successful logins, password and profile changes, uploads, deletes and chats leave audit rows without content or secrets.
- Five failed logins lock the account key for 15 minutes.
- Production start fails with default or missing secrets and names which ones.
- Profile name and password change work from the Settings page; old refresh tokens stop working.
- No new test failures; mutation checks all caught.

## Assumptions to confirm later

- Dropping flagged chunks silently from the answer (the user sees a count only in metadata) is acceptable; a UI notice is a follow-up.
- 10 characters for new passwords; existing 8-character passwords keep working for login.
- In-memory throttling is acceptable for a single-worker deployment.

## AMENDMENTS

- The UI notice for withheld passages (listed under assumptions as a follow-up) shipped in this ticket as a small chip in chat.
- Startup checks also cover the Redis password.
