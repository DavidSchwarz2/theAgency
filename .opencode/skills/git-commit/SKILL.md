---
name: git-commit
description: Use when creating git commits - analyzes changes, ensures code quality, generates conventional commit messages with issue number
---

# Git Commit Skill

## Workflow

### 1. Verify no sensitive information present
Check staged changes for secrets, credentials, or tokens. If found → abort and ask user to remove them.

### 2. Code review (non-trivial changes only)
Review all modified files for quality. Resolve all MUST FIX and SHOULD FIX findings before proceeding.

### 3. Determine GitHub issue reference
- Take GitHub issue number from session context
- If no GitHub issue number known → ask user
- Always use `Related to #<number>` — never use `Closes`

### 4. Commit message format

```
type(scope): Subject line in imperative mood

Optional body (only when necessary).

Related to #123

[GitHub Copilot]
```

**Types:**
- `feat` – observable behavior change (logging, errors, API, UI); includes adding, removing, or silencing any output that operators or users can observe (e.g. removing progress bars, suppressing console noise)
- `fix` – bug fix
- `refactor` – refactoring only, no behavior change
- `test` – test additions/changes only
- `build` – dependencies, build config
- `ci` – GitHub Actions, pipeline changes
- `style` – formatting, linting only (whitespace, semicolons, import order — never output changes)
- `docs` – documentation

**Scope (optional):** Derived from affected file paths (e.g. `backend`, `frontend`, `infra`). Omit if changes span multiple areas.

**Subject:** max 50 chars, imperative mood, specific about what and where, no counts or metrics (e.g. not "fix 4 files" or "resolve 15 errors")

**Body** (rare – only when the *why* is non-obvious and cannot be inferred from the code):
- One single statement explaining why, not what or how
- No bullet points, no lists
- No summary of changes
- Wrap at 72 characters

**Footer:**
- `Related to #<number>` – always; never use `Closes`
- MUST end with `[GitHub Copilot]`

### 5. Execute
```bash
git commit -m "<message>"
```

## Examples

Simple (most commits):
```
feat(backend): remove tqdm progress bars from processing loops

Related to #123

[GitHub Copilot]
```

Style-only (formatting/linting changes that do not affect output):
```
style(backend): remove unused imports in document analyzer

Related to #123

[GitHub Copilot]
```

With body (rare):
```
feat(backend): add retry logic to external API calls

Chose exponential backoff over circuit breaker due to
upstream service SLA requirements.

Related to #456

[GitHub Copilot]
```

## Key principles
- **Quality first** – review code and resolve findings before committing
- **Atomic commits** – one logical purpose per commit
- **Concise** – subject says what, body (if needed) says why
- **Ask for guidance** – issue number if unknown
