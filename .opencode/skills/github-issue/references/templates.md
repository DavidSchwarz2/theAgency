# Issue Templates

## Feature Request

```markdown
## Summary
<!-- 1-2 sentences: what and why -->

## Motivation
<!-- Problem being solved or opportunity. Link to user feedback, metrics, or related issues if available. -->

## Acceptance Criteria
<!-- Checklist of observable, testable outcomes -->
- [ ] ...
- [ ] ...

## Technical Notes
<!-- Optional: pointers to relevant code, architecture constraints, dependencies, migration concerns -->

## Out of Scope
<!-- Optional: explicitly exclude related work to keep the issue focused -->

## Open Questions
<!-- Optional: unresolved design decisions or unknowns -->
```

## Bug Report

```markdown
## Summary
<!-- 1-2 sentences: what is broken -->

## Steps to Reproduce
1. ...
2. ...

## Expected Behavior
<!-- What should happen -->

## Actual Behavior
<!-- What happens instead. Include error messages, screenshots, or logs if available. -->

## Environment
<!-- Optional: browser, OS, deployed environment, relevant versions -->

## Acceptance Criteria
- [ ] ...

## Technical Notes
<!-- Optional: suspected root cause, relevant code paths -->
```

## Writing Guidelines

- **Title**: imperative verb + noun phrase, max ~60 chars (e.g. "Add retry logic to document upload", "Fix crash on empty search query")
- **Summary**: state the *what* and *why* in 1-2 sentences; avoid implementation details
- **Acceptance criteria**: each item independently verifiable; use checkboxes; start with a verb (e.g. "User sees...", "API returns...", "Error message includes..."). Describe *outcomes*, not implementation — no class names, env vars, SDK calls, or specific tool/library references. Implementation details belong in Technical Notes. A good litmus test: if the AC would still hold after a complete rewrite of the internals, it's at the right abstraction level.
- **Technical notes**: only include when non-obvious; point to files/modules, not line numbers
- **Labels**: apply `bug` or `enhancement` via `gh` flags; add additional labels only if the user specifies them
- **Scope**: one concern per issue; if a description grows beyond ~3 acceptance criteria, consider splitting
