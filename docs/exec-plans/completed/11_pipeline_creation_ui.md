# Add Pipeline Creation UI to Web Dashboard

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

Right now, users can only start a pipeline by calling the backend REST API directly (e.g. with curl).
After this change, there will be a "New Pipeline" button in the web dashboard that opens a modal form.
The user fills in a title, selects a pipeline template from a dropdown, enters a prompt, and optionally
a branch name. Submitting the form POSTs to the backend and the new pipeline immediately appears in
the list. The "No pipelines yet. Start one via the API." empty-state message is updated to remove
the stale API instruction.

To see it working: start the dev stack (`mise run dev`), navigate to `http://localhost:5173`, click
"New Pipeline" in the top-right of the Pipelines page header, fill the form, click Create — the modal
closes and the new pipeline card appears in the list.

## Progress

- [x] (2026-02-27 10:00Z) ExecPlan written.
- [x] (2026-02-27 10:05Z) Milestone 1: Added `PipelineCreateRequest`, `PipelineTemplateStepResponse`, `PipelineTemplateResponse` to `types/api.ts`; added `createPipeline` and `fetchPipelineTemplates` to `api/client.ts`.
- [x] (2026-02-27 10:08Z) Milestone 2: Created `hooks/useCreatePipeline.ts`.
- [x] (2026-02-27 10:10Z) Milestone 3: Created `components/NewPipelineModal.tsx` with form, loading state, error display, ARIA, focus management, Escape key, retry affordance for template load failure.
- [x] (2026-02-27 10:12Z) Milestone 4: Updated `PipelineList.tsx` with "New Pipeline" button, modal wiring, updated empty-state message, fixed error guard, removed no-op Tailwind class.
- [x] (2026-02-27 10:15Z) Type-check passes: `npx nx run frontend:type-check` — 0 errors.
- [x] (2026-02-27 10:20Z) Code-quality review: resolved all MUST FIX (headers spread order in `apiFetch`, stale closure in `useEffect`) and all SHOULD FIX (asymmetric guards, submit disabled while loading, focus trap + ARIA + Escape, error guard).
- [x] (2026-02-27 10:25Z) Second type-check after fixes: still clean.
- [x] (2026-02-27 10:30Z) ExecPlan finalized: outcomes written, plan moved to completed location per AGENTS.md.

## Surprises & Discoveries

- Observation: `apiFetch` had a latent bug where `options` was spread after the `headers` object,
  meaning any caller-provided headers would silently overwrite the `Content-Type` header for POST
  requests. Fixed to spread `options` first, then merge headers on top.
  Evidence: Code review flagged the spread order as MUST FIX.

- Observation: TanStack Query `useMutation` returns a stable `reset` reference, so it can safely be
  added to the `useEffect` dependency array rather than suppressing the exhaustive-deps lint rule.
  Evidence: Removing the eslint-disable and adding `reset` to deps passed type-check without issues.

## Decision Log

- Decision: Use a React controlled form with local state rather than a form library (react-hook-form, etc).
  Rationale: The form has only four fields; adding a form library would be disproportionate complexity.
  Date/Author: 2026-02-27 / agent

- Decision: Load templates via a separate TanStack Query (`useQuery`) call inside the modal component
  rather than passing them down from the parent.
  Rationale: Keeps `PipelineList` lean; the modal is only mounted when open so the query only fires
  when needed.
  Date/Author: 2026-02-27 / agent

## Outcomes & Retrospective

The pipeline creation UI is fully implemented. Users can now click "New Pipeline" in the dashboard
header, fill in a title, select a template from a live-fetched dropdown, write a prompt, and
optionally specify a branch. The modal handles loading, error, and retry states for the template
list, disables submission while in-flight, traps focus, closes on Escape, and exposes proper ARIA
attributes. On success the modal closes and the new pipeline card appears immediately via TanStack
Query invalidation.

Two latent bugs in the existing `client.ts` were also fixed as part of the code-quality pass:
the headers spread-order bug and the asymmetric `undefined` guard in `fetchAuditEvents`.

Frontend type-check passes cleanly with zero errors.

## Context and Orientation

The application is a monorepo. The frontend lives in `frontend/` and is a Vite + React + TypeScript
single-page app. Styling uses Tailwind CSS. Data fetching uses TanStack Query v5 (`@tanstack/react-query`).

The relevant files are:

- `frontend/src/types/api.ts` — shared TypeScript interfaces that mirror the backend REST response shapes.
- `frontend/src/api/client.ts` — all `fetch` calls to the backend REST API, each wrapped in typed helper
  functions. All paths are prefixed with `/api` (Vite proxies `/api/*` to `http://localhost:8000/*`,
  stripping the `/api` prefix).
- `frontend/src/hooks/` — TanStack Query hooks. Each file exports one hook. Queries use `useQuery`;
  mutations use `useMutation`.
- `frontend/src/components/` — reusable UI components (PipelineCard, NavBar, etc.).
- `frontend/src/pages/PipelineList.tsx` — the Pipelines page. Currently renders a list of `PipelineCard`
  elements but has no way to create a new pipeline from the UI.

The backend endpoint that creates a pipeline:
  POST /pipelines
  Body (JSON): { template: string, title: string, prompt: string, branch?: string }
  Returns: the created pipeline object (HTTP 201), shaped like the `Pipeline` interface in `api.ts`.

The backend endpoint that lists available pipeline templates:
  GET /registry/pipelines
  Returns: array of objects, each with { name: string, description: string, steps: [...] }.
  Currently available template names: "full_feature", "quick_fix", "issue_only".

The `Pipeline` type in `api.ts` represents the list-endpoint shape (no steps field):
  { id, title, template, status, created_at, updated_at }

The TanStack Query v5 `useMutation` hook's `mutate()` function always requires the variable argument
even when the mutation function uses a default. Call `mutate(variableValue)`, never bare `mutate()`.

## Plan of Work

The work is split into four milestones, each independently verifiable.

**Milestone 1 — Types and API client functions.**
Add two new interfaces to `frontend/src/types/api.ts`:
- `PipelineCreateRequest`: the body sent to `POST /pipelines` — fields `template`, `title`, `prompt`
  (all strings, required) and `branch` (optional string).
- `PipelineTemplateResponse`: one item from `GET /registry/pipelines` — fields `name`, `description`
  (both strings), and `steps` (array of objects with `type`, `agent` (optional string), and `description`).

Then add two new functions to `frontend/src/api/client.ts`:
- `createPipeline(req: PipelineCreateRequest): Promise<Pipeline>` — POSTs to `/pipelines` with the
  request body serialised as JSON. Returns the created `Pipeline`.
- `fetchPipelineTemplates(): Promise<PipelineTemplateResponse[]>` — GETs `/registry/pipelines`.

Both functions use the existing `apiFetch` helper and follow the same pattern as the existing functions.
Update the import line to also import `PipelineCreateRequest` and `PipelineTemplateResponse`.

**Milestone 2 — `useCreatePipeline` hook.**
Create `frontend/src/hooks/useCreatePipeline.ts`. This file exports a single function
`useCreatePipeline()` that wraps TanStack Query's `useMutation`. The mutation function calls
`createPipeline` from the API client. On success it invalidates the `['pipelines']` query so that
the newly created pipeline immediately appears in the list. The hook returns the mutation object
so callers can access `mutate`, `isPending`, and `error`.

**Milestone 3 — `NewPipelineModal` component.**
Create `frontend/src/components/NewPipelineModal.tsx`. The component accepts two props:
- `open: boolean` — whether the modal is visible.
- `onClose: () => void` — called when the modal should close (user cancels or form submits successfully).

Inside the component, load templates with a TanStack Query `useQuery` that calls
`fetchPipelineTemplates`. The query key is `['pipeline-templates']`. Because the template list never
changes at runtime, set `staleTime: Infinity` to avoid redundant refetches.

Local form state holds four fields: `title` (string, default `''`), `template` (string, default `''`),
`prompt` (string, default `''`), `branch` (string, default `''`).

When the form is submitted, call `createPipeline.mutate({ title, template, prompt, branch: branch || undefined })`.
On success (`onSuccess` option of `useMutation`), call `onClose()`.

The modal renders as a fixed full-screen overlay (dark semi-transparent backdrop) with a centred card.
Inside the card: a heading "New Pipeline", the four form fields, a loading/error state, and two
buttons: "Cancel" (calls `onClose`) and "Create" (submit, disabled while `isPending`).

If `open` is false, return `null` so the modal is not in the DOM.

Reset form fields to their defaults when the modal opens (when `open` transitions from false to true).
Use a `useEffect` with `[open]` as the dependency array; reset only when `open === true`.

The template dropdown shows a placeholder option "Select a template" (value `""`, disabled) and then
one option per `PipelineTemplateResponse`. While templates are loading show a single disabled option
"Loading templates…". If template fetch fails, show a disabled option "Failed to load templates".

All fields are required for submission — use the native HTML `required` attribute so the browser
handles empty-field validation without extra code.

Style using Tailwind classes consistent with the rest of the app (dark theme: `bg-gray-900`,
`border-gray-800`, `text-white`, etc.).

**Milestone 4 — Wire modal into `PipelineList` page.**
Modify `frontend/src/pages/PipelineList.tsx`:
- Import `useState` from React and `NewPipelineModal` from `@/components/NewPipelineModal`.
- Add local state `const [modalOpen, setModalOpen] = useState(false)`.
- Render `<NewPipelineModal open={modalOpen} onClose={() => setModalOpen(false)} />` inside the
  return JSX.
- Add a "New Pipeline" button to the page header (top-right). Place the button next to the "Pipelines"
  heading in a flex row.
- Update the empty-state paragraph from "No pipelines yet. Start one via the API." to
  "No pipelines yet."

## Concrete Steps

All commands are run from the repo root `/Users/vwqd2w2/code/iandi/theAgency` unless noted.

**Step 1: Edit `frontend/src/types/api.ts`** — append the two new interfaces after the last line.

**Step 2: Edit `frontend/src/api/client.ts`** — update the import line, then append the two new functions.

**Step 3: Create `frontend/src/hooks/useCreatePipeline.ts`**.

**Step 4: Create `frontend/src/components/NewPipelineModal.tsx`**.

**Step 5: Edit `frontend/src/pages/PipelineList.tsx`** — add button, modal, reset empty-state message.

**Step 6: Type-check**

    npx nx run frontend:type-check

Expect zero errors.

## Validation and Acceptance

Run `npx nx run frontend:type-check` from the repo root. Expect output ending with something like:

    > nx run frontend:type-check
    ...
    Done in X.XXs.

No errors means the TypeScript is structurally sound. Since AGENTS.md specifies frontend validation
is type-checking only (no runtime tests), this is the full automated gate.

For manual verification: start the dev stack with `mise run dev`, navigate to `http://localhost:5173`,
and confirm:
1. A "New Pipeline" button is visible in the Pipelines page header.
2. Clicking it opens a modal with Title, Template, Prompt, and Branch fields.
3. The Template dropdown is populated from the backend (requires backend running).
4. Submitting with valid values closes the modal and the new pipeline appears in the list.
5. The empty-state message no longer says "Start one via the API".

## Idempotence and Recovery

All changes are additive (new files or appended code to existing files). Re-running type-check is
safe. If a type error appears, read the compiler message and fix the offending type annotation.

## Artifacts and Notes

Backend schema for reference (from `backend/app/schemas/pipeline.py`):

    class PipelineCreateRequest(BaseModel):
        template: str
        title: str
        prompt: str
        branch: str | None = None

    class PipelineTemplateResponse(BaseModel):
        name: str
        description: str
        steps: list[dict]   # each dict has 'type', 'agent' (optional), 'description'

## Interfaces and Dependencies

In `frontend/src/types/api.ts`, add:

    export interface PipelineCreateRequest {
      template: string
      title: string
      prompt: string
      branch?: string
    }

    export interface PipelineTemplateStepResponse {
      type: string
      agent?: string
      description: string
    }

    export interface PipelineTemplateResponse {
      name: string
      description: string
      steps: PipelineTemplateStepResponse[]
    }

In `frontend/src/api/client.ts`, add:

    export function createPipeline(req: PipelineCreateRequest): Promise<Pipeline>
    export function fetchPipelineTemplates(): Promise<PipelineTemplateResponse[]>

In `frontend/src/hooks/useCreatePipeline.ts`, export:

    export function useCreatePipeline(): UseMutationResult<Pipeline, Error, PipelineCreateRequest>

In `frontend/src/components/NewPipelineModal.tsx`, export:

    export default function NewPipelineModal(props: { open: boolean; onClose: () => void }): JSX.Element | null
