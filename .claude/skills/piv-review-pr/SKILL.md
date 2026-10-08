---
name: piv-review-pr
description: Review an open pull request with fresh eyes (project validation, the diff, the Open Code Review rules), rank issues by severity, save a report, and post it to GitHub only if the user asked. Uses the GitHub MCP tools, not the gh CLI. Use after piv-create-pr when a PR review is wanted.
argument-hint: "<pr-number | pr-url | branch>"
---

# Review PR

**Input**: $ARGUMENTS

The point is fresh eyes: review in a clean context, not the one that wrote the code, which rationalizes instead of
scrutinizing. Prefer handing the deep pass to a separate subagent (`Agent` tool) that only gets the PR number and the
standards, not the author's reasoning.

Posting a review or comment is outward-facing. Write the report to disk first, show the user the verdict, and post
only when they asked for it. Every GitHub post ends with the attribution footer the session specifies.

## Phase 1: Fetch the PR

Use the GitHub MCP tools (`pull_request_read` for details, diff and changed files). Cloud sessions have no `gh`.
State guard: merged or closed means stop; draft means review direction, do not approve or block.

## Phase 2: Load the bar

- `CLAUDE.md`, `spec.md` sections the PR touches, `.claude/references/`.
- The implementation report (`.claude/reports/*`) if one exists. A documented deviation is an intentional decision,
  not an issue; flag only undocumented divergences.
- The PR title and body: what problem it claims to solve.

## Phase 3: Validation

Run `piv-validate` on the PR's head. A red suite is a finding, but separate known baseline failures (listed in
`piv-validate`) from new ones.

## Phase 4: Review the diff

Read every changed file in full, not just the diff. Apply `piv-review-changes` criteria plus the `ocr` rules:

```bash
ocr delegate preview --from {base} --to HEAD
ocr delegate rule <changed files...>
```

Also check this repo's own rules from `CLAUDE.md`: no sensitive content to disallowed providers, no swallowed
provider/Qdrant/embedding errors, no secrets, tests with behavior changes.

| Severity | Meaning |
|---|---|
| Critical | Blocking: security, data loss, crashes |
| High | Fix before merge: logic errors, missing error handling, type-safety holes |
| Medium | Pattern inconsistencies, missing edge cases, undocumented deviations |
| Low | Suggestions and polish |

Say what is done well too.

## Phase 5: Decide

Approve: no critical or high issues, validation as expected, matches intent. Request changes: high issues or new
failures. Block: critical security or data issues. Never approve over an unresolved critical issue. Approval is the
human's call; you recommend.

## Phase 6: Save, then post if asked

Write `.claude/code-reviews/pr-{N}-review.md` (summary · issues by severity with `file:line` and fix · validation
table with "Not run" · what is good · recommendation). If the user asked you to post it, use the GitHub MCP review
tools (`pull_request_review_write`, or `add_issue_comment` for an advisory comment).

## Output

PR number and URL, issue counts by severity, validation results, the recommendation, and the report path. If there are
issues, the next step is `piv-fix-review-findings`. Remind the user that merging is theirs.
