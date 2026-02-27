---
name: agent-md
description: "Manage agent instruction files (AGENTS.md, CLAUDE.md, COPILOT.md). USE WHEN adding new instructions/rules to AGENTS.md, refactoring a bloated AGENTS.md, splitting agent instructions into linked files, or deciding where a rule belongs. Follows progressive disclosure principles."
---

# Agent MD

Manage agent instruction files (AGENTS.md, CLAUDE.md, COPILOT.md, etc.) following **progressive disclosure principles** — add new instructions to the right place, or refactor bloated files into organized, linked documentation.

---

## Triggers

Use this skill when:
- Adding new instructions/rules to AGENTS.md
- "refactor my AGENTS.md" / "my AGENTS.md is too long"
- "split my agent instructions" / "organize my agent config"
- "where should I put this rule?"

---

## Quick Reference

| Phase | Action | Output |
|-------|--------|--------|
| 0. Add | Place new instruction in correct location | Updated file(s) |
| 1. Analyze | Find contradictions | List of conflicts to resolve |
| 2. Extract | Identify essentials | Core instructions for root file |
| 3. Categorize | Group remaining instructions | Logical categories |
| 4. Structure | Create file hierarchy | Root + linked files |
| 5. Prune | Flag for deletion | Redundant/vague instructions |

For **adding** a new instruction, run Phase 0 only.
For **refactoring**, run Phases 1-5.

---

## Phase 0: Adding New Instructions

When the user wants to add a new rule or instruction:

1. **Read existing structure**: Read the root `AGENTS.md` and any linked files it references.
2. **Determine scope**: Ask — does this apply to every task, or only a specific domain?
   - **Every task** → root `AGENTS.md`
   - **Specific domain** → find or create the appropriate linked file
3. **Check for conflicts**: Verify the new instruction doesn't contradict existing ones. If it does, use the `question` tool to ask the user which takes precedence.
4. **Place it**: Add the instruction to the correct file, following the existing structure and style.
5. **Verify**: Ensure the root file still links to the target file if a new linked file was created.

---

## Phase 1: Find Contradictions

Identify any instructions that conflict with each other.

**Look for:**
- Contradictory style guidelines (e.g., "use semicolons" vs "no semicolons")
- Conflicting workflow instructions
- Incompatible tool preferences
- Mutually exclusive patterns

**For each contradiction found:**
```markdown
## Contradiction Found

**Instruction A:** [quote]
**Instruction B:** [quote]

**Question:** Which should take precedence, or should both be conditional?
```

Use the `question` tool to ask the user to resolve before proceeding.

---

## Phase 2: Identify the Essentials

Extract ONLY what belongs in the root agent file. The root should be minimal — information that applies to **every single task**.

**Essential content (keep in root):**
| Category | Example |
|----------|---------|
| Project description | One sentence: "Monorepo for a requirement optimization tool" |
| Package manager | Only if not npm (e.g., "Uses pnpm workspaces") |
| Non-standard commands | Custom build/test/lint commands |
| Critical overrides | Things that MUST override agent defaults |
| Universal rules | Applies to 100% of tasks |

**NOT essential (move to linked files):**
- Language-specific conventions
- Testing guidelines
- Code style details
- Framework patterns
- Documentation standards
- Git workflow details

### Monorepo Awareness

In monorepos, also check for sub-directory `AGENTS.md` files. Agent instruction files **merge** — the agent sees all of them. Decide what belongs at each level:

| Level | Content |
|-------|---------|
| **Root** | Monorepo purpose, navigation hints, shared tools |
| **Package** | Package purpose, tech stack, package-specific conventions |

Don't duplicate instructions across levels.

---

## Phase 3: Group the Rest

Organize remaining instructions into logical categories.

**Common categories:**
| Category | Contents |
|----------|----------|
| `python.md` | Python conventions, type hints, import style |
| `typescript.md` | TS conventions, type patterns, strict mode rules |
| `testing.md` | Test frameworks, coverage, mocking patterns |
| `code-style.md` | Formatting, naming, comments, structure |
| `git-workflow.md` | Commits, branches, PRs, reviews |
| `architecture.md` | Patterns, folder structure, dependencies |
| `api-design.md` | REST/GraphQL conventions, error handling |

**Grouping rules:**
1. Each file should be self-contained for its topic
2. Aim for 3-8 files (not too granular, not too broad)
3. Name files clearly: `{topic}.md`
4. Include only actionable instructions

---

## Phase 4: Create the File Structure

**Output structure:**
```
project-root/
├── AGENTS.md                    # Minimal root with links
└── docs/                        # Linked instruction files
    ├── python.md
    ├── typescript.md
    ├── testing.md
    ├── git-workflow.md
    └── architecture.md
```

**Root file template:**
```markdown
# Project Name

One-sentence description of the project.

## Quick Reference

- **Package Manager:** pnpm
- **Build:** `nx build`
- **Test:** `nx test`
- **Lint:** `nx lint`

## Detailed Instructions

For specific guidelines, see:
- [Python Conventions](/docs/python.md)
- [TypeScript Conventions](/docs/typescript.md)
- [Testing Guidelines](/docs/testing.md)
- [Git Workflow](/docs/git-workflow.md)
- [Architecture](.opencode/docs/architecture.md)
```

**Each linked file template:**
```markdown
# {Topic} Guidelines

## Overview
Brief context for when these guidelines apply.

## Rules

### Rule Category 1
- Specific, actionable instruction
- Another specific instruction

### Rule Category 2
- Specific, actionable instruction

## Examples

### Good
\`\`\`python
# Example of correct pattern
\`\`\`

### Avoid
\`\`\`python
# Example of what not to do
\`\`\`
```

---

## Phase 5: Flag for Deletion

Identify instructions that should be removed entirely.

**Delete if:**
| Criterion | Example | Why Delete |
|-----------|---------|------------|
| Redundant | "Use TypeScript" (in a .ts project) | Agent already knows |
| Too vague | "Write clean code" | Not actionable |
| Overly obvious | "Don't introduce bugs" | Wastes context |
| Default behavior | "Use descriptive variable names" | Standard practice |
| Outdated | References deprecated APIs or moved files | No longer applies |
| Stale paths | Documents file paths that may have changed | Poisons context |
| Derivable from tooling | NX target commands, available scripts, project structure | Agent can query at runtime (`nx show project`, `package.json`) |

Present flagged items to the user for confirmation before deleting.

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Keeping everything in root | Bloated, wastes token budget | Split into linked files |
| Too many categories | Fragmentation | Consolidate related topics |
| Vague instructions | Wastes tokens, no value | Be specific or delete |
| Duplicating defaults | Agent already knows | Only override when needed |
| Deep nesting | Hard to navigate | Flat structure with links |
| Documenting file paths | Go stale quickly | Describe capabilities instead |
| Duplicating across monorepo levels | Confusing merges | Each level owns its scope |
| Listing derivable commands | Goes stale, wastes tokens | Let agent discover via tooling |

---

## Execution Checklist

```
[ ] Phase 1: All contradictions identified and resolved
[ ] Phase 2: Root file contains ONLY essentials
[ ] Phase 3: All remaining instructions categorized (3-8 files)
[ ] Phase 4: File structure created with proper links
[ ] Phase 5: Redundant/vague instructions removed
[ ] Verify: Each linked file is self-contained
[ ] Verify: Root file is under 50 lines
[ ] Verify: All links work correctly
[ ] Verify: No duplicate instructions across monorepo levels
```

---

## Verification

After refactoring, verify:

1. **Root file is minimal** — Under 50 lines, only universal info
2. **Links work** — All referenced files exist
3. **No contradictions** — Instructions are consistent across all files
4. **Actionable content** — Every instruction is specific and useful
5. **Complete coverage** — No instructions were lost (unless flagged for deletion)
6. **Self-contained files** — Each linked file stands alone
7. **No monorepo duplication** — Instructions aren't repeated at multiple levels

---

## References

- [A Complete Guide to AGENTS.md](https://www.aihero.dev/a-complete-guide-to-agents-md) — Progressive disclosure principles, instruction budgets, and why minimal root files matter.
- [softaworks/agent-toolkit](https://github.com/softaworks/agent-toolkit/tree/main/skills/agent-md-refactor) — Original agent-md-refactor skill this is based on.
