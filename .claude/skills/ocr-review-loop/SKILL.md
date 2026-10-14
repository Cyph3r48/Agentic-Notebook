---
name: ocr-review-loop
description: Review the current changes with Open Code Review rules, fix what is real, validate, and repeat until no findings at or above the severity threshold remain or the iteration cap is hit. Replaces the Greptile review loop. Use after implementing a change and before committing or asking for a PR.
argument-hint: "[--base <branch>] [--max-iterations 3] [--threshold medium]"
---

# OCR review loop

A local replacement for a hosted review loop. Nothing is posted anywhere and no external reviewer is waited on. The
reviewer is an agent that did not write the change (use a subagent via the `Agent` tool when you can), applying the
`ocr` rulebook.

Defaults: base = the branch point from the default branch, max iterations 3, threshold `medium` (fix critical, high
and medium; list low as suggestions).

## Loop

1. **Scope.** `ocr delegate preview` (workspace changes) or `ocr delegate preview --from <base> --to HEAD`. If `ocr`
   is missing, install it: `npm install -g @alibaba-group/open-code-review` (Git 2.41+, Node 18+). It skips Markdown
   and other unsupported types; review those by reading.
2. **Review.** Run `piv-review-changes` (it pulls the rules with `ocr delegate rule <files>`). A fresh-context subagent
   is preferred. Apply the rules' own "do not report" exceptions.
3. **Verify.** Each finding must be real: reproduce it or point to the line that proves it. Drop the rest and say why.
4. **Fix.** `piv-fix-review-findings` for the real ones at or above the threshold, each with a test.
5. **Validate.** `piv-validate`. A new failure outside the known baseline sends you back to step 4.
6. **Stop** when an iteration finds nothing at or above the threshold, or at the cap. At the cap, report what remains;
   do not claim clean.

## Report

Per iteration: findings count by severity, fixed, dropped (with reason), validation verdict. At the end: remaining
findings and what was not covered (Markdown, files `ocr` excludes, anything `piv-validate` lists under "Not run").

## API mode (optional, unverified)

With a provider configured (`ocr config provider`, `ocr config model`), `ocr review --from <base> --to HEAD --format json
--output .ocr/result.json` runs ocr's own LLM review. Its JSON schema and exit codes were not documented where I
looked and need one real run before a script gates on them. Privacy: that mode sends the diff to the configured
provider, so for sensitive code use Ollama or stay in delegation mode (the default here).
