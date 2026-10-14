---
name: piv-implement
description: Executes an implementation plan task-by-task with validation at every step. Use when you have a completed feature plan and want to implement it in one pass.
argument-hint: [path-to-plan]
---

# Execute: Implement from Plan

## Plan to Execute

Read plan file: `$ARGUMENTS`

## Before you start: branch and plan

Work on the branch the session assigned (see `CLAUDE.md`). Do not create a new branch and do not touch `main`. If
`git status` shows unrelated uncommitted changes, stop and ask. Run `piv-validate` once first so you know the
baseline: a failure that exists before you start is not yours, and a failure you add is.

## Execution Instructions

### 1. Read and Understand

- Read the ENTIRE plan carefully
- Understand all tasks and their dependencies
- Note the validation commands to run
- Review the testing strategy

### 2. Execute Tasks in Order

For EACH task in "Step by Step Tasks":

#### a. Navigate to the task
- Identify the file and action required
- Read existing related files if modifying

#### b. Implement the task
- Follow the detailed specifications exactly
- Maintain consistency with existing code patterns
- Include proper type hints and documentation
- Add structured logging where appropriate

#### c. Verify as you go
- After each file change, check syntax
- Ensure imports are correct
- Verify types are properly defined
- **Run the task's own `VALIDATE` command before starting the next task.** Every task in the plan carries one.
  A task is not done until its check passes — if it fails, fix it now rather than carrying the failure forward.
  The full suite still runs at step 4; this is the per-task gate that keeps step 4 from becoming a pile-up.

### 3. Implement Testing Strategy

After completing implementation tasks:

- Create all test files specified in the plan
- Implement all test cases mentioned
- Follow the testing approach outlined
- Ensure tests cover edge cases

### 4. Run Validation Commands

Execute ALL validation commands from the plan in order:

```bash
# Run each command exactly as specified in plan
```

If any command fails:
- Fix the issue
- Re-run the command
- Continue only when it passes

### 5. Final Verification

Before completing:

- ✅ All tasks from plan completed
- ✅ All tests created and passing
- ✅ All validation commands pass
- ✅ Code follows project conventions
- ✅ Documentation added/updated as needed

## Output — write an implementation report

Write a short report to `.claude/reports/<plan-slug>-report.md` (and print the summary). This is what the PR body
and the `piv-review-pr` gate read — especially the **deviations** (a documented deviation is an *intentional*
decision the reviewer should not flag):

```markdown
# Implementation Report — <feature>

**Plan**: <path>   **Branch**: <feature/...>   **Status**: COMPLETE | PARTIAL

## Summary
{What was built, 2-4 sentences.}

## Tasks completed
- [task] → `path/to/file` (CREATE/UPDATE)

## Tests added
{Test files + cases + results.}

## Validation results
{Type-check / lint / tests / build — pass/fail with counts.}

## Deviations from the plan
{What changed vs the plan and WHY — or "none". This is the reviewer's signal of intent.}

## Issues encountered
{Anything notable, or "none".}
```

### Ready for the next step
- Confirm all changes are complete and validations pass.
- Update `progress.md` (move the item, add a Log line, write the next step).
- Next: `piv-review-changes`, fix what it finds with `piv-fix-review-findings`, then `piv-commit`. Open a PR with `piv-create-pr` only if the user asked for one.

## Notes

- If you encounter issues not addressed in the plan, document them
- If you need to deviate from the plan, explain why
- If tests fail, fix implementation until they pass
- Don't skip validation steps
