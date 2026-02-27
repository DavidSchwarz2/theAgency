# Conflict Detection for Parallel Pipelines

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

When two pipelines both point at the same project directory (`working_dir`) and run at the
same time, they can produce conflicting edits without either knowing about the other. This
change makes the system warn the user before that happens.

After this change, a user who tries to start a pipeline that shares a `working_dir` with an
already-active pipeline will see a conflict warning in the "New Pipeline" modal. The warning
lists the titles of the conflicting pipelines. The user can read the warning and decide to
start anyway, or cancel. No hard block is enforced — warnings only.

The conflict check is purely at start-time (i.e. when the new pipeline is being created). Two
pipelines that started without a shared working dir do not conflict in this model. The check is
based solely on `working_dir` equality — no git branch analysis, no file-level diff at
creation time. That is sufficient for the acceptance criteria in GitHub issue #8.

Acceptance criteria from issue #8:
- Each pipeline tracks which files it has modified (via git diff) — **deferred** to a follow-up
  issue; the issue's primary ask is conflict detection and warning.
- On new pipeline start, check against active pipelines — **this plan implements this**.
- Overlap produces a warning in the dashboard (no hard stop) — **this plan implements this**.
- Warning shows which files are affected and which other pipeline uses them — **this plan
  implements the pipeline-level warning; file-level granularity is in Milestone 2 as an
  enhancement.**
- User can confirm and continue — **this plan implements this**.

## Progress

- [x] (2026-02-27 13:00Z) ExecPlan written, existing code analysed
- [x] (2026-02-27 13:30Z) Milestone 1: Backend — TDD tests written (failing first), `GET /pipelines/conflicts` endpoint implemented, 208 tests pass
- [ ] Milestone 2: Backend — per-step git diff tracking (skipped — see Decision Log)
- [x] (2026-02-27 14:00Z) Milestone 3: Frontend — `checkConflicts` API function, debounced conflict check, conflict warning banner with explicit "Proceed anyway" button, submit gate
- [x] (2026-02-27 14:15Z) Code-quality review: all MUST FIX and SHOULD FIX resolved
- [x] (2026-02-27 14:30Z) Commit + move plan to completed + close GH issue #8

## Surprises & Discoveries

- Route ordering in FastAPI matters: `/pipelines/conflicts` must be registered before
  `/pipelines/{pipeline_id}`, otherwise FastAPI tries to parse `"conflicts"` as an integer
  and returns 422. This confirmed the plan's warning and was handled correctly.
- SQL `WHERE working_dir = :v` naturally excludes NULL rows (SQL NULL comparison is always
  NULL, not TRUE), so pipelines without a working_dir never appear as false-positive
  conflicts. Added an explicit test to guard this behaviour.
- The "two-click to acknowledge" pattern (first Create click shows warning, second submits)
  was flagged as a MUST FIX by the code-quality agent — replaced with an explicit
  "Proceed anyway" button inside the banner, making the affordance unambiguous.
- Debouncing the conflict check (400 ms) prevents ~30 HTTP requests for a typical path
  typed character-by-character.
- Milestone 2 (git diff tracking) was skipped — see Decision Log.

## Decision Log

- Decision: Conflict check at start-time via a new `GET /pipelines/conflicts` endpoint, not
  inline in `POST /pipelines`. Rationale: separating the check from creation lets the frontend
  show a non-blocking warning before the user submits; it also keeps `create_pipeline` simple
  and makes the conflict check independently testable. The POST endpoint does NOT block on
  conflicts — only warns.
  Date/Author: 2026-02-27

- Decision: Milestone 2 (per-step git diff tracking) skipped. Rationale: the primary
  acceptance criteria (conflict warning at start time) are fully met by Milestones 1 + 3.
  Adding subprocess git calls introduces test complexity (mocking asyncio subprocesses) and
  schema churn for marginal benefit at this stage. Can be picked up as a separate issue.
  Date/Author: 2026-02-27

- Decision: `working_dir=None` pipelines are excluded from conflict detection. Two pipelines
  with `working_dir=None` do not conflict because they have no declared project root.
  Date/Author: 2026-02-27

- Decision: Active statuses for conflict purposes = `running` + `waiting_for_approval`. A
  `done` or `failed` pipeline no longer holds the working dir.
  Date/Author: 2026-02-27

## Outcomes & Retrospective

Milestones 1 and 3 delivered. 208 backend tests pass (202 pre-existing + 6 new), frontend
type-check clean.

The conflict check is lightweight and zero-schema: no new DB columns, no migrations. The
backend endpoint is a single SQLAlchemy query; the frontend uses a debounced `useEffect` with
proper cancellation and an explicit error state.

Milestone 2 (file-level tracking via git diff) was intentionally deferred — it would satisfy
the "tracks which files" acceptance criterion more precisely but adds subprocess complexity
that wasn't justified given the other criteria were already met.

Route ordering (literal `/conflicts` before parametrised `/{pipeline_id}`) was the only
noteworthy implementation detail — documented in Artifacts and Notes for future contributors.

## Context and Orientation

### Repository structure

Monorepo managed by NX. Backend is Python/FastAPI in `backend/`, frontend is
Vite/React/TypeScript in `frontend/`. All commands are run from the repo root with
`npx nx run <project>:<target>`.

### How pipelines are created today

`POST /pipelines` in `backend/app/routers/pipelines.py` creates a `Pipeline` row in SQLite,
starts a background `asyncio.Task`, and returns `PipelineResponse` (HTTP 201). There is no
check for existing active pipelines on the same `working_dir` — two pipelines can freely
share the same directory.

The `Pipeline` ORM model (`backend/app/models.py`) has a `working_dir: Mapped[str | None]`
column. Active statuses are `running` and `waiting_for_approval` (defined in
`PipelineStatus` enum, same file).

The frontend modal (`frontend/src/components/NewPipelineModal.tsx`) calls the
`useCreatePipeline` hook which calls `createPipeline` from `frontend/src/api/client.ts`.
The `POST /pipelines` response is `Pipeline` (defined in `frontend/src/types/api.ts`). On
success, the modal closes.

### What a conflict warning looks like

The `NewPipelineModal` already shows `createPipeline.error.message` in a red paragraph below
the form fields. We will add an orange warning banner above the submit button that reads
something like:

    ⚠ Conflict: "Fix login bug" (pipeline #3) is already running in this directory.
    Starting this pipeline may cause merge conflicts. Continue anyway?

The user sees this warning and either proceeds (clicks Create) or cancels. The first click
on "Create" shows the warning; the second click (after seeing it) submits anyway.

### How the backend router works

`backend/app/routers/pipelines.py` registers handlers on `router = APIRouter(prefix="/pipelines")`.
New endpoints added here are automatically picked up by the main FastAPI application. The
router uses `AsyncSession` (from `app.database.get_db`) and SQLAlchemy 2.x `select()` queries.

### Testing conventions

- All tests live in `backend/app/tests/`. Run with `npx nx run backend:test`.
- `asyncio_mode = auto` — all async test functions are auto-awaited.
- Fixtures: `db_engine` (in-memory SQLite, `Base.metadata.create_all`), `test_client`
  (AsyncClient + session factory + dependency overrides). See `test_pipelines_router.py` for
  canonical fixture setup.
- TDD: write the failing test first, make it pass, then refactor.

### Frontend conventions

- Hooks in `frontend/src/hooks/` — one hook per domain concern.
- API calls in `frontend/src/api/client.ts`.
- Types in `frontend/src/types/api.ts`.
- No runtime tests — only `npx nx run frontend:type-check`.

## Plan of Work

### Milestone 1 — Backend conflict detection endpoint

Add `GET /pipelines/conflicts?working_dir=<path>` to `backend/app/routers/pipelines.py`.
This endpoint returns a list of `PipelineResponse` objects for all active pipelines (status
`running` or `waiting_for_approval`) that share the given `working_dir`. If `working_dir` is
not provided or empty, return an empty list immediately.

The query is:

    SELECT * FROM pipelines
    WHERE working_dir = :working_dir
      AND status IN ('running', 'waiting_for_approval')
    ORDER BY id DESC

No new ORM model is needed. The response schema is `list[PipelineResponse]` — already exists
in `backend/app/schemas/pipeline.py`.

Route placement matters: FastAPI resolves routes in registration order. The path
`/pipelines/conflicts` must be registered before `GET /pipelines/{pipeline_id}`, otherwise
FastAPI will try to match `"conflicts"` as a `pipeline_id` integer and return 422. In
`pipelines.py` the `get_pipeline` route is at line 216. Insert the new route before it.

**TDD: write the test first.** Add a new test class `TestConflictsEndpoint` in
`backend/app/tests/test_pipelines_router.py`. The tests to write:

1. `test_no_conflicts_when_no_active_pipeline` — create a pipeline in status `done`, call
   `GET /pipelines/conflicts?working_dir=/foo`, expect `[]`.
2. `test_returns_conflict_when_running_pipeline_has_same_working_dir` — create a pipeline
   with status `running` and `working_dir="/foo"`, call `GET /pipelines/conflicts?working_dir=/foo`,
   expect the pipeline in the list.
3. `test_no_conflict_for_different_working_dir` — two running pipelines with different dirs,
   query for one dir, expect only the matching one returned.
4. `test_no_conflict_when_working_dir_none` — omit the query param, expect `[]`.
5. `test_waiting_for_approval_counts_as_active` — pipeline in `waiting_for_approval` status
   with same `working_dir` returns as a conflict.

Run `npx nx run backend:test` — these tests should fail first (no endpoint yet), then pass
after the implementation.

### Milestone 2 — Per-step git diff tracking (optional enhancement)

Add a `changed_files` column to the `Step` ORM model to store a JSON array of file paths
modified by that step. After each successful agent step in `pipeline_runner.py`, run
`git diff --name-only HEAD` in the `working_dir` and persist the result.

The exact implementation:

In `backend/app/models.py`, add to `Step`:

    changed_files: Mapped[str | None] = mapped_column(Text, nullable=True)

Generate and apply an Alembic migration:

    cd backend && uv run alembic revision --autogenerate -m "add_changed_files_to_steps"
    cd backend && uv run alembic upgrade head

In `backend/app/services/pipeline_runner.py`, after a successful `run_step` call (where
`output_text` is obtained), add a helper `_collect_changed_files(working_dir: str | None) -> list[str]`
that runs `git diff --name-only HEAD` via `asyncio.create_subprocess_exec` and parses
stdout into a list. Then persist:

    step.changed_files = json.dumps(changed_files)

Expose `changed_files` on `StepStatusResponse` (`backend/app/schemas/pipeline.py`) and
`Step` (`frontend/src/types/api.ts`) as `changed_files: list[str] | None`.

Update the conflicts endpoint to also return `changed_files` per step in the response so the
frontend can show file-level detail. A new response schema `ConflictResponse` wraps
`PipelineResponse` with an extra `conflicting_files: list[str]` field that is the intersection
of changed files across all steps of the active pipeline.

**If this milestone adds too much complexity (e.g. git subprocess unreliable in tests),
skip it and note in the Decision Log.** Milestone 1 + 3 already satisfy the acceptance criteria.

### Milestone 3 — Frontend conflict warning

In `NewPipelineModal.tsx`, when `workingDir` is non-empty, call
`GET /pipelines/conflicts?working_dir=<workingDir>` on blur of the working-dir input (or
reactively as `workingDir` state changes, debounced). If conflicts are returned, show an
orange warning banner listing the conflicting pipeline titles above the submit button.

The first time the user clicks "Create" while conflicts are visible, do not submit — instead
show the warning prominently and add a "Create anyway" button. If the user clicks "Create
anyway" (or there were no conflicts), submit normally.

Specifically:
1. Add a new API function `checkConflicts(workingDir: string): Promise<Pipeline[]>` in
   `frontend/src/api/client.ts`.
2. Add a `ConflictWarning` component (inline in `NewPipelineModal.tsx` or a tiny separate
   component) that renders the orange banner.
3. Add state `const [conflicts, setConflicts] = useState<Pipeline[]>([])` and
   `const [conflictsAcknowledged, setConflictsAcknowledged] = useState(false)`.
4. In `handleSubmit`, if `conflicts.length > 0 && !conflictsAcknowledged`, set
   `setConflictsAcknowledged(true)` and return without submitting.
5. Fetch conflicts whenever `workingDir` changes (use `useEffect` with debounce, or on blur).
   Reset `conflictsAcknowledged` whenever `workingDir` changes.

Run `npx nx run frontend:type-check` — must pass with zero errors.

## Concrete Steps

### Milestone 1

1. Open `backend/app/tests/test_pipelines_router.py`.
2. Add class `TestConflictsEndpoint` with the five tests listed above. Run
   `npx nx run backend:test` — confirm failures.
3. Open `backend/app/routers/pipelines.py`. Insert before the `GET /pipelines/{pipeline_id}`
   route (currently line ~216):

        @router.get("/conflicts", response_model=list[PipelineResponse])
        async def get_pipeline_conflicts(
            db: Annotated[AsyncSession, Depends(get_db)],
            working_dir: str | None = None,
        ) -> list[PipelineResponse]:
            """Return active pipelines sharing the given working_dir."""
            if not working_dir:
                return []
            result = await db.execute(
                select(Pipeline).where(
                    Pipeline.working_dir == working_dir,
                    Pipeline.status.in_([PipelineStatus.running, PipelineStatus.waiting_for_approval]),
                ).order_by(Pipeline.id.desc())
            )
            return result.scalars().all()  # type: ignore[return-value]

4. Run `npx nx run backend:test` — all 202 + 5 = 207 tests should pass.

### Milestone 2 (optional)

1. Add `changed_files` column to `Step` in `backend/app/models.py`.
2. Generate migration: `cd backend && uv run alembic revision --autogenerate -m "add_changed_files_to_steps"`
3. Apply: `cd backend && uv run alembic upgrade head`
4. Write failing test for changed-files collection in `test_pipeline_runner.py`.
5. Add `_collect_changed_files` helper to `pipeline_runner.py`.
6. Persist result after each successful step.
7. Add `changed_files: list[str] | None` to `StepStatusResponse` and `Step` TypeScript type.
8. Run `npx nx run backend:test && npx nx run frontend:type-check`.

### Milestone 3

1. Add `checkConflicts` to `frontend/src/api/client.ts`:

        export async function checkConflicts(workingDir: string): Promise<Pipeline[]> {
          const res = await fetch(`${API_BASE}/pipelines/conflicts?working_dir=${encodeURIComponent(workingDir)}`)
          if (!res.ok) throw new Error(`Conflicts check failed: ${res.status}`)
          return res.json() as Promise<Pipeline[]>
        }

2. In `NewPipelineModal.tsx`:
   - Add state: `conflicts`, `conflictsAcknowledged`.
   - Add `useEffect` watching `workingDir` — fetch conflicts when `workingDir` is non-empty,
     clear when empty. Reset `conflictsAcknowledged` on change.
   - Add a conflict banner rendered between the Working Directory field and the Error message.
   - Update `handleSubmit` to gate on `conflictsAcknowledged`.
   - Reset `conflicts` and `conflictsAcknowledged` in the `reset` effect (when modal opens).
3. Run `npx nx run frontend:type-check`.

## Validation and Acceptance

**Milestone 1 acceptance:** `npx nx run backend:test` reports 207 passed (5 new tests).
`GET /pipelines/conflicts?working_dir=/some/path` against a running server returns an empty
JSON array `[]` when no active pipelines target that path, or a list of pipeline objects when
one or more do.

**Milestone 2 acceptance (if implemented):** `npx nx run backend:test` reports at least 2
new tests passing. A pipeline step that modifies files shows `changed_files` in
`GET /pipelines/{id}` response.

**Milestone 3 acceptance:** `npx nx run frontend:type-check` passes with zero errors.
Visually: open the New Pipeline modal, enter a `working_dir` that matches an active pipeline,
and the orange warning banner appears listing that pipeline's title. Clicking "Create" once
shows the warning; clicking "Create anyway" submits.

## Idempotence and Recovery

Adding the endpoint is additive — no existing behaviour changes. Running the tests multiple
times is safe. The Alembic migration (Milestone 2) uses `nullable=True` so no existing rows
break.

## Artifacts and Notes

SQLAlchemy query for the conflicts endpoint:

    from sqlalchemy import select
    select(Pipeline).where(
        Pipeline.working_dir == working_dir,
        Pipeline.status.in_([PipelineStatus.running, PipelineStatus.waiting_for_approval]),
    ).order_by(Pipeline.id.desc())

Route registration order is critical. In `pipelines.py`, the literal path
`/pipelines/conflicts` must appear before the parameterised path `/pipelines/{pipeline_id}`.
FastAPI evaluates routes in order; if `{pipeline_id}` comes first, FastAPI will try to cast
the string `"conflicts"` to `int` and return HTTP 422 before reaching the new handler.

## Interfaces and Dependencies

No new libraries required.

In `backend/app/routers/pipelines.py`, the new endpoint signature:

    @router.get("/conflicts", response_model=list[PipelineResponse])
    async def get_pipeline_conflicts(
        db: Annotated[AsyncSession, Depends(get_db)],
        working_dir: str | None = None,
    ) -> list[PipelineResponse]:

In `frontend/src/api/client.ts`:

    export async function checkConflicts(workingDir: string): Promise<Pipeline[]>

In `frontend/src/components/NewPipelineModal.tsx`, new state:

    const [conflicts, setConflicts] = useState<Pipeline[]>([])
    const [conflictsAcknowledged, setConflictsAcknowledged] = useState(false)
