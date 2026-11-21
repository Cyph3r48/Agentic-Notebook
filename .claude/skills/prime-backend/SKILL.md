---
name: prime-backend
description: Primes the agent with focused understanding of the backend portion of the codebase — API routes, services, data models, and database layer — without loading unrelated frontend code. Use at the start of a session when the work is scoped to API endpoints, business logic, or data access.
---

# Prime Backend: Load Backend Context

## Objective

Build targeted understanding of the backend codebase by analyzing its structure, routes, services, and data layer. Loading only backend context keeps the context window light on complex full-stack codebases.

## Process

### 1. Locate the Backend

List all tracked files to find the backend root:

!`git ls-files`

Common backend roots: `backend/`, `server/`, `api/`, `app/` (FastAPI/Django), `src/` (when project is backend-only). Identify the correct root before proceeding.

### 2. Read Backend Documentation

- Read CLAUDE.md, `AGENTS.md`, `progress.md` (where we left off) and the relevant part of `spec.md` (for project-wide conventions)
- Read any README inside the backend root
- Read `.claude/references/backend-api-best-practices.md` if it exists — it contains project-specific API conventions

### 3. Identify Key Backend Files

Based on the structure, read:

- Main entry point (`main.py`, `app.py`, `server.ts`, `index.ts`, etc.)
- Route registration / router index (`routes/`, `api/`, `routers/`)
- Core configuration (`pyproject.toml`, `package.json`, `tsconfig.json`)
- Database configuration and ORM setup (`database.py`, `db.ts`, `alembic.ini`)
- Core data models or schemas (`models/`, `schemas/`)
- One or two representative feature slices (route + service + model) to internalize established patterns
- Middleware and dependency injection setup

Skip files outside the backend root unless they define a shared type or contract the backend exposes.

### 4. Understand Current Backend State

Check recent backend-relevant activity:

!`git log -10 --oneline`

!`git status`

Note any open migrations, pending schema changes, or in-progress API changes.

## Output Report

Provide a concise summary covering:

### Backend Overview
- Framework and major libraries (FastAPI, Django, Express, NestJS, etc.)
- Language and runtime version
- Database and ORM (PostgreSQL + SQLAlchemy, MongoDB + Mongoose, etc.)

### Directory Map
- Backend root and key sub-directories with one-line purpose each

### Architecture Patterns
- How routes, services, and data access are layered
- Dependency injection or middleware patterns observed
- Error handling approach

### Conventions
- Naming conventions, module organization
- Migration tooling and current migration state
- Testing framework and conventions observed

### Current State
- Active branch, recent backend changes
- Any pending migrations or schema changes
- Any immediate concerns (missing validation, unhandled errors, etc.)

**Make this summary easy to scan - use bullet points and clear headers.**
