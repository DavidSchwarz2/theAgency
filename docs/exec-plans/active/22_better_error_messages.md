# Surface Pipeline Step Failure Reasons End-to-End (Issue #22)

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

When a pipeline step fails today, the only evidence of *why* it failed lives in the server
logs — it never reaches the database, the REST API, or the browser UI. A user who sees the
red "failed" badge has no actionable information: they cannot tell whether OpenCode crashed,
returned an empty body, timed out, or whether the agent itself reported an error.

After this change, the browser shows a human-readable error message directly under the
failed step badge, e.g. `"OpenCode returned empty body (status 200)"` or `"Step timed out
after 600s"`. That message is persisted in the database, returned by the REST API, and
rendered in the `StepRow` component in `PipelineCard.tsx`.

Five root-cause gaps were identified and are all fixed here:

1. `Step` has no `error_message` column — failure reasons never reach the DB.
2. No audit event is written on hard step failure — nothing queryable.
3. `opencode_client.py` does not wrap all failure modes — `json.JSONDecodeError` (empty 2xx
   body), `httpx.HTTPError`, and `pydantic.ValidationError` escape the `except
   OpenCodeClientError` handler in `run_step` and propagate uncaught.
4. `_launch_pipeline_background_task._run()` has no `except` — any unhandled exception
   leaves the pipeline stuck in `running` forever.
5. The API schema (`StepStatusResponse`) and frontend type (`Step`) do not carry
   `error_message`.

## Progress

- [x] (2026-02-27 10:00Z) ExecPlan written and staged.
- [x] (2026-02-27 10:15Z) Milestone 1: DB column (`Step.error_message`) added; Alembic migration generated and applied; `opencode_client.py` wraps JSONDecodeError, ValidationError, non-list/non-bool shapes; `_persist_failure` stores `error_message` and writes `step_failed` audit event; `_execute_steps` logs `StepExecutionError`; `_launch_pipeline_background_task._run()` catch-all guards pipeline status before overwriting. 230 tests pass.
- [x] (2026-02-27 10:20Z) Milestone 2: `StepStatusResponse.error_message: str | None = None` added; `get_pipeline` passes `error_message=step.error_message` in constructor. Tests still green.
- [x] (2026-02-27 10:25Z) Milestone 3: `Step.error_message: string | null` added to TypeScript interface; `StepRow` renders error under the failed badge. Frontend type-check passes.
- [x] (2026-02-27 10:35Z) Post-implementation review: all MUST FIX and SHOULD FIX findings resolved — fixture DRY refactor, `_parse_list` list shape guard, `_parse_bool` strict boolean check, `_execute_steps` error logging, catch-all status guard, 2 new test cases for `_parse_list` coverage.
- [x] (2026-02-27 10:40Z) ExecPlan finalized: outcomes written, plan moved to completed location per AGENTS.md.

## Surprises & Discoveries

- `_launch_pipeline_background_task._run()` already had a `try/finally` but no `except` —
  unhandled exceptions from `run_fn` (e.g. a raw `JSONDecodeError` that escaped
  `run_step`) propagated to asyncio and left the pipeline stuck in `running`.
- `opencode_client.py`'s `_raise_for_status` only covered HTTP error status codes. The
  methods called `resp.json()` and `Model.model_validate(...)` directly with no wrapping, so
  `json.JSONDecodeError` (empty 2xx body) and `pydantic.ValidationError` both bypassed
  `run_step`'s `except OpenCodeClientError` handler.
- `recover_interrupted_pipelines` (`pipeline_runner.py:506`) already had a broad
  `except Exception` that marks pipelines failed — that path was safe, no change needed.
- `Handoff.metadata_json` stores `None` (not empty string `""`) from `_persist_success`
  when `handoff_schema is None` — the resume_pipeline guard at line 464 is correct and
  needed no fix.
- The `_parse_bool` strict check revealed that existing tests used `text="true"` in respx
  mocks — `true` is valid JSON and parses as Python `True`, so existing delete/abort tests
  continued to pass without modification.
- Code review identified that `_execute_steps` silently swallowed `StepExecutionError`
  without logging it at the pipeline level — fixed by adding a logger.error call before
  `_mark_pipeline_failed`.

## Decision Log

- Decision: Wrap `json.JSONDecodeError`, `httpx.HTTPError`, and `pydantic.ValidationError`
  at the call sites inside each REST method in `opencode_client.py`, not inside
  `_raise_for_status`, so that the wrapping is co-located with the code that can raise.
  Rationale: `_raise_for_status` only has access to the response object; it cannot
  meaningfully wrap parsing errors. Per-call-site wrapping is explicit and testable.
  Date/Author: 2026-02-27 / automated agent.

- Decision: Add `error_message: Mapped[str | None]` to `Step`; use Alembic autogenerate
  for the migration. Rationale: aligns with the project's existing migration pattern
  (`alembic/versions/`). Date/Author: 2026-02-27 / automated agent.

- Decision: Write a `step_failed` audit event in `_persist_failure` with
  `{"error_message": <str>}` in the payload. Rationale: makes failures queryable via the
  audit log without requiring callers to query `Step.error_message`. Date/Author:
  2026-02-27 / automated agent.

- Decision: Add `except Exception` catch-all in `_launch_pipeline_background_task._run()`
  that marks the pipeline `failed` and logs `pipeline_task_unhandled_error`. Rationale:
  this is the only place in the call stack above `run_fn` where we can guarantee the
  pipeline status gets corrected. Date/Author: 2026-02-27 / automated agent.

## Outcomes & Retrospective

All five root-cause gaps identified in the Purpose section were closed:

1. `Step.error_message` column added via Alembic migration — failure reasons now persist in
   the DB.
2. `step_failed` audit event written in `_persist_failure` with `{"error_message": ...}` —
   failures are now queryable via the audit log.
3. `opencode_client.py` wraps `json.JSONDecodeError`, `pydantic.ValidationError`, non-list,
   and non-bool shapes into `OpenCodeClientError` via `_parse`, `_parse_list`, and
   `_parse_bool` helpers — no failure mode can escape as an unhandled exception.
4. `_launch_pipeline_background_task._run()` now has an `except Exception` catch-all that
   marks the pipeline `failed` and logs `pipeline_task_unhandled_error` — pipelines can no
   longer get stuck in `running` forever.
5. `StepStatusResponse.error_message` and the TypeScript `Step.error_message` field expose
   the error to the browser; `StepRow` renders it under the failed badge.

**Metrics:** 230 backend tests pass, 0 lint warnings on modified files, frontend type-check
passes. 7 new test cases covering all new wrapping paths and error persistence.

**What went smoothly:** The hexagonal architecture made the changes surgical — one adapter,
one service, one router, one schema, one frontend component. The TDD discipline (red/green/
refactor) caught the `_parse_list` shape-guard gap before it shipped.

**What was unexpected:** `_raise_for_status` only covered HTTP error status codes — parsing
errors completely bypassed `run_step`'s `except OpenCodeClientError`. The per-call-site
wrapping approach (not inside `_raise_for_status`) proved cleaner and more testable.

**No scope changes:** All work stayed within the original plan. No new issues opened.

## Context and Orientation

The repository is a Python/FastAPI backend + Vite/React/TypeScript frontend monorepo
managed with NX. The backend uses SQLAlchemy 2 async + aiosqlite with Alembic migrations.
The frontend uses React Query for data fetching and Tailwind CSS for styling. The NX task
runner is the only way to run tests, lint, and type-check.

**Key files:**

- `backend/app/models.py` — SQLAlchemy ORM models. `Step` lives here; we add
  `error_message`.
- `backend/app/adapters/opencode_client.py` — HTTP client for OpenCode. All REST methods
  call `self._raise_for_status(resp)` then `resp.json()` / `Model.model_validate(...)`.
  We need to wrap the json/validate calls.
- `backend/app/services/pipeline_runner.py` — Orchestration service. `run_step` catches
  `OpenCodeClientError` and calls `_persist_failure`. We extend `_persist_failure` to
  accept and store an error string. `_execute_steps` loops over steps.
  `_launch_pipeline_background_task._run()` (in `routers/pipelines.py`) launches the
  background coroutine.
- `backend/app/routers/pipelines.py` — FastAPI router. `_launch_pipeline_background_task`
  creates the asyncio background task. `get_pipeline` builds `StepStatusResponse` objects.
- `backend/app/schemas/pipeline.py` — Pydantic schemas. `StepStatusResponse` is the
  per-step response shape.
- `frontend/src/types/api.ts` — TypeScript interface for `Step`.
- `frontend/src/components/PipelineCard.tsx` — Renders `StepRow`; we add error display.
- `alembic/versions/` — Migration files. Run from `backend/` directory.

**Test files:**

- `backend/app/tests/test_pipeline_runner.py` — TDD tests for `PipelineRunner`. All new
  backend behavior must have a failing test written first.
- `backend/app/tests/test_opencode_client.py` — Tests for `OpenCodeClient`. New wrapping
  behavior tested here.

**Running tasks (from repo root):**

    npx nx run backend:test
    npx nx run backend:lint
    npx nx run backend:type-check
    npx nx run frontend:type-check

## Plan of Work

### Milestone 1 — DB column, client robustness, runner fixes (backend)

**Step 1.1 — Add `error_message` to `Step` model.**
In `backend/app/models.py`, add `error_message: Mapped[str | None] = mapped_column(Text,
nullable=True)` after the `finished_at` column in the `Step` class.

**Step 1.2 — Alembic migration.**
From inside `backend/`, run `uv run alembic revision --autogenerate -m "add step
error_message column"`. Inspect the generated file in `alembic/versions/` to confirm it
adds a nullable `error_message` TEXT column to `steps`. Then run `uv run alembic upgrade
head` to apply it. The existing test suite uses an in-memory SQLite DB bootstrapped from
`Base.metadata.create_all`, so tests pick up the column automatically without needing to
run migrations in test mode.

**Step 1.3 — Wrap failure modes in `opencode_client.py`.**
The methods `create_session`, `list_sessions`, `get_session`, `delete_session`,
`send_message`, `send_message_async`, `abort_session`, and `get_todos` each call
`resp.json()` and then `Model.model_validate(...)`. Wrap each call site pattern with a
helper or `try/except` block that re-raises as `OpenCodeClientError`. The cleanest
approach: add a private `_parse` method to `OpenCodeClient` that accepts the response and
a Pydantic model type, and does:

    try:
        data = resp.json()
    except json.JSONDecodeError as exc:
        raise OpenCodeClientError(f"OpenCode returned non-JSON body: {exc}", status_code=resp.status_code) from exc
    try:
        return Model.model_validate(data)
    except pydantic.ValidationError as exc:
        raise OpenCodeClientError(f"OpenCode response schema mismatch: {exc}", status_code=resp.status_code) from exc

And a `_parse_bool` helper for methods that expect `bool` (delete_session, abort_session):

    try:
        return bool(resp.json())
    except json.JSONDecodeError as exc:
        raise OpenCodeClientError(...) from exc

For list methods (`list_sessions`, `get_todos`), wrap the `resp.json()` call then iterate
and parse each item with the same guard.

**Step 1.4 — Extend `_persist_failure` to store `error_message`.**
Change the signature to `async def _persist_failure(self, step: Step, error: str | None =
None) -> None`. Set `step.error_message = error` before committing. Add a `step_failed`
`AuditEvent` with `payload_json=json.dumps({"error_message": error})`.

**Step 1.5 — Thread error strings through `run_step`.**
In `run_step`, the `except TimeoutError` block calls `_persist_failure(step)` — change to
`_persist_failure(step, error=f"Step timed out after {self._step_timeout}s")`. The `except
OpenCodeClientError` block calls `_persist_failure(step)` — change to
`_persist_failure(step, error=str(exc))`.

**Step 1.6 — Add catch-all in `_launch_pipeline_background_task._run()`.**
The `try/finally` in `_run()` (in `routers/pipelines.py:69`) should become a
`try/except/finally`. Add an `except Exception` block before the `finally` that:
- Logs `pipeline_task_unhandled_error` with `pipeline_id` and `exc_info=True`.
- Fetches a fresh pipeline from the DB (or uses `bg_pipeline` if still in scope) and sets
  `status = PipelineStatus.failed`, `updated_at = datetime.now(UTC)`, then commits.

### Milestone 2 — API exposure

Add `error_message: str | None = None` field to `StepStatusResponse` in
`backend/app/schemas/pipeline.py`. The class uses `ConfigDict(from_attributes=True)`, so
the field is automatically populated from `Step.error_message` when the ORM object is
passed in. Update `get_pipeline` in `routers/pipelines.py` to pass `error_message=step.error_message`
in the `StepStatusResponse(...)` constructor call (around line 301–312).

### Milestone 3 — Frontend display

In `frontend/src/types/api.ts`, add `error_message: string | null` to the `Step`
interface. In `frontend/src/components/PipelineCard.tsx`, update `StepRow` to render the
error message when the step status is `'failed'` and `step.error_message` is non-null:

    {step.status === 'failed' && step.error_message && (
      <p className="mt-0.5 ml-2 text-red-400 text-xs font-mono">{step.error_message}</p>
    )}

Place this just after the status badge + agent name row, before the handoff section.

## Concrete Steps

All commands run from the repo root unless noted.

**Milestone 1:**

    # 1. Write failing test first (TDD), then implement.
    # Tests go in backend/app/tests/test_pipeline_runner.py and test_opencode_client.py

    # 2. Create Alembic migration (from backend/ directory):
    cd backend && uv run alembic revision --autogenerate -m "add step error_message column"
    # Inspect generated file, then:
    uv run alembic upgrade head

    # 3. Run tests:
    npx nx run backend:test

    # 4. Run lint + type-check:
    npx nx run backend:lint
    npx nx run backend:type-check

**Milestone 2:**

    npx nx run backend:test
    npx nx run backend:lint
    npx nx run backend:type-check

**Milestone 3:**

    npx nx run frontend:type-check

## Validation and Acceptance

After all milestones are complete:

1. `npx nx run backend:test` — all tests green, including the new tests that fail before
   changes and pass after (TDD).
2. `npx nx run backend:lint` and `npx nx run backend:type-check` — zero errors.
3. `npx nx run frontend:type-check` — zero errors.
4. Manually: start the app, trigger a pipeline where OpenCode returns an empty body (or
   force a timeout); observe that the step shows `status=failed` and `error_message` is
   non-null in `GET /pipelines/{id}` JSON response.
5. Manually: open the browser UI, confirm the error message is displayed under the failed
   step badge.

## Idempotence and Recovery

The Alembic migration adds a nullable column — safe to apply to an existing DB. If the
migration fails partway, run `uv run alembic downgrade -1` from `backend/` to revert.

## Artifacts and Notes

*None yet — will be populated during implementation.*

## Interfaces and Dependencies

At the end of Milestone 1, `_persist_failure` has this signature:

    async def _persist_failure(self, step: Step, error: str | None = None) -> None

At the end of Milestone 2, `StepStatusResponse` includes:

    error_message: str | None = None

At the end of Milestone 3, the `Step` TypeScript interface includes:

    error_message: string | null
