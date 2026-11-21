# Conventions

Read by `piv-commit` (`## commit`) and `piv-create-pr` (`## pr`). These win over the skills' defaults.

## commit

- Conventional tags: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, with an optional scope: `fix(llm): ...`.
- Subject under 72 characters, imperative, no trailing period. Body explains why, not what the diff already shows.
- One logical change per commit. Never commit `.env`, keys, `logs/`, `.ocr/`, `.venv-be/`, `node_modules/`.
- Run the subject and body through `unslop`. Do not edit the attribution trailer lines the session provides; they are
  required and go last, after a blank line.
- A behavior change needs a test in the same commit, or a line in `progress.md` saying why not.

## pr

- Only when the user asks. Work on the assigned branch; never push elsewhere without permission.
- Title: `<tag>: <what it delivers>`.
- Body sections: Summary, What changed, Validation (state what was **not** run), Notes for the reviewer (deviations,
  risks, known baseline failures), Linked issues. Mirror a PR template if the repo has one.
- State the privacy impact when a change touches providers, memory, or the decision layer.
- End with the attribution line the session provides.
