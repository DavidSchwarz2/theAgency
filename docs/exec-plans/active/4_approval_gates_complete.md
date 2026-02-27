# Complete Approval Gates: Comment UI + Timeout/Reminder

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

After this change, users working with pipelines that contain approval gate steps will be able
to (a) type an optional comment when approving or rejecting, which the system injects into
the prompt sent to the next agent step, and (b) configure a reminder timeout on each approval
gate so the system logs a warning after N hours without a decision.

The comment feature closes the loop between human reviewer and the AI agents: a reviewer who
approves can say "focus on performance" and the next agent step will receive that instruction
as context. A reviewer who rejects can explain why, and that too becomes part of the audit trail.

The timeout/reminder feature prevents silent, indefinite waits: if no decision arrives within
a configured number of hours, the system writes an audit event and logs a structured warning
so operators can see stale approvals in their logs. It does not auto-reject — the pipeline
simply keeps waiting.

Acceptance criteria from GitHub issue #4:
- Approve/Reject with optional comment is possible through the UI
- Comment is passed as additional context to the next agent (already works in backend — only
  the UI was missing)
- Timeout configuration is possible (reminder after X hours)

## Progress

- [x] (2026-02-27 09:00Z) ExecPlan written, current state analysed
- [x] (2026-02-27 10:00Z) Milestone 1: Add comment textarea to ApprovalBanner UI (frontend only)
- [x] (2026-02-27 10:30Z) Milestone 2: Add `created_at` to Approval model + Alembic migration
- [x] (2026-02-27 11:30Z) Milestone 3: Add timeout reminder — `remind_after_hours` on PipelineTemplate approval steps + two-phase wait
- [x] (2026-02-27 12:00Z) Run code-quality agent on all modified files, resolved all MUST FIX / SHOULD FIX
- [x] (2026-02-27 12:30Z) Commit + move this plan to completed + close GH issue #4

## Surprises & Discoveries

- The backend already fully supports comments on approve/reject (schema field `comment`,
  injection in `pipeline_runner.py:257–258`). Only the UI was missing.
- `Approval` has no `created_at` column — needed for timeout calculation. Must add it via
  Alembic migration.
- `_execute_approval_step` calls `await event.wait()` with no timeout. Adding a timeout
  reminder means wrapping this in `asyncio.wait_for` or using `asyncio.wait` with a timeout,
  then continuing to wait if only a reminder fires (not an auto-reject).
- `recover_interrupted_pipelines` at startup only handles `running` pipelines — pipelines
  stuck in `waiting_for_approval` are not recovered. This is out of scope for #4 but noted.
- Frontend `api.ts` has no TypeScript type for `ApproveRequest`/`RejectRequest` — the body
  shape is implicit in `client.ts`. Adding explicit types is a SHOULD FIX.

## Decision Log

- Decision: Timeout/reminder = structured log warning + audit event only (no auto-reject,
  no email). Rationale: keeping scope small; the issue says "reminder" not "auto-reject".
  Date: 2026-02-27

- Decision: `remind_after_hours` is an optional field on `PipelineStep` (inside
  `PipelineTemplate.steps`), not a global setting. Rationale: each gate can have its own
  urgency. A pipeline-level default would be acceptable too, but per-step is more expressive
  and consistent with how `model` is already per-step.

- Decision: Reminder fires once and then waits indefinitely (no repeated reminders).
  Rationale: simplest correct implementation; repeated reminders add complexity for marginal
  value.

- Decision: `created_at` added to `Approval` model and populated in `_execute_approval_step`.
  Rationale: needed to compute elapsed time for reminder. `server_default=func.now()` ensures
  no existing rows break.

## Outcomes & Retrospective

All three milestones delivered as planned with 202 backend tests passing (200 pre-existing + 2
new `TestApprovalStepReminder` tests). Frontend type-check clean.

**What worked well:**
- The backend comment-injection was already implemented — Milestone 1 was purely a UI add.
- `asyncio.shield` + `asyncio.wait_for` cleanly handles the one-shot reminder without
  cancelling the underlying event wait.
- Using `server_default=func.now()` for `Approval.created_at` meant no existing rows broke
  and no explicit setter was needed in production code.

**Scope changes:**
- `ApprovalStep` discriminated union (not plain `PipelineStep`) required threading
  `template_steps: list[PipelineStep] | None` through `_execute_steps` with positional index
  lookup rather than passing `remind_after_hours` directly — slightly more indirection than
  the plan described, but keeps the method signature clean.
- `ApprovalActionRequest` type alias added in `api.ts` to unify `ApproveRequest`/`RejectRequest`
  (SHOULD FIX from discoveries, resolved during Milestone 1).

**Deferred:**
- Recovery of pipelines stuck in `waiting_for_approval` at startup — out of scope, noted in
  Surprises & Discoveries.
- Repeated reminders (fire once only by design, see Decision Log).

## Context and Orientation

### Repository structure

The repo is a monorepo managed by NX. Backend is Python/FastAPI in `backend/`, frontend is
Vite/React/TypeScript in `frontend/`. All commands are run from the repo root with
`npx nx run <project>:<target>`.

### How approval gates work today

When a pipeline is created, each step in the template is persisted as a `Step` row in SQLite.
Approval gate steps are identified by `step.agent_name == "__approval__"` (the sentinel
`APPROVAL_SENTINEL` constant in `pipeline_runner.py:22`). When the runner reaches an approval
step, it creates an `Approval` row, sets `pipeline.status = "waiting_for_approval"`, and
suspends via `await asyncio.Event.wait()`. The HTTP handlers at
`POST /pipelines/{id}/approve` and `POST /pipelines/{id}/reject` write the decision to the
`Approval` row, then call `event.set()` to wake the runner. The runner re-reads the approval
from DB, and if approved, appends the comment to the current prompt and continues with the
next step.

### Key files and their responsibilities

`backend/app/models.py` — SQLAlchemy ORM models: `Pipeline`, `Step`, `Approval`,
`AuditEvent`. The `Approval` table currently has `id`, `step_id`, `status`, `comment`,
`decided_by`, `decided_at`. It does NOT have `created_at`.

`backend/app/schemas/pipeline.py` — Pydantic schemas. `ApproveRequest` and `RejectRequest`
extend `ApprovalDecisionRequest(comment: str | None, decided_by: str | None)`. No timeout
fields exist here yet.

`backend/app/services/pipeline_runner.py` — `PipelineRunner` class. The method
`_execute_approval_step` (line 195) handles the pause/resume loop. The comment injection at
lines 257–258 already works. The `await event.wait()` at line 236 has no timeout.

`backend/alembic/versions/` — migration scripts. New migration must add `created_at` to
`approvals` and `remind_after_hours` to... (see Milestone 3 for exact location).

`backend/config/pipelines.yaml` — YAML definitions of pipeline templates. Each template has
a `steps` list. Approval steps look like `{name: "Gate", type: approval}`. The `remind_after_hours`
field will be added here.

`backend/app/schemas/registry.py` — Pydantic models for `PipelineTemplate` and `PipelineStep`.
`PipelineStep` currently has `name`, `agent`, `model`, `type`. Adding `remind_after_hours` here.

`frontend/src/components/PipelineCard.tsx` — `ApprovalBanner` component (lines 86–114).
Currently hardcodes `mutate('')`. Needs a `<textarea>` and state.

`frontend/src/api/client.ts` — `approvePipeline` and `rejectPipeline` functions (lines 50–62).
Already accept a `comment` string. Just needs calling correctly from UI.

`frontend/src/types/api.ts` — TypeScript interfaces. Should gain `ApproveRequest` and
`RejectRequest` types (SHOULD FIX).

### How Alembic migrations work in this project

Migrations live in `backend/alembic/versions/`. To create a new one:

    cd backend && uv run alembic revision --autogenerate -m "describe the change"

Then inspect and clean up the generated file. To apply:

    cd backend && uv run alembic upgrade head

In tests, tables are created from `Base.metadata.create_all` (in-memory SQLite) so tests
automatically see new columns without running migrations.

### Testing conventions

- `asyncio_mode = auto` — all async test functions are auto-awaited
- Fixtures: `db_engine` (in-memory SQLite), `test_client` (HTTP client + session factory)
- Dependencies are overridden via `app.dependency_overrides[get_db] = ...`
- `app.state` is set manually in the `test_client` fixture
- TDD: write failing test first, then implement, then refactor
- Run tests: `npx nx run backend:test`

## Plan of Work

### Milestone 1 — Comment textarea in ApprovalBanner (frontend)

In `PipelineCard.tsx`, the `ApprovalBanner` component currently calls `approve.mutate('')`
and `reject.mutate('')` with hardcoded empty strings. The change is to add local state for
a comment string, render a `<textarea>` above the buttons, and pass the state value to the
mutation.

The textarea should be a small, dark-themed input matching the card's look. It should be
optional (users can still approve/reject with no comment). The label says "Optional comment".

In `frontend/src/types/api.ts`, add the request types:

    interface ApproveRequest { comment?: string }
    interface RejectRequest  { comment?: string }

These are not strictly required by the API calls (which already work), but make the codebase
self-documenting. No backend changes needed for Milestone 1 — the backend already handles
comments correctly.

After this milestone: run `npx nx run frontend:type-check` to confirm no TypeScript errors.

### Milestone 2 — `created_at` column on `Approval` model (backend DB migration)

Add `created_at: Mapped[datetime]` to `Approval` in `models.py`:

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

Generate an Alembic migration:

    cd backend && uv run alembic revision --autogenerate -m "add_created_at_to_approvals"

In `_execute_approval_step`, set `approval.created_at = datetime.now(UTC)` when creating the
`Approval` row (so it's set even in tests without server_default).

No schema changes needed yet. After this milestone: run `npx nx run backend:test` — all 200
tests should still pass.

### Milestone 3 — Timeout reminder: `remind_after_hours` on approval steps

This milestone adds the ability to configure a reminder duration on each approval gate step
in a pipeline template. If configured, the runner logs a warning and writes an audit event
after that many hours have elapsed without a decision.

**Schema change — `PipelineStep`:** In `backend/app/schemas/registry.py`, add field
`remind_after_hours: float | None = None` to `PipelineStep`. This is the only schema change
— the field is part of the template definition, not the request body.

**Runner change — `_execute_approval_step`:** Replace the bare `await event.wait()` with a
two-phase wait:

1. If `remind_after_hours` is set on the step (passed as a parameter), compute a timeout in
   seconds: `timeout = remind_after_hours * 3600`.
2. Use `asyncio.wait_for(asyncio.shield(event.wait()), timeout=timeout)` inside a
   `try/except asyncio.TimeoutError`. On timeout: write an `AuditEvent(event_type="approval_reminder")`
   and log a structured warning. Then call `await event.wait()` again to continue waiting.
3. If `remind_after_hours` is None, use the existing `await event.wait()` directly.

**Why `asyncio.shield`:** Without it, `wait_for` would cancel the internal `event.wait()`
coroutine when the timeout fires. The event itself would be lost. `shield` prevents
cancellation of the inner coroutine, so after the timeout fires we can simply call
`event.wait()` again and it will return immediately if the event was already set, or block
if not.

**Template YAML:** In `backend/config/pipelines.yaml`, approval gate steps can optionally
include `remind_after_hours: 2` (or any float). Existing entries without the field are
unchanged.

**Step model:** The `remind_after_hours` value is carried from the template definition (read
from YAML), not stored in the `steps` DB table. The runner receives it via the template
object (`PipelineTemplate → PipelineStep.remind_after_hours`). No DB migration needed for
this field.

**Signal passage into `_execute_approval_step`:** The method signature needs to accept the
`remind_after_hours` value. The caller `_execute_steps` currently passes the template step
to decide between approval/agent steps — it already has access to the `PipelineStep` object
and can read `.remind_after_hours`.

After this milestone: run `npx nx run backend:test`. Write new TDD tests first:
- test that `approval_reminder` audit event is written when timeout fires
- test that pipeline continues to wait (event still fires and approves correctly) after reminder

## Concrete Steps

### Milestone 1

1. Edit `frontend/src/types/api.ts` — add `ApproveRequest` and `RejectRequest` interfaces.
2. Edit `frontend/src/components/PipelineCard.tsx` — update `ApprovalBanner`:
   - Add `const [comment, setComment] = useState('')`
   - Add `<textarea>` with `value={comment}` and `onChange`
   - Change `approve.mutate('')` to `approve.mutate(comment)`
   - Change `reject.mutate('')` to `reject.mutate(comment)`
3. Run: `npx nx run frontend:type-check`

### Milestone 2

1. Edit `backend/app/models.py` — add `created_at` column to `Approval`.
2. From `backend/` directory:
       uv run alembic revision --autogenerate -m "add_created_at_to_approvals"
   Review and clean the generated file.
3. Edit `backend/app/services/pipeline_runner.py` — set `approval.created_at = datetime.now(UTC)` when creating the row.
4. Run: `npx nx run backend:test`

### Milestone 3

1. Edit `backend/app/schemas/registry.py` — add `remind_after_hours: float | None = None` to `PipelineStep`.
2. Write failing tests in `backend/app/tests/test_pipeline_runner.py` for reminder behaviour.
3. Edit `backend/app/services/pipeline_runner.py`:
   - Update `_execute_approval_step` signature to accept `remind_after_hours: float | None = None`
   - Implement two-phase wait
4. Update `_execute_steps` to pass `step_def.remind_after_hours` when calling `_execute_approval_step`.
   Note: `_execute_steps` currently receives the `Step` ORM objects (not template steps). The template
   step data (`PipelineStep`) needs to be threaded through. The runner already receives the template
   in `run_pipeline` — pass template steps alongside ORM steps.
5. Run: `npx nx run backend:test` — new tests should pass.
6. Run: `npx nx run frontend:type-check`

## Validation and Acceptance

**Milestone 1 acceptance:** Start the dev server (`npx nx run frontend:serve`). Create a
pipeline with an approval gate step. When it reaches the gate, the PipelineCard shows a
yellow "Waiting for approval" banner with a textarea and Approve/Reject buttons. Type a
comment, click Approve, and the pipeline continues. The comment appears in the next agent
step's prompt (visible in its handoff output). Alternatively, confirm via backend tests in
`test_pipeline_runner.py` that the comment is injected.

**Milestone 2 acceptance:** `npx nx run backend:test` passes with 200+ tests. The migration
file exists in `backend/alembic/versions/`. Running `uv run alembic upgrade head` from
`backend/` succeeds.

**Milestone 3 acceptance:** New tests in `test_pipeline_runner.py` verify that when
`remind_after_hours` is set and the timeout fires, an `approval_reminder` audit event is
written and the pipeline is still in `waiting_for_approval` status. After the event fires
(approval arrives), the pipeline continues normally. `npx nx run backend:test` passes.

## Idempotence and Recovery

All steps are additive. Migration adds a nullable-friendly column with a server default.
Tests use in-memory SQLite that is always rebuilt fresh. Re-running tests is always safe.

## Artifacts and Notes

Current `ApprovalBanner` (lines 86–114 of `PipelineCard.tsx`) for reference:

    function ApprovalBanner({ pipelineId }: { pipelineId: number }) {
      const { approve, reject } = useApprovalMutation(pipelineId)
      const isPending = approve.isPending || reject.isPending
      const error = approve.error ?? reject.error
      return (
        <div className="mt-3 p-3 rounded bg-yellow-950 border border-yellow-700">
          <p className="text-yellow-300 text-xs font-semibold mb-2">Waiting for approval</p>
          <div className="flex gap-2">
            <button ... onClick={() => approve.mutate('')}>Approve</button>
            <button ... onClick={() => reject.mutate('')}>Reject</button>
          </div>
          ...
        </div>
      )
    }

Target shape of the two-phase wait in `_execute_approval_step`:

    if remind_after_hours is not None:
        timeout_secs = remind_after_hours * 3600
        try:
            await asyncio.wait_for(asyncio.shield(event.wait()), timeout=timeout_secs)
        except asyncio.TimeoutError:
            # Write reminder audit event, log warning, then continue waiting
            ...
            await event.wait()  # wait indefinitely after reminder
    else:
        await event.wait()

## Interfaces and Dependencies

In `backend/app/schemas/registry.py`, `PipelineStep` must end up with:

    class PipelineStep(BaseModel):
        name: str
        agent: str | None = None
        model: str | None = None
        type: str = "agent"
        remind_after_hours: float | None = None

In `backend/app/services/pipeline_runner.py`, `_execute_approval_step` signature after
Milestone 3:

    async def _execute_approval_step(
        self,
        step: Step,
        pipeline: Pipeline,
        current_prompt: str,
        remind_after_hours: float | None = None,
    ) -> str | None:
