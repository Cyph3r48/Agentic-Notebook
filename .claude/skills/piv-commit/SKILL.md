---
name: piv-commit
description: Creates a new git commit for all uncommitted changes with an atomic, conventionally-tagged message. Use when work is complete and ready to be committed.
---

# Commit: Create a New Commit

Create a new commit for all of our uncommitted changes.

## Process

0. **Read this project's conventions.** `.claude/references/conventions.md` has a `## commit` section; follow it, its rules win over the defaults below.
1. Run `git status && git diff HEAD && git status --porcelain` to see what files are uncommitted.
2. Add the untracked and changed files. Never add `.env`, keys, `logs/`, `.ocr/` or `node_modules/`.
3. Write an atomic commit message with a descriptive summary and a tag such as `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.
4. Apply the `unslop` skill to the subject and body, not to the trailer lines.
5. Append the attribution trailer lines the session instructs (Co-Authored-By and Session). They are required; keep them exactly as given.

## Output

A single commit containing all uncommitted changes, with a conventional-commit-style message
(`<tag>: <atomic description>`) that accurately reflects the work done.

After the commit succeeds, print two clearly labelled summaries:

### What Changed
One short paragraph (3–6 sentences) describing the feature/fix/refactor that was committed — what problem it solves and what files were the key touch points. Write for a developer skimming the git log.

### AI Layer Changes
Only include this section if any files under `.claude/` were modified or added (CLAUDE.md, `.claude/references/`, `.claude/skills/`, `.claude/agents/`, etc.).

List each changed AI-layer file with a one-line note on what evolved and why. If nothing in `.claude/` changed, omit this section entirely.
