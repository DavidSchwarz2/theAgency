---
name: github-issue
description: Write and refine GitHub issues (features and bugs). Use when the user wants to create a new GitHub issue, improve an existing issue draft, or refine an open issue on GitHub. Triggers on phrases like "create issue", "write issue", "new issue", "refine issue", "improve issue", "github issue".
---

# GitHub Issue

## Workflow: Write New Issue

### 1. Gather context
- Ask user for a brief description of the feature or bug
- Determine issue type: feature request or bug report
- If codebase context is relevant, explore the repo to inform technical notes

### 2. Draft the issue
- Read [references/templates.md](references/templates.md) for the template and writing guidelines
- Apply the appropriate template (feature or bug)
- Write a concise title: imperative verb + noun phrase, max ~60 chars

### 3. Present draft to user
- Show the full issue (title + body) in a markdown code block
- Ask for feedback; iterate until the user approves

### 4. Create on GitHub
After user approval:
```bash
gh issue create --title "<title>" --label "<bug|enhancement>" --body "$(cat <<'EOF'
<body>
EOF
)"
```
- Add extra `--label` flags only if user requests them
- Report the issue URL back to the user

## Workflow: Refine Existing Issue

### 1. Fetch the issue
```bash
gh issue view <number> --json title,body,labels
```

### 2. Analyze and improve
Read [references/templates.md](references/templates.md) for guidelines. Common improvements:
- Add missing acceptance criteria
- Sharpen vague summary or title
- Separate mixed concerns into distinct issues
- Add technical notes if codebase context helps
- Remove implementation details from summary
- Flag scope creep

### 3. Present changes
- Show a before/after comparison of key sections
- Explain what changed and why

### 4. Update on GitHub
After user approval:
```bash
gh issue edit <number> --title "<title>" --body "$(cat <<'EOF'
<body>
EOF
)"
```

## Key Principles
- **One concern per issue** — split if scope grows beyond ~3 acceptance criteria
- **Testable acceptance criteria** — each item independently verifiable, starts with a verb
- **No implementation in summary** — describe *what* and *why*, not *how*
- **Ask, don't assume** — when context is ambiguous, ask the user before drafting
