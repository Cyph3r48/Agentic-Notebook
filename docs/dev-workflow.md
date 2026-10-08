# Dev workflow: plugins, skills and code review

Status: **plan, nothing installed yet.** Everything here was researched from public pages on 2026-10-08 and must be reviewed before installing. Skills and plugins run with the agent's permissions, so read their source first.

## 1. Ponytail (plugin)

- Repo: `DietrichGebert/ponytail` (MIT). Injects a "laziest senior dev" ruleset at session start so the agent prefers deleting or reusing code over writing more. Commands include `/ponytail-audit` (find over-engineering) and `/ponytail-debt`.
- Install (in Claude Code, two separate commands): `/plugin marketplace add DietrichGebert/ponytail`, then `/plugin install ponytail@ponytail`.
- Needs `node` on PATH (it runs two small lifecycle hooks).
- Its published benchmark numbers (less code, cheaper, faster) are the author's own; treat as unverified.
- Only install from the official repo; mirrors exist.

## 2. Skills from `michaelshimeles/skills`

Install: `npx skills add michaelshimeles/skills`. Contents and what we do with each:

| Skill | What it does | Decision |
|---|---|---|
| `new-feature` | Isolated git worktree per task, branched from `origin/main` | Keep (adapt base branch/naming to our branch rules) |
| `code-structure` | Service-layer guidance (actions vs services) | Keep; check it matches our `services`/`repositories` split |
| `evidence-driven-testing` | Records UI test video, posts to PR | Keep, optional (needs FFmpeg/Playwright) |
| `unslop` | Removes AI-writing patterns from prose | Keep for README/docs |
| `before-and-after` | Before/after screenshots into a PR table via `@vercel/before-and-after` | Keep, but see licence note; no Greptile dependency |
| `greploop` | Loops on a PR until Greptile scores 5/5 | **Replace** with an Open Code Review loop |
| `greploop-apps` | Same, triggered by tagging `@greptile-apps` | **Replace** (same) |

Licence note: the repo as a whole states no licence on its page. `before-and-after` is PolyForm Shield 1.0.0 (restricts use that competes with the licensor); `greploop`, `greploop-apps` and `unslop` are MIT; the others state none. Check before redistributing any of it. Prefer vendoring into `.claude/skills/` rather than depending on the repo at runtime.

## 3. Replacing Greptile with Open Code Review

There are two unrelated projects with this name; **pick one** (open question in `spec.md`):

- **Alibaba `open-code-review`** (`alibaba/open-code-review`, Apache-2.0). CLI `ocr`, forge-agnostic: reviews any local git diff. `npm install -g @alibaba-group/open-code-review`, needs Git 2.41+ and Node 18+. Works with OpenAI- and Anthropic-compatible endpoints (Ollama support unconfirmed). Commands: `ocr review` (workspace), `ocr review --from main --to <branch>`, `ocr review --format json --output result.json`, `ocr scan`. **Recommended**, because it runs locally and so fits the privacy goal.
- **open-codereview.ai** (`@open-code-review/cli`): multi-persona GitHub PR reviewer with a local dashboard, Node 22.5+.

### Replacement skill: `ocrloop` (to be written)

Same shape as `greploop`, with the Greptile parts swapped out:

1. Run `ocr review --from <base> --to HEAD --format json --output .ocr/result.json`.
2. Parse findings. **Unknown today:** the JSON schema, severity fields and exit codes are not documented on the pages I could read, so first run `ocr` once on this repo and write the gate against the real output.
3. Fix actionable findings, run tests, commit.
4. Repeat until no findings at or above the chosen severity, or `--max-iterations` (default 5) is hit.
5. Optionally post a summary comment on the PR (never required; no external reviewer to wait for or poll).

Differences from `greploop` worth noting: no polling or 10-minute timeout, no `@greptile review` comment, no dependence on GitHub; the "5/5 confidence" stop condition becomes "zero findings at/above threshold". Because the reviewer is an LLM we configure, it needs a key; the loop must respect the privacy policy (use a local/Ollama model for sensitive repos).

### `before-and-after`

Does not depend on Greptile, so it can stay as is. Two tweaks: the default image host is `0x0.st`, a public anonymous host, so for private work use the Gist option or commit images to the PR branch; and its pre-flight step installs a global npm package, so install it ourselves up front.

## 4. Dark Factory / software factory

The term (Dan Shapiro's top level of AI-assisted coding): agents take work from an issue queue, implement, test, and ship with little or no human code review. The only installable skill I found is a MindStudio tutorial that scaffolds the harness; **no skill named "Dark Factory" exists in `michaelshimeles/skills`**. Please share the exact repo you meant.

Proposed shape for this project (our own, built from skills above):

1. **Spec** — `spec.md` + an issue per task with acceptance criteria.
2. **Plan** — agent proposes the plan; human approves for anything touching security, providers or migrations.
3. **Implement** — `new-feature` worktree, `code-structure` and Ponytail rules.
4. **Verify** — tests, lint, `evidence-driven-testing` for UI.
5. **Review** — `ocrloop`.
6. **Merge gate** — CI green + zero findings above threshold. A human approves merges while the evaluators are young; relax later.

The honest bottlenecks of a dark factory are spec quality and evaluator coverage. Until the test suite covers the provider, memory and decision layers, autonomy should stay limited to low-risk changes.
