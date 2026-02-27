# Show Agent Output per Pipeline Step as Markdown (#19)

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

After this change, each step in a running or completed pipeline displays its agent's output
(the "handoff" — what the agent wrote when it finished) as rendered Markdown instead of plain
preformatted text. Additionally, the step that is currently running auto-expands its handoff
section so users can see output as it arrives without having to manually click "view handoff".

A user looking at a pipeline detail view will immediately see the active step's output rendered
beautifully — headers, code blocks, lists, and all — and previously completed steps will show
Markdown too when expanded.

## Progress

- [ ] M1: Install `react-markdown`, render `content_md` as Markdown in `StepRow`, fix `skipped`
       status in `STEP_STATUS_CLASSES`, auto-expand the running step
- [ ] ExecPlan finalized: outcomes written, plan moved to completed location per AGENTS.md.

## Surprises & Discoveries

_(fill in as work proceeds)_

## Decision Log

- Decision: Use `react-markdown` (not `marked` or `remark-react`) because it is the most
  actively maintained React Markdown renderer with zero-config SSR-safe rendering.
  Date/Author: 2026-02-27 / Josie

- Decision: Auto-expand logic: `useState(false)` initial state is replaced with
  `useState(step.status === 'running')` so the step starts expanded when running and collapsed
  otherwise. The expand state is not reactively updated after mount (i.e., we do not add a
  `useEffect` that watches `step.status`) because the component re-renders via polling/SSE and
  the `key` prop on `StepRow` resets state naturally when step identity changes.
  Rationale: keeping it simple — no useEffect needed since the parent re-renders the list on
  every SSE event, passing new `step` props. A newly-started step will mount with `expanded: true`.
  Date/Author: 2026-02-27 / Josie

- Decision: Add `skipped` to `STEP_STATUS_CLASSES` to fix the pre-existing TypeScript gap
  (the `StepStatus` type in `api.ts` already includes `'skipped'` but the Record was missing it).
  Date/Author: 2026-02-27 / Josie

## Outcomes & Retrospective

_(fill in at completion)_

## Context and Orientation

### Where does the handoff content live?

`frontend/src/components/PipelineCard.tsx` — The `StepRow` function component receives a `Step`
prop (from `frontend/src/types/api.ts`). `Step` has `latest_handoff: HandoffResponse | null`.
`HandoffResponse` has `content_md: string` and `metadata: Record<string, unknown> | null`.

Current rendering logic (lines 56–73): if `handoff.metadata` is truthy, render a `<dl>` of
key/value pairs. Otherwise, render `handoff.content_md` inside a `<pre>` tag — plain text, no
Markdown rendering. The change: replace the `<pre>` with a `<ReactMarkdown>` component.

The `expanded` state is initialized to `false` unconditionally. The change: initialize to
`step.status === 'running'`.

### The `skipped` gap

`frontend/src/types/api.ts` line 6 already defines `StepStatus = '...' | 'skipped'`.
`STEP_STATUS_CLASSES` in `PipelineCard.tsx` is typed as `Record<StepStatus, string>` but does
not include `'skipped'`. TypeScript does not currently error here because the Record is not
exhaustively checked at declaration — but it would crash at runtime if a step has status
`'skipped'`. Fix: add `skipped: 'bg-gray-700 text-gray-500'` to the Record.

### Installing react-markdown

`react-markdown` is a React component library. Install it in the frontend workspace:

    npm install react-markdown --workspace=frontend

This adds it to `frontend/package.json` and `node_modules`. After installation, import with:

    import ReactMarkdown from 'react-markdown'

and use as `<ReactMarkdown>{content_md}</ReactMarkdown>`.

### Styling Markdown output

The default `ReactMarkdown` output is unstyled HTML. Apply Tailwind `prose` classes via the
`className` prop on a wrapping `<div>`. Because the pipeline card uses a dark background
(`bg-gray-900`), use `prose-invert` from `@tailwindcss/typography`. If the typography plugin
is not already installed, it needs to be added. Check `frontend/tailwind.config.js` for the
`typography` plugin; if missing, install `@tailwindcss/typography` and add it.

The wrapper: `<div className="prose prose-invert prose-xs max-w-none text-gray-300">`.
`prose-xs` keeps font sizes appropriate for the compact card layout.
`max-w-none` removes the default width cap of the prose plugin.

## Plan of Work

### M1: Single focused change to PipelineCard.tsx (and supporting infrastructure)

**Step 1 — Check/install `@tailwindcss/typography`**

Read `frontend/tailwind.config.js`. If `typography` plugin is present, skip. Otherwise:

    npm install @tailwindcss/typography --workspace=frontend --save-dev

Add to `tailwind.config.js` plugins array: `require('@tailwindcss/typography')`.

**Step 2 — Install `react-markdown`**

    npm install react-markdown --workspace=frontend

**Step 3 — Modify `PipelineCard.tsx`**

Three changes in this file:

a) Add `skipped` to `STEP_STATUS_CLASSES`:

    skipped: 'bg-gray-700 text-gray-500',

b) Change `useState(false)` in `StepRow` to `useState(step.status === 'running')` so the step
starts expanded when running.

c) Replace the `<pre>` rendering of `content_md` with:

    <div className="prose prose-invert prose-xs max-w-none mt-1">
      <ReactMarkdown>{handoff.content_md}</ReactMarkdown>
    </div>

d) Add the import at the top of the file:

    import ReactMarkdown from 'react-markdown'

**Step 4 — Type-check**

    npx nx run frontend:type-check

## Concrete Steps

All commands run from the repo root (`/Users/vwqd2w2/code/iandi/theAgency`).

    # 1. Check if typography plugin is in tailwind config
    # (read frontend/tailwind.config.js)

    # 2. Install dependencies
    npm install react-markdown --workspace=frontend
    # if typography plugin needed:
    npm install @tailwindcss/typography --save-dev --workspace=frontend

    # 3. Edit PipelineCard.tsx (skipped status, auto-expand, ReactMarkdown)

    # 4. Type-check
    npx nx run frontend:type-check

## Validation and Acceptance

`npx nx run frontend:type-check` exits 0. Visually:
- A pipeline with a running step auto-expands showing the latest handoff rendered as Markdown
- Code blocks in agent output appear with monospace styling
- Bullet lists and headings render with proper hierarchy
- A step with `status: 'skipped'` displays a gray badge without a runtime error

## Idempotence and Recovery

Installing npm packages is idempotent. The file edits are small and surgical. If `react-markdown`
causes TypeScript errors (e.g., missing type declarations), check whether `@types/react-markdown`
is needed — since v9, `react-markdown` ships its own types, so no separate `@types` package is
required.

## Artifacts and Notes

The `react-markdown` component renders children as Markdown. Basic usage:

    import ReactMarkdown from 'react-markdown'
    // ...
    <ReactMarkdown>{someMarkdownString}</ReactMarkdown>

`@tailwindcss/typography` provides the `prose` class family. `prose-invert` switches to
light-on-dark colors. `prose-xs` is the extra-small size variant.
