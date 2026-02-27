# Web Dashboard — Issue #6

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

After this change an operator opens a browser to `http://localhost:3000` and sees every
pipeline — what it is called, which steps have run and which are next, and whether the
pipeline is running, waiting for approval, or done. Pipelines waiting for approval show
Approve and Reject buttons directly on the card; clicking them sends the decision to the
backend. Step output (handoffs) can be expanded inline. A dedicated Audit Trail tab lets
the operator filter and browse the full event history. All data stays current without
manual reload because the UI subscribes to the backend's Server-Sent Events stream.

## Progress

- [x] (2026-02-27 09:30Z) ExecPlan written and committed.
- [x] (2026-02-27 09:45Z) Milestone 0: Dependencies installed and router wired up — `tsc --noEmit` clean.
- [x] (2026-02-27 10:00Z) Milestone 1: Pipeline list page — cards with step status badges, live SSE refresh.
- [x] (2026-02-27 10:15Z) Milestone 2: Approval actions — Approve/Reject buttons on waiting-for-approval pipelines.
- [x] (2026-02-27 10:20Z) Milestone 3: Handoff detail expansion — collapsed by default, expandable inline.
- [x] (2026-02-27 10:30Z) Milestone 4: Audit Trail tab — filterable, paginated, linked from a navigation bar.
- [x] (2026-02-27 11:00Z) Backend GET /pipelines list endpoint added with 3 TDD tests (TestListPipelines); 126 backend tests passing.
- [x] (2026-02-27 11:15Z) Post-implementation code-quality review — all MUST FIX / SHOULD FIX resolved (see Surprises & Discoveries).
- [x] (2026-02-27 11:25Z) Commit (code + ExecPlan together). Commit: 9a0462b
- [x] (2026-02-27 11:30Z) ExecPlan moved to completed/, issue closed.

## Surprises & Discoveries

- The `GET /pipelines/{id}` detail endpoint returns a `PipelineDetailResponse` with
  `steps: list[StepStatusResponse]`, where each step has `latest_handoff: HandoffResponse | null`
  (fields: `id`, `content_md`, `metadata: dict | null`, `created_at`). The ExecPlan's Artifacts
  section had an outdated schema (`output`, `metadata_json`). The actual schema was used throughout.

- The `GET /pipelines` list endpoint did not exist; it was added with TDD as part of Milestone 1.
  Route ordering matters: `GET ""` (list) must be registered before `GET "/{pipeline_id}"` (detail)
  to avoid FastAPI treating the path as a parameterised route.

- `Pipeline` (list) and `PipelineDetail` (detail) are distinct shapes — the list response omits
  `steps`. Introduced `PipelineDetail extends Pipeline` in `src/types/api.ts`; `PipelineCard`
  accepts `Pipeline & { steps?: Step[] }` so it works for both list and detail contexts.

- TanStack Query v5 `mutate()` requires the variable argument even when the `mutationFn` has a
  default parameter — use `approve.mutate('')` not `approve.mutate()`.

- `EventSource.onerror` fires on every reconnect attempt, not only on permanent failure. Fixed
  `App.tsx` to check `es.readyState === EventSource.CLOSED` before marking `connected = false`.

- `Number(input)` can produce `NaN` or floats. Added `Number.isInteger` validation for
  `pipeline_id` input in `AuditTrail.tsx` before sending the query.

- `result.scalars().all()` must be called only once per `Result`; the cursor is exhausted
  after the first call. A copy-paste bug caused the list endpoint to return an empty list; fixed
  by assigning to a variable before returning.

## Decision Log

- Decision: Install `@tanstack/react-query` (TanStack Query v5) for all REST data fetching.
  Rationale: the skeleton uses raw `useEffect + fetch` with no caching or refetch. TanStack
  Query gives background refetch, stale-while-revalidate, and mutation state management for
  the approve/reject actions. It is the library called out in the issue acceptance criteria
  technical notes.
  Date/Author: 2026-02-27 / agent

- Decision: Do NOT install shadcn/ui or any other component library.
  Rationale: shadcn requires an initialisation step that rewrites several project config
  files, adds a `components.json`, and has a different path convention. Given the tight
  scope and the existing Tailwind v4 setup, plain utility classes are faster and produce
  zero extra dependencies. We can always add shadcn in a follow-up.
  Date/Author: 2026-02-27 / agent

- Decision: Use React Router v7 (already installed) for two routes: `/` (pipeline list) and
  `/audit` (audit trail). No nested routes for now.
  Rationale: React Router is already in `package.json`; no new dependency needed.
  Date/Author: 2026-02-27 / agent

- Decision: SSE invalidation strategy — on every SSE event that looks like a pipeline state
  change, invalidate the `["pipelines"]` TanStack Query cache so the list refetches
  automatically. This is simpler than parsing SSE payloads into local state.
  Rationale: backend SSE stream already sends heartbeat and pipeline events; refetching on
  any event is cheap and keeps the frontend stateless.
  Date/Author: 2026-02-27 / agent

- Decision: Frontend testing is type-check only (`tsc --noEmit`). No runtime tests.
  Rationale: AGENTS.md explicitly states "Frontend: type-checking only. No runtime tests."
  Date/Author: 2026-02-27 / agent

## Outcomes & Retrospective

Issue #6 is fully implemented. An operator can open `http://localhost:3000` and see all
pipelines as cards, approve or reject waiting pipelines directly from the UI, expand step
handoffs inline, and browse the full audit trail with filters. Live updates arrive via SSE
without manual reload. The backend has a proper `GET /pipelines` list endpoint backed by 3
new tests. All 126 backend tests pass and `tsc -b --noEmit` reports zero errors.

The main lesson: always split list and detail TypeScript types when the backend returns
different shapes — conflating them causes silent `undefined` dereferences at runtime.

## Context and Orientation

### Repository layout

The monorepo has two sub-projects:

- `backend/` — Python/FastAPI, served on port 8000. All REST endpoints are prefixed at the
  root (e.g. `GET /pipelines`, `GET /audit`).
- `frontend/` — Vite + React + TypeScript, served on port 3000. The Vite dev server proxies
  every request starting with `/api` to `http://localhost:8000`, stripping the `/api` prefix.
  So `fetch('/api/pipelines')` reaches `http://localhost:8000/pipelines`.

### Existing frontend files

All source files live in `frontend/src/`:

- `main.tsx` — React 19 entrypoint; mounts `<App />`.
- `App.tsx` — single-page skeleton; opens an SSE connection to `/api/events`, shows a live
  event log, and renders `<AgentList />`.
- `components/AgentList.tsx` — renders agent cards from `/api/registry/agents`.
- `hooks/useAgents.ts` — raw `useEffect + fetch` hook for agent data.
- `index.css` — contains only `@import "tailwindcss"` (Tailwind v4 one-liner setup).

### Backend API endpoints relevant to this dashboard

The following backend REST endpoints already exist and are fully tested:

- `GET /pipelines/{id}` — single pipeline with steps and latest handoff.
  Response shape:

      {
        "id": 1,
        "title": "string",
        "template": "string",
        "prompt": "string",
        "status": "pending|running|waiting_for_approval|done|failed",
        "steps": [
          {
            "id": 1,
            "agent_name": "developer",
            "order_index": 0,
            "status": "pending|running|done|failed",
            "output": "string|null",
            "started_at": "iso|null",
            "finished_at": "iso|null",
            "metadata_json": "string|null"
          }
        ],
        "latest_handoff": "string|null",
        "created_at": "iso",
        "updated_at": "iso"
      }

  Note: there is no `GET /pipelines` list endpoint yet — we need to add it. See Plan of Work.

- `POST /pipelines/{id}/approve` — approve a waiting pipeline. Body: `{"comment": ""}` (optional).
  Returns 200 on success, 409 if not waiting, 404 if not found.

- `POST /pipelines/{id}/reject` — reject a waiting pipeline. Body: `{"comment": ""}`.
  Returns 200 on success, 409 if not waiting, 404 if not found.

- `GET /audit` — list audit events. Query params: `pipeline_id`, `event_type`, `since`, `until`,
  `limit` (default 100), `offset` (default 0). Returns newest first:

      [
        {
          "id": 1,
          "pipeline_id": 1,
          "step_id": 2,
          "event_type": "handoff_created",
          "payload": {},
          "created_at": "iso"
        }
      ]

- `GET /events` — Server-Sent Events stream. Sends `data: {"type": "heartbeat", "ts": ...}`
  roughly every 5 seconds. The `type` field can also be pipeline-specific event names.

- `GET /approvals` — list pending approvals. Returns a list of step objects in `waiting_approval`
  state.

### Dependency versions already installed

- React 19.2, react-dom 19.2
- react-router-dom 7.13.1 (installed, not yet used)
- Tailwind CSS 4.2 via `@tailwindcss/vite` (no config file needed)
- TypeScript ~5.9, strict mode on

Not yet installed but needed:
- `@tanstack/react-query` v5 (for data fetching, caching, and mutations)

### Missing backend endpoint

There is no `GET /pipelines` list endpoint. We must add it to the backend before the frontend
can list pipelines. It should return a paginated or full list of pipelines ordered by
`created_at DESC`. This is a small addition to `backend/app/routers/pipelines.py`.

## Plan of Work

### Milestone 0 — Install dependencies and wire up router

Install TanStack Query:

    cd frontend && npm install @tanstack/react-query

Add the router and query client to `main.tsx`. Wrap the tree in `<BrowserRouter>` (from
`react-router-dom`) and `<QueryClientProvider>` (from `@tanstack/react-query`). Create a
`QueryClient` with default options: `staleTime: 10_000` (10 seconds) and `refetchInterval`
left to per-query configuration.

Replace the placeholder `<App />` content with a simple two-route structure: `/` renders
`<PipelineList />` (to be created in Milestone 1) and `/audit` renders `<AuditTrail />` (to
be created in Milestone 4).

Update `index.html` title from "frontend" to "theAgency".

Add a persistent top navigation bar in `App.tsx` (or a layout component) with links to
`/` (Pipelines) and `/audit` (Audit Trail).

At the end of this milestone, `tsc --noEmit` must pass with zero errors.

### Milestone 1 — Pipeline list with step status badges

First, add a backend `GET /pipelines` list endpoint. In
`backend/app/routers/pipelines.py`, add a route `GET /pipelines` that returns all pipelines
ordered by `created_at DESC`. Reuse the existing `PipelineResponse` schema. Write one test:
`test_list_pipelines_returns_all` — creates two pipelines via `POST /pipelines` and asserts
`GET /pipelines` returns both.

Then build the frontend. Create `src/api/client.ts` — a thin module that exports typed async
functions wrapping `fetch`. Start with `fetchPipelines(): Promise<Pipeline[]>` and
`fetchPipeline(id: number): Promise<Pipeline>`. Define the `Pipeline`, `Step` TypeScript
types in `src/types/api.ts` to match the backend schema described above.

Create `src/hooks/usePipelines.ts` — a TanStack Query hook that calls `fetchPipelines` with
`queryKey: ['pipelines']` and `refetchInterval: 5000`. Also create
`src/hooks/usePipeline.ts` for a single pipeline.

Create `src/components/PipelineCard.tsx`. Each card shows the pipeline title, template,
status badge (colour-coded: blue for running, yellow for waiting_for_approval, green for
done, red for failed, grey for pending), and a row of step badges (small coloured dots or
pills) showing each step's agent name and status. Wrap the card in a `<Link to={...}>`
or make it expandable in place.

Create `src/pages/PipelineList.tsx` — uses `usePipelines`, maps over results to render
`<PipelineCard />` per pipeline. Shows a loading skeleton while fetching and an error
message on failure. Shows "No pipelines yet" when the list is empty.

Add a global SSE subscriber in `App.tsx` (or a dedicated `usePipelineSSE` hook) that opens
`/api/events` via `EventSource`. On any received event, call
`queryClient.invalidateQueries({ queryKey: ['pipelines'] })` so cards refresh automatically.
The existing `App.tsx` SSE code can be adapted for this.

Verify: run `tsc --noEmit` with zero errors.

### Milestone 2 — Approval actions

Create `src/api/client.ts` entries: `approvePipeline(id: number, comment?: string)` and
`rejectPipeline(id: number, comment?: string)`, both `POST` with JSON body
`{ comment: comment ?? "" }`.

Create `src/hooks/useApprovalMutation.ts` — wraps TanStack Query `useMutation`. On success,
call `queryClient.invalidateQueries({ queryKey: ['pipelines'] })` to refresh the list.

In `PipelineCard.tsx`, when `pipeline.status === "waiting_for_approval"`, render a prominent
banner with an "Approve" button (green) and "Reject" button (red). Clicking either shows a
confirmation (or directly calls the mutation — keep it simple, no modal). While the mutation
is in-flight, disable both buttons. On error, show the error message inline on the card.

Verify: `tsc --noEmit` with zero errors.

### Milestone 3 — Handoff detail expansion

In `PipelineCard.tsx` (or a separate `StepList.tsx` child), render each step. When a step
has `output` (non-null), show a small "View handoff" toggle button. On click, expand an
inline `<pre>` block showing the raw output text. Use local `useState<number | null>` to
track which step is expanded. Only one step can be expanded at a time per card.

If the step has `metadata_json`, parse it and additionally display any structured fields
from the handoff (next steps, key decisions, current status — see backend handoff schema).

Verify: `tsc --noEmit` with zero errors.

### Milestone 4 — Audit Trail tab

Create `src/api/client.ts` entry: `fetchAuditEvents(params: AuditQueryParams): Promise<AuditEvent[]>`.
Define `AuditQueryParams` with optional `pipeline_id`, `event_type`, `since`, `until`,
`limit`, `offset`.

Create `src/hooks/useAuditEvents.ts` — TanStack Query hook with `queryKey: ['audit', params]`.
No auto-refetch needed here (audit is historical).

Create `src/pages/AuditTrail.tsx`:
- A filter row at the top: a number input for `pipeline_id`, a text input for `event_type`,
  a datetime-local input for `since`, and a "Filter" button that re-fires the query with
  the new params. All filters are optional.
- Below the filter row, a table with columns: `id`, `pipeline_id`, `step_id`, `event_type`,
  `created_at` (formatted as local datetime), `payload` (JSON-stringified, truncated to 60
  chars with a "..." expand toggle).
- Pagination: "Load more" button that increments `offset` by 50 and appends results.
- Empty state: "No audit events found" message.

Wire up the `/audit` route in the router to render `<AuditTrail />`.

Verify: `tsc --noEmit` with zero errors.

## Concrete Steps

All frontend commands run from `frontend/`. All backend commands run from `backend/`.

### Step 0 — Dependencies

    cd frontend && npm install @tanstack/react-query

Verify no peer-dependency warnings. Then run:

    npm run type-check   # must pass with 0 errors

### Step 1 — Backend list endpoint

In `backend/app/routers/pipelines.py`, add before the existing `GET /pipelines/{id}`:

    @router.get("", response_model=list[PipelineResponse])
    async def list_pipelines(db: Annotated[AsyncSession, Depends(get_db)]) -> list[PipelineResponse]:
        result = await db.execute(select(Pipeline).order_by(Pipeline.created_at.desc()))
        pipelines = list(result.scalars().all())
        return [_to_response(p) for p in pipelines]

Write one TDD test in `test_pipelines_router.py`:

    class TestListPipelines:
        async def test_list_pipelines_returns_all(self, test_client): ...

Run backend tests: `uv run pytest app/tests/test_pipelines_router.py -v`

### Step 2 — Frontend scaffolding (Milestone 0)

Edit `frontend/index.html`: change `<title>frontend</title>` to `<title>theAgency</title>`.

Edit `frontend/src/main.tsx`: add `BrowserRouter` and `QueryClientProvider`.

Create `frontend/src/types/api.ts` with TypeScript types.

Create `frontend/src/api/client.ts` with fetch wrappers.

Create `frontend/src/components/NavBar.tsx`.

Edit `frontend/src/App.tsx`: remove old single-page content, add router outlet with two routes.

### Step 3 — Milestone 1 (pipeline list)

Create files: `src/hooks/usePipelines.ts`, `src/components/PipelineCard.tsx`,
`src/pages/PipelineList.tsx`. Adapt SSE subscriber.

### Step 4 — Milestone 2 (approval)

Create `src/hooks/useApprovalMutation.ts`. Update `PipelineCard.tsx`.

### Step 5 — Milestone 3 (handoff expansion)

Update `PipelineCard.tsx` with inline expansion.

### Step 6 — Milestone 4 (audit trail)

Create `src/hooks/useAuditEvents.ts`, `src/pages/AuditTrail.tsx`.

### Final validation

    cd frontend && npm run type-check    # 0 errors
    cd backend  && uv run pytest app/tests/ -q  # all pass

## Validation and Acceptance

The feature is complete when all of the following hold:

1. `http://localhost:3000/` shows a list of pipelines. Each card has a title, status badge,
   and step badges.
2. A pipeline in `waiting_for_approval` status shows Approve and Reject buttons. Clicking
   Approve sends `POST /api/pipelines/{id}/approve`; the card updates to `running` or `done`.
3. A step with output shows a "View handoff" toggle. Clicking it expands the handoff text.
4. `http://localhost:3000/audit` shows the audit event table with filter controls.
5. The SSE connection keeps the pipeline list current: starting a new pipeline from another
   terminal causes a new card to appear within ~5 seconds without manual reload.
6. `npm run type-check` passes with zero errors.
7. All 123+ backend tests continue to pass.

## Idempotence and Recovery

All `npm install` commands are idempotent. Frontend source changes are additive; nothing
is deleted. The backend list endpoint is a pure read and is safe to add without migration.

## Artifacts and Notes

TypeScript types to define in `src/types/api.ts`:

    export type PipelineStatus = 'pending' | 'running' | 'waiting_for_approval' | 'done' | 'failed'
    export type StepStatus = 'pending' | 'running' | 'done' | 'failed'

    export interface Step {
      id: number
      agent_name: string
      order_index: number
      status: StepStatus
      output: string | null
      started_at: string | null
      finished_at: string | null
      metadata_json: string | null
    }

    export interface Pipeline {
      id: number
      title: string
      template: string
      prompt: string
      status: PipelineStatus
      steps: Step[]
      latest_handoff: string | null
      created_at: string
      updated_at: string
    }

    export interface AuditEvent {
      id: number
      pipeline_id: number
      step_id: number | null
      event_type: string
      payload: Record<string, unknown> | null
      created_at: string
    }

Status badge colour mapping (Tailwind utility classes):

    pending          → bg-gray-500
    running          → bg-blue-500 animate-pulse
    waiting_for_approval → bg-yellow-500
    done             → bg-green-500
    failed           → bg-red-500
