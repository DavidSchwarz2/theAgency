# AGENTS.md — elhico (Requirement Optimization Tool)

Monorepo: Python/FastAPI backend + Next.js/React frontend + AWS CDK infrastructure.
Managed with **NX** and **mise** (`.mise.toml`).

**[ARCHITECTURE.md](ARCHITECTURE.md) for module map, boundaries, invariants.**

## Environment Setup

`mise install && mise run deps` — installs tooling + all dependencies + creates `.env` files from examples.

- **LLM provider**: set `LLM` in backend `.env` — `gemini`, `openai`, `anthropic`, `gcp_gemini`.
- **Database**: PostgreSQL 16 with pgvector. `DATABASE_URL` in backend `.env`.

## Pre-commit

Husky runs `nx affected -t lint type-check test --exclude=frontend` then `git add -u`.

## Post-implementation Review

After non-trivial changes, run a self-review before marking complete:

1. Run the **code-quality** agent (Task tool, `subagent_type: code-quality`) on all modified files
2. Resolve all **MUST FIX** and **SHOULD FIX** findings
3. Run `nx lint <project>`, `nx type-check <project>`, `nx test <project>`; fix all errors/warnings
4. Repeat steps 1–3 until the code-quality agent reports no MUST FIX or SHOULD FIX findings
5. Summarize improvements in final message

Skip for: trivial changes, doc-only changes, user requests skip.

## ExecPlans

For complex features or significant refactors, use an ExecPlan from design through implementation. Use the **execplan** skill.

- Name: `<github-issue>_<short_title>.md` (omit issue prefix if none)
- Active plans: `docs/exec-plans/active/`
- Completed plans: move to `docs/exec-plans/completed/`
- The ExecPlan file **must be staged in the same commit** as the code changes it documents. Never commit code changes without the corresponding ExecPlan update.

## Branching

Trunk-based development. Default branch: **main**.

- Commit directly to main for single-agent work.
- Use short-lived feature branches when multiple agents work in parallel. Rebase onto main and merge as soon as the work is complete.
- Keep commits small and incremental.
- No long-lived feature branches or Git Flow.

## Commits

Use the **git-commit** skill. Conventional commit messages with Github issue numbers.

## Testing

- **Backend**: test-driven development (red/green/refactor) is MANDATORY for service logic, domain rules, and API
  endpoints. Write the failing test first, make it pass, then refactor both production and test code. **One test at a
  time** — never write the next test until the current one passes and the code is refactored.
- **Frontend**: type-checking only (`tsc --noEmit`). No runtime tests.
- **Never delete or skip failing tests.** Fix the implementation or fix the test.

## Detailed Guidelines

- [Backend conventions](docs/backend.md) — logging, error handling, async, database, testing
- [Frontend conventions](docs/frontend.md) — components, state, data fetching
