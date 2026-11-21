---
name: prime-frontend
description: Primes the agent with focused understanding of the frontend portion of the codebase — components, routing, state management, and styling — without loading unrelated backend code. Use at the start of a session when the work is scoped to UI or client-side features.
---

# Prime Frontend: Load Frontend Context

## Objective

Build targeted understanding of the frontend codebase by analyzing its structure, components, and conventions. Loading only frontend context keeps the context window light on complex full-stack codebases.

## Process

### 1. Locate the Frontend

List all tracked files to find the frontend root:

!`git ls-files`

Common frontend roots: `frontend/`, `client/`, `web/`, `src/` (when project is frontend-only), `app/` (Next.js). Identify the correct root before proceeding.

### 2. Read Frontend Documentation

- Read CLAUDE.md, `AGENTS.md`, `progress.md` (where we left off) and the relevant part of `spec.md` (for project-wide conventions)
- Read any README inside the frontend root
- Read `.claude/references/frontend-component-best-practices.md` if it exists — it contains project-specific component conventions

### 3. Identify Key Frontend Files

Based on the structure, read:

- Main entry point (`main.tsx`, `index.tsx`, `app/layout.tsx`, `pages/_app.tsx`, etc.)
- Routing configuration (`router.tsx`, `routes.ts`, `app/` directory for Next.js)
- Global state setup (store, context providers)
- Shared component library root (`components/`, `ui/`)
- Core configuration (`package.json`, `tsconfig.json`, `vite.config.ts`, `next.config.ts`)
- One or two representative feature components to internalize the established patterns

Skip files outside the frontend root unless they define a shared type or contract the frontend depends on.

### 4. Understand Current Frontend State

Check recent frontend-relevant activity:

!`git log -10 --oneline`

!`git status`

Note any open changes in the frontend directory.

## Output Report

Provide a concise summary covering:

### Frontend Overview
- Framework and major libraries (React, Vue, Next.js, Tailwind, etc.)
- Component patterns observed (atomic design, feature folders, etc.)
- State management approach

### Directory Map
- Frontend root and key sub-directories with one-line purpose each

### Conventions
- Naming conventions, file co-location rules
- Styling approach
- Testing framework and conventions observed

### Current State
- Active branch, recent frontend changes
- Any immediate concerns (missing types, deprecated patterns, etc.)

**Make this summary easy to scan - use bullet points and clear headers.**
