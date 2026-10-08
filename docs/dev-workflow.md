# Dev workflow: the software factory

Status: **plan, partly installed.** Researched 2026-10-08 from the sources below. Only `unslop` is installed so far (`.claude/skills/unslop/`). Everything else here waits for approval.

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
| Prime | `prime-codebase`, `prime-backend`, `prime-frontend` | Cole | adopt after reading |
| Plan | `piv-plan-implementation` | Cole | adopt after reading |
| Isolate | `new-feature` | Shimeles | install locally via `npx skills add` (no licence to vendor); Claude Code already manages worktrees |
| Implement | `piv-implement`, `code-structure`, Ponytail | Cole, Shimeles | adopt; map `code-structure` onto our layers (below) |
| Validate | `piv-validate` | Cole | adopt, fill in our commands (below) |
| Review | `piv-review-changes` + `ocr review` | Cole, Alibaba | adopt; see section 4 |
| Prove | `evidence-driven-testing` | Shimeles | defer until UI work; needs Playwright/FFmpeg |
| Write | `unslop` | Shimeles via Cursor | **installed** |
| Commit | `piv-commit` | Cole | adopt; keep the attribution trailers |
| PR | `piv-create-pr` | Cole | only when asked (project rule) |

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

Install: `npm install -g @alibaba-group/open-code-review` (Git 2.41+, Node 18+). Configure with `ocr config provider` and `ocr config model`. Ollama support is unconfirmed; check before relying on it for private repos.

Replacement for `greploop`, called `ocrloop` (to be written after one real run):

1. `ocr review --from <base> --to HEAD --format json --output .ocr/result.json`
2. Read findings. The JSON schema, severity fields and exit codes are not documented on the pages I read, so run it once here and write the gate against the real output.
3. Fix actionable findings, rerun `piv-validate`, commit.
4. Stop at zero findings at or above the chosen severity, or after 5 iterations.

No polling, no `@greptile` comment, no dependence on GitHub. `ocr` is a second opinion from a model that did not write the code, which is the part of Greptile we wanted. `.ocr/` goes in `.gitignore`.

`before-and-after` does not use Greptile, so it can stay in principle. It is PolyForm Shield licensed, uploads to the public host `0x0.st` by default (use a Gist or in-branch images for private work), and needs a global npm install. Defer until there is UI work to show.

## 5. Hooks (tranche 2, after I read each script)

Cole's `hooks/` are the part I most want, because a rule asks and a hook guarantees. Not installed yet because I have read only `pre_tool_use_secrets.py` and the README, not the other five.

| Hook | Use here |
|---|---|
| `pre_tool_use_secrets` | Yes. Blocks routes to `.env`, keys, and `rm -rf`. Matters more once provider API keys exist. |
| `session_start_context` | Yes. Injects branch and recent commits. Pairs with `progress.md`. |
| `post_tool_use_log` | Yes. Audit trail in `logs/` (gitignored). |
| `stop_tests_must_pass` | **Not yet.** Our tests need Docker. A stop hook that cannot run the tests would trap the session. Enable once there is a test command that runs without Docker. |
| `pre_tool_use_dependencies` | Later. Declare couplings such as migration and model files. |
| `stop_notify` | Optional, desktop only. |

Hooks run through `uv`, so `uv` must be available. The secrets hook documents its own gaps (`@file` mentions bypass it; a written script can read the environment). Treat it as a guard rail, not a vault.

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

This session has no `gh` CLI; GitHub goes through the GitHub MCP tools. Skills that call `gh` (`new-feature` scope check, `piv-create-pr`, `piv-review-pr`) need a note telling the agent to use the MCP equivalents. Project rules also override skills: no PR unless asked, work on the assigned branch, no force-push.

## 8. What you run yourself

Plugin installs are interactive, so run these in Claude Code:

```
/plugin marketplace add DietrichGebert/ponytail
/plugin install ponytail@ponytail
```

Optionally, for the Shimeles skills with no vendorable licence:

```
npx skills add michaelshimeles/skills --skill new-feature code-structure evidence-driven-testing
```

Ponytail needs `node` on PATH. Its benchmark claims are the author's own.
