---
name: piv-create-pr
description: Push the current feature branch and open a pull request, only when the user has explicitly asked for one. Detects the base branch, pushes, opens the PR with a clear body (summary, what changed, validation, deviations), and returns the URL. Uses the GitHub MCP tools, not the gh CLI.
argument-hint: "[--base <branch>] (default: auto-detected)"
---

# Create PR

**Only run this when the user explicitly asked for a PR.** This repo's rule is no PR unless asked (see `CLAUDE.md`).
If the session names a PR template location or rules, follow them.

The implementation is committed on the assigned branch. Cloud sessions have no `gh` CLI; use the GitHub MCP tools
(load them with `ToolSearch` if they are deferred): `create_pull_request`, `list_pull_requests`, `pull_request_read`.

## Phase 0: Base branch

1. `--base <branch>` in `$ARGUMENTS`, else
2. `git symbolic-ref refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@'`, else
3. the repository's default branch from the GitHub MCP, else `main`.

## Phase 1: Validate git state

```bash
git branch --show-current
git status --short
git log origin/{base}..HEAD --oneline
```

| State | Action |
|---|---|
| On `{base}` | STOP: the work belongs on the assigned branch. |
| Uncommitted changes | STOP: commit with `piv-commit` first. |
| No commits ahead of `{base}` | STOP: nothing to PR. |
| A PR for this branch already exists (`list_pull_requests` with `head`) | STOP and print its URL. |
| Anything else | PROCEED |

If the branch's earlier PR was merged, treat follow-up work as new: restart the branch from the latest base as the
session instructions say, and open a new PR. Never reuse a merged one.

## Phase 2: Gather the body

- `.claude/references/conventions.md`, `## pr` section: its rules win.
- Look for a PR template: `.github/pull_request_template.md`, `.github/PULL_REQUEST_TEMPLATE.md`, root
  `PULL_REQUEST_TEMPLATE.md`, `docs/PULL_REQUEST_TEMPLATE.md`. If one exists, mirror its headings and fill them from the
  diff. Skip any section that asks for credentials, tokens or anything unrelated to the diff.
- `git log origin/{base}..HEAD --pretty=format:"- %s"` and `git diff --stat origin/{base}..HEAD`.
- The implementation report in `.claude/reports/` if present: summary, validation results, and **documented
  deviations** (these tell the reviewer what was intentional).
- Linked issue numbers from commits or the branch name.

Apply the `unslop` skill to the title and body. End the body with the attribution line the session instructs.

## Phase 3: Push and open

```bash
git push -u origin HEAD
```

Then `create_pull_request` with `head` = the branch, `base` = `{base}`, title `{type}: {concise description}`, and a body:
Summary (1-2 sentences) · What changed · Validation (from `piv-validate`, including "Not run") · Notes for the reviewer
(deviations, risks) · Linked issues. Use a draft PR if the work is not ready.

## Output

PR number and URL, `head` into `base`, and the next step: ask whether to run `piv-review-pr` and whether to
subscribe to PR activity. Do not merge.
