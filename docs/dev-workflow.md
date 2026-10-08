# Dev workflow: the software factory

Status: **installed (supervised level).** Skills, hooks and the review loop are in `.claude/`. Ponytail is a plugin you install yourself, and a session restart is needed for new skills to load. Provenance and licences: `.claude/ATTRIBUTION.md`.

Skills and plugins run with the agent's permissions. Read a skill's source before it goes into `.claude/`, and vendor files instead of depending on a remote repo at runtime.

## 1. What we are combining

| Source | What it is | Licence |
|---|---|---|
| **Shimeles** `michaelshimeles/skills` | A short, opinionated workflow: isolate, build, prove, ship. Seven skills plus an `AGENTS.md` template. | `unslop` MIT. `new-feature`, `code-structure`, `evidence-driven-testing`: **none stated**. `before-and-after`: PolyForm Shield. `greploop*`: MIT. |
| **Cole's skills** `coleam00/skills` | 35 skills built around a plan, implement, validate loop (PIV), plus hooks and meta-skills, including `build-dark-factory`. | MIT |
| **Cole's factory** `coleam00/ai-software-factory` | A ready-made unattended factory. Issues in, merged PRs out, driven by a scheduler and Archon workflows pinned to one revision of a third-party repo. | **No LICENSE file** |
| **Ponytail** `DietrichGebert/ponytail` | Plugin that makes the agent prefer deleting or reusing code over writing more. | MIT |
| **Open Code Review** `alibaba/open-code-review` | Local `ocr` CLI for AI code review. Replaces Greptile. | Apache-2.0 |

The two Cole repos overlap. `build-dark-factory` is a skill that builds a factory into your repo one component at a time and works with any coding agent. `ai-software-factory` is one finished factory that depends on Archon. We use the skill and borrow ideas from the factory. We do not install the factory yet (section 6).

## 2. Verdict

- **Shimeles** gives us the shortest correct workflow and the best multi-agent hygiene (one worktree per task, scope check against open PRs, never plain `--force`). Its weakness is that it ends in Greptile and has no planning step.
- **Cole's skills** give us the structure Shimeles lacks: priming, planning, a single validate verdict, fresh-eyes review, and hooks that enforce rules in code instead of asking nicely. Its weakness is size. 35 skills cost about 4,400 tokens of always-on context, so we take a subset.
- **Cole's factory** has the best ideas about trusting a merge nobody reads (a mission with an out-of-scope list, hidden holdout scenarios, calibrating the verifier with deliberate faults, a halt switch). It is too heavy and too trusting for a repo with this little test coverage.

## 3. The combined loop

```
prime -> plan -> isolate -> implement -> validate -> review -> prove -> commit -> (PR only when asked)
```

| Step | Skill | From | State |
|---|---|---|---|
| Prime | `prime-codebase`, `prime-backend`, `prime-frontend` | Cole | **installed** (Jira/Confluence step removed) |
| Plan | `piv-plan-implementation` | Cole | **installed** (GitHub MCP for tickets; asks clarifying questions, then stops) |
| Isolate | assigned branch (see `CLAUDE.md`) | n/a | Shimeles's `new-feature` not vendored (no licence); Claude Code manages worktrees |
| Implement | `piv-implement`, Ponytail, layering rules in `CLAUDE.md` | Cole, Ponytail | **installed**; Ponytail is yours to install |
| Validate | `piv-validate` | Cole | **installed**, wired to this repo's real commands and baseline |
| Review | `ocr-review-loop` → `piv-review-changes` + `ocr delegate` | Cole, Alibaba | **installed** |
| Fix | `piv-fix-review-findings` | Cole | **installed** |
| Prove | `evidence-driven-testing` | Shimeles | deferred (no licence; needs Playwright/FFmpeg; wait for UI work) |
| Write | `unslop` | Shimeles via Cursor | **installed** |
| Commit | `piv-commit` + `.claude/references/conventions.md` | Cole | **installed**; keeps attribution trailers |
| PR | `piv-create-pr`, `piv-review-pr` | Cole | **installed**, GitHub MCP, **only when asked** |

Skipped for now: `piv-run-full-loop` (chains steps without a human checkpoint), `worktree-create/merge` (we run one task at a time), `before-and-after` (see below), the signal-engine, second-brain and tutor skills (unrelated), and `greploop`, `greploop-apps` (Greptile).

### Where `code-structure` lands in this repo

Its "actions" are our `api/v1/endpoints`, its "service layer" is `services`, and DB access stays in `repositories`. Services return structured results and never touch tables directly. The extraction trigger (two or more callers) matches Ponytail's bias, so the two agree.

### `piv-validate` commands

```
backend:   make test-backend            (Docker; same suite CI runs)
frontend:  cd frontend && npm run lint
```

There is no type checker or frontend test runner yet. Adding them is on the `progress.md` list. A validate step that only runs what exists will say PASS about code nobody tests, so the verdict must print what it did not run.

## 4. Code review: Alibaba Open Code Review replaces Greptile

Verified 2026-10-08 with `ocr` v1.12.12 (`npm install -g @alibaba-group/open-code-review`; Git 2.41+, Node 18+).

**Delegation mode is the default here.** `ocr delegate preview` lists the reviewable files and `ocr delegate rule <files>`
prints the review rules grouped by language (Python rules cover dead code, mutable defaults, edge cases, error handling,
resource management, performance and more, each with "do not report" exceptions). No LLM key is needed: the agent applies
the rules itself. That fits the privacy goal, because the diff goes nowhere. It skips Markdown and other unsupported types.

The loop is the `ocr-review-loop` skill: scope, review with a fresh-context agent, verify each finding is real, fix with tests,
`piv-validate`, repeat until nothing at or above the threshold or 3 iterations. It replaces `greploop`: no polling, no
`@greptile` comment, no GitHub dependency.

**API mode** (`ocr review --format json`, `ocr config provider`) runs ocr's own LLM review and can use Anthropic or
OpenAI-compatible endpoints; Ollama support is unconfirmed. It sends the diff to that provider and its JSON schema and
exit codes are undocumented where I looked, so nothing gates on it yet. Run it once before relying on it.

`before-and-after` does not use Greptile, so it can stay in principle. It is PolyForm Shield licensed, uploads to the
public host `0x0.st` by default, and needs a global npm install. Deferred until there is UI work to show.

## 5. Hooks

Installed in `.claude/hooks/`, registered in `.claude/settings.json`, and tested in both directions (block and allow):

| Hook | What it does here |
|---|---|
| `pre_tool_use_secrets` | Blocks routes to `.env`, keys, `.ssh`, `.aws`, and recursive-force deletes. Allows `.env.example` and `.env.template` (local change). Matches text crudely, so a command that only mentions a blocked pattern is refused too. |
| `session_start_context` | Injects branch, uncommitted files and recent commits. `progress.md` is read through `CLAUDE.md`, not injected. |
| `post_tool_use_log` | Appends one JSON line per tool call to `logs/agent-actions.jsonl` (gitignored). |

They run with `python3` (standard library only), not `uv`. Known gaps from the hook author: `@file` mentions bypass tool hooks, and a
written script can read the environment. Treat it as a guard rail, not a vault. All three fail open.

Not installed: `stop_tests_must_pass` (needs a test command that runs without a Docker daemon; the native suite has 4 known
environment failures, so it would trap sessions), `pre_tool_use_dependencies` (needs a coupling map we have not earned yet),
`stop_notify` (desktop only).

## 6. How autonomous, and when

`build-dark-factory` builds in this order: guidance layer, validation harness, workflow-driven repo, deployment, and the scheduler last. We follow it, and stop at a level the tests justify.

| Level | What happens | Entry condition |
|---|---|---|
| **Now: supervised factory** | Agent plans, builds, validates, reviews with `ocr`. A human approves the plan for risky areas and merges every PR. | Skills installed, `piv-validate` filled in |
| **Next: gated factory** | Agent also opens PRs and fixes review findings in a loop. Human still merges. | `ocrloop` works; CI covers provider, memory and decision layers; `MISSION.md` with out-of-scope list written |
| **Later: dark factory** | Scheduler picks issues, merges on green plus zero findings. | Holdout scenarios kept **outside** the builder's checkout; verifier calibrated with deliberate faults; halt switch tested; a human watched at least one full lap |

Why not install `ai-software-factory` now:
- No LICENSE file, so we cannot copy it into a repo.
- It pins Archon to one commit of a third-party repo, and its own README describes that source as depending on workflow changes still being merged upstream.
- It runs unattended with merge authority and expects the agent to run as root with `IS_SANDBOX=1`.
- It needs `gh` with the `workflow` scope, `bun`, `uv`, and journeys that exercise the running app. We have no E2E journeys and thin tests.
- Its own README says the hard half is trusting a merge nobody read. We have not built that trust yet.

What we take from it now: the `MISSION.md` out-of-scope list (seven things a reasonable person would ask for that we refuse), a `halt` mechanism, and the rule that hidden scenarios must be physically hidden from the builder.

## 7. Cloud-session adaptations

- No `gh` CLI: the installed skills use the GitHub MCP tools (`ToolSearch` loads them if deferred).
- Docker has a client but no daemon, so `piv-validate` runs the backend suite natively in a venv without torch (see the skill and the baseline in `progress.md`).
- Project rules override skills: no PR unless asked, work on the assigned branch, no force-push.
- New hooks and settings apply from the next session start.

## 8. What you run yourself

Plugin installs are interactive, so run these in Claude Code:

```
/plugin marketplace add DietrichGebert/ponytail
/plugin install ponytail@ponytail
```

Ponytail needs `node` on PATH. Its benchmark claims are the author's own. Then restart the session and check `/skills`.
