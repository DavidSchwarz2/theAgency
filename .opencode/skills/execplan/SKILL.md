---
name: execplan
description: >
  Create, implement, discuss, and maintain Execution Plans (ExecPlans) — self-contained design
  documents that guide a coding agent or novice through delivering a working feature or system
  change. USE WHEN: (1) creating a new ExecPlan for a complex feature or significant refactor,
  (2) implementing an existing ExecPlan, (3) discussing or revising an ExecPlan, (4) researching
  a design with significant unknowns that needs prototyping milestones. Also use when the user
  mentions "ExecPlan", "execution plan", or "plan" in the context of feature delivery.
---

# ExecPlans

An ExecPlan is a living, self-contained design document that enables a stateless agent or human
novice to deliver a working, observable result by reading it top to bottom. It contains all
knowledge and instructions needed to succeed — no prior context, no external references.

The agent executing an ExecPlan can list files, read files, search, run the project, and run
tests. It does not know any prior context and cannot infer what you meant from earlier
milestones. Repeat any assumption you rely on. Do not point to external blogs or docs; if
knowledge is required, embed it in the plan itself in your own words.

## Modes of Operation

### Authoring a New ExecPlan

Re-read this entire skill before starting. Be thorough in reading (and re-reading) source
material to produce an accurate specification. Start from the skeleton (below) and flesh it out
during research.

### Implementing an ExecPlan

Do not prompt the user for "next steps"; proceed to the next milestone autonomously. Keep all
sections up to date. Resolve ambiguities autonomously. Commit frequently. If you change course
mid-implementation, document why in the Decision Log and reflect the implications in Progress.
Plans are guides for the next contributor as much as checklists for you.

Before starting implementation, re-read the Progress section and the Writing Guidelines. Then
verify compliance with these rules at every stopping point:

- Every Progress entry must include a UTC timestamp, e.g. `- [x] (2025-10-01 13:00Z) ...`.
  Entries without timestamps are non-compliant.
- Narrative sections (Plan of Work, Context and Orientation, etc.) must be prose-first. If you
  find yourself writing a list with more than five items outside the Progress section, stop and
  rewrite it as prose with representative examples.
- **Update the ExecPlan (Progress, Discoveries, Decision Log) before committing.** The plan
  must always be committed together with the code changes it describes — never after. Stage the
  updated plan file as part of the same `git add` that stages the code changes.

After completing the final milestone and validation, follow the project's AGENTS.md for any
post-completion steps (e.g., moving the plan to a completed directory, closing issues).

### Discussing / Revising an ExecPlan

Record decisions in the Decision Log. It must be unambiguously clear why any change was made.
When revising, ensure changes are reflected across all sections (including living-document
sections). Write a note at the bottom of the plan describing the change and the reason.

### Researching / Prototyping

When a design has challenging requirements or significant unknowns, use milestones to implement
proof-of-concepts or "toy implementations" that validate feasibility. Read library source code,
research deeply, include prototypes to guide fuller implementation.

## Non-Negotiable Requirements

1. **Self-contained.** The ExecPlan in its current form contains all knowledge and instructions
   needed for a novice to succeed. Do not say "as defined previously" or "according to the
   architecture doc." Include the explanation, even if repeating yourself.
2. **Living document.** Revise as progress is made, discoveries occur, and decisions are
   finalized. Each revision must remain self-contained.
3. **Novice-enabling.** Enable a complete novice to implement end-to-end without prior repo
   knowledge.
4. **Outcome-focused.** Produce demonstrably working behavior, not merely code changes.
5. **Plain language.** Define every term of art or do not use it.
6. **Prior plans.** If an ExecPlan builds upon a prior ExecPlan and that file is checked in,
   incorporate it by reference. If it is not checked in, include all relevant context from
   that plan directly.

## Writing Guidelines

### Purpose and Intent First

Begin by explaining why the work matters from a user's perspective: what someone can do after
this change that they could not do before, and how to see it working. Then guide through the
exact steps to achieve that outcome.

### Plain Prose

Write in plain prose. Prefer sentences over lists. Avoid checklists, tables, and long
enumerations unless brevity would obscure meaning. Checklists are permitted only in the
Progress section (where they are mandatory). Narrative sections must remain prose-first.

### Define Jargon Immediately

If you introduce a phrase that is not ordinary English ("daemon", "middleware", "RPC gateway",
"filter graph"), define it immediately and remind the reader how it manifests in this repository
(naming the files or commands where it appears).

### Mechanical Changes: Pattern over Enumeration

When a change follows a mechanical pattern applied to many locations (e.g., renaming a function,
migrating an API call style, updating import paths), describe the pattern and its detection
method (e.g., a grep command or regex) rather than enumerating every instance. Include 2-3
representative before/after examples so the pattern is unambiguous. Exhaustive line-by-line
listings bloat the plan without adding clarity — the agent can find the remaining instances from
the pattern description.

### Avoid Common Failure Modes

Do not rely on undefined jargon. Do not describe a feature so narrowly that the resulting code
compiles but does nothing meaningful. Do not outsource key decisions to the reader. When
ambiguity exists, resolve it in the plan itself and explain why you chose that path. Err on the
side of over-explaining user-visible effects and under-specifying incidental implementation
details.

### Observable Outcomes

State what the user can do after implementation, the commands to run, and the outputs they
should see. Phrase acceptance as behavior a human can verify ("after starting the server,
navigating to `http://localhost:8080/health` returns HTTP 200 with body `OK`") rather than
internal attributes ("added a HealthCheck struct"). If a change is internal, explain how its
impact can still be demonstrated (e.g., tests that fail before and pass after).

### Explicit Repository Context

Name files with full repository-relative paths, name functions and modules precisely, describe
where new files should be created. If touching multiple areas, include a short orientation
paragraph that explains how those parts fit together so a novice can navigate confidently. When
running commands, show the working directory and exact command line. When outcomes depend on
environment, state assumptions and provide alternatives.

### Idempotent and Safe

Write steps so they can run multiple times without damage or drift. If a step can fail halfway,
include retry/adaptation instructions. If a migration or destructive operation is necessary,
spell out backups or safe fallbacks. Prefer additive, testable changes.

### Validation is Not Optional

Include instructions to run tests, to start the system if applicable, and to observe it doing
something useful. Describe comprehensive testing for any new features or capabilities. Include
expected outputs and error messages. Show how to prove the change is effective beyond
compilation (e.g., end-to-end scenario, CLI invocation, HTTP request/response transcript).
State the exact test commands and how to interpret results.

### Capture Evidence

When steps produce terminal output, short diffs, or logs, include them as indented examples
within the ExecPlan. Keep them concise and focused on what proves success.

## Formatting Rules

Each ExecPlan is a single Markdown file. When the file content is only the ExecPlan, omit
wrapping triple backticks. If embedding an ExecPlan inside another document, use a single
fenced code block labeled `md`. Do not nest additional triple-backtick code fences inside; use
indented blocks for commands, transcripts, diffs, or code. Use two newlines after every heading.

## Milestones

When work contains two or more independent changes that can each be validated separately, use
milestones. Each milestone should be committable and verifiable on its own. If in doubt, prefer
milestones over a flat plan — they reduce blast radius and make progress legible.

Introduce each milestone with a brief paragraph describing: scope, what will exist at the end
that did not exist before, commands to run, and expected acceptance. Keep it readable as a
story: goal, work, result, proof. Never abbreviate a milestone for brevity — do not leave out
details crucial to future implementation.

Each milestone must be independently verifiable and incrementally implement the overall goal.

Progress and milestones are distinct: milestones tell the story, progress tracks granular work.
Both must exist.

### Prototyping Milestones

It is acceptable — and often encouraged — to include explicit prototyping milestones when they
de-risk a larger change. Examples: adding a low-level operator to a dependency to validate
feasibility, or exploring two composition orders while measuring optimizer effects. Keep
prototypes additive and testable. Label scope as "prototyping"; describe how to run and observe
results; state criteria for promoting or discarding the prototype.

Prefer additive code changes followed by subtractions that keep tests passing. Parallel
implementations (e.g., keeping an adapter alongside an older path during migration) are fine
when they reduce risk. Describe how to validate both paths and how to retire one safely with
tests. For multiple new libraries or feature areas, consider creating spikes that evaluate
feasibility independently, proving external libraries perform as expected in isolation.

## Required Living-Document Sections

Every ExecPlan must contain and maintain these sections:

- **Progress** — Checklist with timestamps. Every stopping point documented, even if splitting
  a partially completed task into "done" vs "remaining". Use timestamps to measure rates of
  progress.
- **Surprises & Discoveries** — Unexpected behaviors, bugs, optimizations, or insights with
  concise evidence (test output is ideal).
- **Decision Log** — Every decision with rationale and date/author.
- **Outcomes & Retrospective** — Summarize outcomes, gaps, and lessons learned at major
  milestones or at completion.

## Skeleton

Use this skeleton when creating a new ExecPlan. Replace bracketed placeholders with real
content. Do not remove any required section.

    # <Short, action-oriented description>

    This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
    Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

    ## Purpose / Big Picture

    Explain in a few sentences what someone gains after this change and how they can see it
    working. State the user-visible behavior you will enable.

    ## Progress

    - [x] (2025-10-01 13:00Z) Example completed step.
    - [ ] Example incomplete step.
    - [ ] Example partially completed step (completed: X; remaining: Y).
    - [ ] ExecPlan finalized: outcomes written, plan moved to completed location per AGENTS.md.

    ## Surprises & Discoveries

    - Observation: ...
      Evidence: ...

    ## Decision Log

    - Decision: ...
      Rationale: ...
      Date/Author: ...

    ## Outcomes & Retrospective

    Summarize outcomes, gaps, and lessons learned at major milestones or at completion.
    Compare the result against the original purpose.

    ## Context and Orientation

    Describe the current state relevant to this task as if the reader knows nothing. Name the
    key files and modules by full path. Define any non-obvious term. Do not refer to prior
    plans.

    ## Plan of Work

    Describe, in prose, the sequence of edits and additions. For each edit, name the file and
    location (function, module) and what to insert or change.

    ## Concrete Steps

    State exact commands to run and where (working directory). When a command generates output,
    show a short expected transcript for comparison. Update this section as work proceeds.

    ## Validation and Acceptance

    Describe how to start or exercise the system and what to observe. Phrase acceptance as
    behavior with specific inputs and outputs. If tests are involved: "run <test command> and
    expect <N> passed; the new test <n> fails before the change and passes after."

    ## Idempotence and Recovery

    If steps can be repeated safely, say so. If a step is risky, provide a safe retry or
    rollback path.

    ## Artifacts and Notes

    Include the most important transcripts, diffs, or snippets as indented examples.

    ## Interfaces and Dependencies

    Name the libraries, modules, and services to use and why. Specify types, traits/interfaces,
    and function signatures that must exist at the end of the milestone. E.g.:

    In crates/foo/planner.rs, define:

        pub trait Planner {
            fn plan(&self, observed: &Observed) -> Vec<Action>;
        }

The bar: a single, stateless agent — or a human novice — can read the ExecPlan from top to
bottom and produce a working, observable result. SELF-CONTAINED, SELF-SUFFICIENT,
NOVICE-GUIDING, OUTCOME-FOCUSED.

Based on: https://developers.openai.com/cookbook/articles/codex_exec_plans
