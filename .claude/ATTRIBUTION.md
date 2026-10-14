# Third-party agent files

| Path | Source | Licence | Changes |
|---|---|---|---|
| `skills/unslop/` | cursor/plugins via michaelshimeles/skills | MIT (Lauren Tan) | none |
| `skills/prime-*`, `skills/piv-*` | https://github.com/coleam00/skills (fetched 2026-10-08) | MIT (Cole Medin), see `LICENSE.coleam00-skills` | adapted: Jira/Confluence removed, `gh` replaced by GitHub MCP, repo-specific validate commands, branch/PR rules, `ocr` review pass, unslop and attribution trailers |
| `hooks/pre_tool_use_secrets.py`, `session_start_context.py`, `post_tool_use_log.py` | https://github.com/coleam00/skills `hooks/` | MIT (Cole Medin) | `.env.template` allowed, no injected context files, `python3` instead of `uv run` |
| `skills/ocr-review-loop/` | original, modelled on the review-loop idea | project licence | n/a |

Not vendored on purpose: Shimeles's `new-feature`, `code-structure`, `evidence-driven-testing` (no licence stated),
`before-and-after` (PolyForm Shield), `greploop*` (Greptile), and Cole's `ai-software-factory` (no licence file).
