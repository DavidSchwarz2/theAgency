# Pipeline Restart

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

After this change, a user can restart a failed pipeline — either one that crashed, timed out,
or was aborted — without having to create a brand-new run from scratch. The pipeline resumes
from the first step that has not yet completed (`done`), using the last successful step's
handoff as context. A **Restart** button appears on failed pipeline cards in the dashboard.

The endpoint is `POST /pipelines/{id}/restart`. It returns the updated pipeline object with
`status: running`. The frontend mirrors the pattern of the existing Abort action.

## Progress

- [x] (2026-02-27 16:30Z) ExecPlan written
- [x] (2026-02-27 16:31Z) GitHub issue #20 created
- [x] (2026-02-27 16:35Z) RED: wrote 3 failing tests for restart endpoint
- [x] (2026-02-27 16:38Z) GREEN: implemented `restart_pipeline` router endpoint; all 3 tests pass
- [x] (2026-02-27 16:45Z) REFACTOR: extracted `_launch_pipeline_background_task` helper to eliminate duplication with `create_pipeline`; added 2 additional SHOULD FIX tests (409 on done, DB status assertion); fixed local import alias in test
- [x] (2026-02-27 16:50Z) Frontend: `restartPipeline` in `client.ts`, `useRestartMutation` hook, `RestartButton` in `PipelineCard`
- [x] (2026-02-27 16:52Z) Frontend type-check clean; 213 backend tests pass
- [x] (2026-02-27 16:55Z) Code-quality agent review; all MUST FIX and SHOULD FIX resolved
- [x] (2026-02-27 16:57Z) ExecPlan finalized: outcomes written, plan moved to `docs/exec-plans/completed/`

## Surprises & Discoveries

- The `_run_in_background` closure in `create_pipeline` was copy-pasted verbatim into
  `restart_pipeline` — extracted into `_launch_pipeline_background_task` helper. The refactor
  required `import collections.abc` to satisfy the ruff UP035 rule (Callable/Coroutine must
  come from `collections.abc` not `typing`).
- `resume_pipeline` already handles failed steps correctly without an explicit status reset —
  `_execute_steps` sets each step to `running` at the start, overwriting `failed`.
- `template=None` in `resume_pipeline` is intentional: the method reconstructs context from
  stored DB handoffs and does not need the template definition at all.

## Decision Log

- Decision: Reset failed steps to `pending` before re-running them, not `skipped`.
  Rationale: A failed step needs to be retried; marking it `skipped` would imply it was
  intentionally bypassed. Resetting to `pending` means the runner treats it as not yet started,
  which is the correct semantic for a retry.
  Date/Author: 2026-02-27 / Josie

- Decision: Reuse `resume_pipeline` logic rather than duplicating it.
  Rationale: `resume_pipeline` already handles "find first non-done step, build prompt from
  last handoff" correctly. The restart endpoint just needs to reset failed steps and call it.
  Date/Author: 2026-02-27 / Josie

- Decision: 409 when pipeline is not `failed`.
  Rationale: Consistent with `abort` (409 when not `running`) and `approve`/`reject` (409 when
  not `waiting_for_approval`). Restart on a running or done pipeline would be semantically wrong.
  Date/Author: 2026-02-27 / Josie

- Decision: Do not introduce a new `restarted` status.
  Rationale: The pipeline transitions directly to `running` — adding a new status would require
  frontend changes to every status-aware component and adds no observable value.
  Date/Author: 2026-02-27 / Josie

## Outcomes & Retrospective

`POST /pipelines/{id}/restart` is live. Failed pipelines can now be retried from the first
non-completed step without re-entering a prompt. The UI shows a "Restart" button on every
failed pipeline card. The background-task lifecycle (DB session, runner wiring,
active_runners/approval_events cleanup) is now a single shared helper used by both
`create_pipeline` and `restart_pipeline`, eliminating the duplication. 213 backend tests pass;
frontend type-check is clean.

## Context and Orientation

### Current State

The project is a Python/FastAPI backend + React/TypeScript frontend in an NX monorepo.

**Key backend files:**

- `backend/app/models.py` — SQLAlchemy ORM models. `Pipeline` has a `status` column typed
  `PipelineStatus` (a Python `StrEnum`): `pending`, `running`, `waiting_for_approval`, `done`,
  `failed`. `Step` has `status: StepStatus`: `pending`, `running`, `done`, `failed`, `skipped`.
- `backend/app/services/pipeline_runner.py` — `PipelineRunner` class. The `resume_pipeline`
  method (line 434) picks up from the first step that is not `done`, reconstructs the prompt
  from prior handoffs, and calls `_execute_steps`. It is currently used only for crash recovery
  on server startup.
- `backend/app/routers/pipelines.py` — FastAPI router. The abort endpoint
  (`POST /pipelines/{id}/abort`, line 293) is the closest structural parallel to the new
  restart endpoint.
- `backend/app/tests/test_pipelines_router.py` — all router tests. The `test_client` fixture
  (line 42) sets up an in-memory SQLite DB, mock OpenCode client, and all `app.state` keys.
- `backend/app/schemas/pipeline.py` — Pydantic response/request schemas.

**Key frontend files:**

- `frontend/src/api/client.ts` — typed HTTP client; all calls go through `apiFetch`.
- `frontend/src/hooks/useApprovalMutation.ts` — pattern to copy for `useRestartMutation`.
- `frontend/src/components/PipelineCard.tsx` — card component. Shows `ApprovalBanner` for
  `waiting_for_approval` pipelines. The restart button follows the same conditional-render
  pattern.

### How `resume_pipeline` Works

`resume_pipeline` loads all steps with their handoffs. It iterates over done steps to find the
last successful handoff and sets it as `current_prompt`. It then collects all steps where
`status != done` and calls `_execute_steps` on them. If there are no remaining steps it marks
the pipeline `done` immediately.

**Important:** `resume_pipeline` does **not** reset any step statuses. A step that is `failed`
has `status != done`, so it would be picked up as a remaining step — but `_execute_steps`
starts each step by setting its status to `running`, which overwrites `failed`. This means
`resume_pipeline` already handles failed steps correctly without an explicit reset. No status
reset is needed in the restart endpoint.

### Background Task Pattern

Every pipeline runs as an `asyncio` background task. The task is stored in
`app.state.pipeline_tasks[pipeline_id]`. An `asyncio.Event` for approval gating is stored in
`app.state.approval_events[pipeline_id]`. An `active_runners` dict holds the live
`PipelineRunner` instance. The restart endpoint must:

1. Register a new `asyncio.Event` in `app.state.approval_events`.
2. Create and start a background task that calls `resume_pipeline`.
3. Store the task in `app.state.pipeline_tasks`.
4. Register a done-callback that removes it from `pipeline_tasks`.

This mirrors the `_run_in_background` closure in `create_pipeline` (router lines 185–206).

## Plan of Work

### Milestone 1 — Backend: `POST /pipelines/{id}/restart`

**Step 1 — Write the failing test** in `test_pipelines_router.py`.

Add a new test class `TestRestartPipeline` at the end of the file. It needs three tests:

1. A pipeline in `failed` status is restarted successfully (200, status becomes `running`).
2. A pipeline that is not `failed` returns 409.
3. A pipeline that does not exist returns 404.

For test 1, use the same `patch("app.routers.pipelines.PipelineRunner")` pattern used in
`TestAbortPipeline`. Create a `Pipeline` row in the DB with `status=PipelineStatus.failed` and
at least one `Step` row with `status=StepStatus.failed`. Mock `PipelineRunner` so
`resume_pipeline` returns immediately (use `AsyncMock`). Assert the response status is 200 and
the returned body has `status == "running"`.

**Step 2 — Implement the endpoint** in `backend/app/routers/pipelines.py`.

Add a new route just below the `abort_pipeline` route (around line 333):

    @router.post("/{pipeline_id}/restart", response_model=PipelineResponse)
    async def restart_pipeline(
        pipeline_id: int,
        db: Annotated[AsyncSession, Depends(get_db)],
        client: Annotated[OpenCodeClient, Depends(get_opencode_client)],
        request: Request,
    ) -> PipelineResponse:

Logic:

1. Fetch the pipeline; raise 404 if not found.
2. If `pipeline.status != PipelineStatus.failed`, raise 409 with detail
   `f"Pipeline is not failed (status={pipeline.status})"`.
3. Set `pipeline.status = PipelineStatus.running`, `pipeline.updated_at = datetime.now(UTC)`.
4. Commit.
5. Register an `asyncio.Event` in `app_state.approval_events[pipeline_id]`.
6. Build a `_run_in_background` closure (identical pattern to `create_pipeline`) that opens a
   fresh DB session, fetches the pipeline, constructs a `PipelineRunner`, calls
   `runner.resume_pipeline(bg_pipeline, template=None)`, and cleans up `active_runners`.
7. Create the task, store in `app_state.pipeline_tasks[pipeline_id]`, attach done-callback.
8. Return `PipelineResponse.model_validate(pipeline)`.

The `effective_registry` is not needed here because `resume_pipeline` does not look up agent
profiles from the registry by name — it reads step records from the DB which already contain
`agent_name`. However, `PipelineRunner` requires `registry` to be non-None (checked at the
start of `resume_pipeline`). Pass `request.app.state` registry via a new
`Depends(get_registry)` parameter, same as in `create_pipeline`.

### Milestone 2 — Frontend

**Step 1** — Add `restartPipeline(id)` to `frontend/src/api/client.ts`:

    export function restartPipeline(id: number): Promise<Pipeline> {
      return apiFetch<Pipeline>(`/pipelines/${id}/restart`, { method: 'POST' })
    }

**Step 2** — Create `frontend/src/hooks/useRestartMutation.ts` (mirrors `useApprovalMutation`):

    import { useMutation, useQueryClient } from '@tanstack/react-query'
    import { restartPipeline } from '@/api/client'

    export function useRestartMutation(pipelineId: number) {
      const queryClient = useQueryClient()
      return useMutation({
        mutationFn: () => restartPipeline(pipelineId),
        onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['pipelines'] }),
      })
    }

**Step 3** — Add a `RestartButton` section to `PipelineCard.tsx`, rendered when
`pipeline.status === 'failed'`:

    {pipeline.status === 'failed' && <RestartButton pipelineId={pipeline.id} />}

The `RestartButton` component shows a single button "Restart" that calls `restart.mutate()`.
Display a loading state (`disabled`) while pending and an error message on failure.

## Concrete Steps

All commands run from the repository root `/Users/vwqd2w2/code/iandi/theAgency`.

1. Write the failing test:

        # Edit backend/app/tests/test_pipelines_router.py — add TestRestartPipeline at the end

2. Verify the test fails (RED):

        npx nx run backend:test -- -k TestRestartPipeline

3. Implement the endpoint in `backend/app/routers/pipelines.py`.

4. Verify the test passes (GREEN):

        npx nx run backend:test -- -k TestRestartPipeline

5. Run all backend tests to confirm no regressions:

        npx nx run backend:test

6. Run lint and type-check:

        npx nx run backend:lint
        npx nx run backend:type-check

7. Add frontend changes.

8. Frontend type-check:

        npx nx run frontend:type-check

## Validation and Acceptance

**Backend:**

    npx nx run backend:test

Expected: all existing 208 tests pass + new `TestRestartPipeline` tests pass.

**Manual smoke test (after starting the server):**

    # Create a pipeline
    curl -X POST http://localhost:8000/pipelines \
      -H "Content-Type: application/json" \
      -d '{"pipeline_name": "quick_fix", "title": "test", "prompt": "hello"}'

    # Manually set it to failed (or wait for failure), then:
    curl -X POST http://localhost:8000/pipelines/1/restart

    # Expected response: { "status": "running", ... }

    # 409 on non-failed pipeline:
    curl -X POST http://localhost:8000/pipelines/1/restart
    # Expected: 409 "Pipeline is not failed (status=running)"

**Frontend:** Open `http://localhost:5173`, find a failed pipeline card — a "Restart" button
should be visible. Click it; the card should update to `running`.

## Idempotence and Recovery

The endpoint only accepts `failed` pipelines — calling it twice in a row would return 409 on
the second call because the pipeline is already `running` after the first call. Safe.

## Artifacts and Notes

Pre-existing lint suppressions (do not fix): B008, SIM108 in `pipelines.py`/`health.py`;
UP037 in `agent_registry.py`; F401 in `test_fs_router.py`; SIM117 in
`test_opencode_health_router.py`; I001 in `test_registry_router.py`.

## Interfaces and Dependencies

In `backend/app/routers/pipelines.py`, add:

    @router.post("/{pipeline_id}/restart", response_model=PipelineResponse)
    async def restart_pipeline(
        pipeline_id: int,
        db: Annotated[AsyncSession, Depends(get_db)],
        registry: Annotated[AgentRegistry, Depends(get_registry)],
        client: Annotated[OpenCodeClient, Depends(get_opencode_client)],
        request: Request,
    ) -> PipelineResponse: ...

In `frontend/src/api/client.ts`:

    export function restartPipeline(id: number): Promise<Pipeline>

In `frontend/src/hooks/useRestartMutation.ts`:

    export function useRestartMutation(pipelineId: number): UseMutationResult<Pipeline, Error, void>
