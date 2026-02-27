# Issue #12: Configure Working Directory Per Pipeline Run

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

After this change, a user creating a pipeline can optionally specify a working directory
(e.g. `/home/user/myproject`). Every agent step in that pipeline will receive an instruction
telling it to treat that path as its working directory. Without this, agents operate from
whatever directory OpenCode was started in — usually fine for the default case, but wrong when
the codebase to work on lives somewhere else.

A user can see this working: create a pipeline with `working_dir` set to a local project path,
and the first agent step's prompt will contain a preamble like
`Working directory: /home/user/myproject — all file operations must use this path.`

If `working_dir` is omitted, no preamble is added and nothing changes for existing pipelines.

## Progress

- [x] (2026-02-27 10:30Z) Research: OpenCode `/session` API accepts only `{ parentID?, title? }` — no `cwd` field. Working dir will be injected as a system preamble in `send_message`.
- [x] (2026-02-27 10:35Z) ExecPlan written.
- [x] (2026-02-27 10:50Z) M1: Added `working_dir` to `Pipeline` ORM model, `PipelineCreateRequest`, `PipelineResponse` (+ `branch` for symmetry). Generated and applied Alembic migration `0f13e9f2a28d`. All 3 router tests green. Full suite: 144 passed.
- [x] (2026-02-27 11:05Z) M2: Added `working_dir` param to `run_step`, extracted `_build_prompt` helper, wired `working_dir=pipeline.working_dir` in `_execute_steps`. Fixed detached-session bug in `recover_interrupted_pipelines`. All 6 working_dir tests green.
- [x] (2026-02-27 11:15Z) M3: Added `working_dir?: string` to `PipelineCreateRequest` frontend interface, `working_dir: string | null` (+ `branch`) to `Pipeline` interface, added controlled input field to `NewPipelineModal`. Type-check clean.
- [x] (2026-02-27 11:20Z) Post-implementation review: all MUST FIX and SHOULD FIX resolved. Lint clean, 144 tests pass, type-check clean.
- [ ] ExecPlan finalized: outcomes written, plan moved to `docs/exec-plans/completed/`.

## Surprises & Discoveries

- The OpenCode HTTP server's `POST /session` body only accepts `{ parentID?, title? }`. There
  is no `cwd`, `path`, or working-directory field at the session level. The `POST /session/:id/message`
  body accepts a `system` field, but that would require changing `OpenCodeClient.send_message`
  to accept an optional `system` kwarg. The simpler and equally effective approach is to prepend
  the working directory as a plain-text preamble in the prompt body, which requires no API
  signature changes beyond what already exists.

- The `PipelineResponse` schema was missing `branch`, which has lived on the ORM since early
  milestones. The addition of `working_dir` exposed this asymmetry; both fields were added to
  the response schema simultaneously.

- The `recover_interrupted_pipelines` function passed a detached `Pipeline` ORM object to
  `resume_pipeline` — the object was fetched in one session that had already closed. Accessing
  scalar attributes from a detached instance can raise `DetachedInstanceError` in SQLAlchemy.
  Fixed by re-fetching the pipeline inside the new session, matching the pattern already used
  in `_run_in_background` in the router.

## Decision Log

- Decision: Inject working directory as a text preamble prepended to the prompt in `run_step`,
  rather than via a dedicated `system` field in `send_message` or at session-creation time.
  Rationale: The OpenCode session API has no `cwd` field. Using the `system` field in
  `send_message` would work but requires an extra kwarg that isn't needed yet. Plain-text
  preamble is the lowest-complexity approach and is equally effective for guiding an agent.
  Date/Author: 2026-02-27 / agent

## Outcomes & Retrospective

All three milestones delivered and verified. Users can now set an optional `working_dir` on any
pipeline create request. The value is persisted on the `Pipeline` row, returned in all pipeline
responses, and prepended as a clear working-directory instruction to every agent step prompt.
Omitting the field produces identical behaviour to before — no regression.

Two bonus fixes were included: `PipelineResponse` now exposes `branch` (previously missing
despite being stored), and the crash-recovery path no longer passes detached ORM objects across
session boundaries.

Final state: 144 backend tests passing, frontend type-check clean, ruff lint clean.

## Context and Orientation

This is a Python/FastAPI + React/TypeScript monorepo managed with NX. The backend lives in
`backend/` and the frontend in `frontend/`.

**ORM layer** (`backend/app/models.py`): SQLAlchemy 2.x async models. `Pipeline` is the
top-level model that holds all pipeline metadata. Currently its columns are: `id`, `title`,
`template`, `branch`, `status`, `created_at`, `updated_at`, `prompt`. We will add
`working_dir: str | None`.

**Alembic** (`backend/alembic/`): database migration tool. Migrations live in
`backend/alembic/versions/`. The last migration is `f9486768fea8_add_model_to_steps.py`.
All `alembic` commands must be run from inside `backend/` with `uv run alembic ...`.

**Schemas** (`backend/app/schemas/pipeline.py`): Pydantic models used for request/response
validation. `PipelineCreateRequest` describes what a caller sends when creating a pipeline;
`PipelineResponse` and `PipelineDetailResponse` describe what is returned. Both need a
`working_dir: str | None = None` field.

**Router** (`backend/app/routers/pipelines.py`): FastAPI router. The `create_pipeline`
endpoint constructs a `Pipeline` ORM object from `PipelineCreateRequest`. It must also pass
`working_dir=body.working_dir` when constructing the ORM object.

**PipelineRunner** (`backend/app/services/pipeline_runner.py`): Orchestrates step execution.
`run_step(step, agent_profile, prompt, model)` creates an OpenCode session, builds the full
prompt (optionally prepending `agent_profile.system_prompt_additions`), and calls
`self._client.send_message(session_id, prompt=full_prompt, agent=..., model=...)`. We will
add a `working_dir: str | None = None` parameter to `run_step`. When `working_dir` is set,
the preamble `Working directory: <path> — treat this as the project root for all file
operations.\n\n` is prepended to `full_prompt` (before the existing `system_prompt_additions`
prepend, so the working-dir preamble comes first).

`_execute_steps(steps, initial_prompt, pipeline)` calls `run_step` for each agent step. It
needs access to `pipeline.working_dir` to forward it. Since `pipeline` is already a parameter,
we pass `working_dir=pipeline.working_dir` in the `run_step` call.

`run_pipeline` and `resume_pipeline` both call `_execute_steps` and already receive `pipeline`,
so no signature change is needed there.

**Frontend** (`frontend/src/`): React + TypeScript. The new pipeline form lives in
`frontend/src/components/NewPipelineModal.tsx`. The API types are defined in
`frontend/src/types/api.ts`. We add `working_dir?: string` to both the `PipelineCreateRequest`
interface and the `Pipeline` interface.

## Plan of Work

### Milestone 1 — Schema, ORM, Migration

Add `working_dir: Mapped[str | None] = mapped_column(String(500), nullable=True)` to the
`Pipeline` class in `backend/app/models.py`, between the `branch` column and the `status`
column (for readability — order does not affect function).

In `backend/app/schemas/pipeline.py`, add `working_dir: str | None = None` to:
- `PipelineCreateRequest` (incoming request body)
- `PipelineResponse` (returned on create/list/abort/approve/reject)

`PipelineDetailResponse` inherits from `PipelineResponse` so it gets the field for free.

In `backend/app/routers/pipelines.py`, pass `working_dir=body.working_dir` when constructing
the `Pipeline` ORM object in `create_pipeline`. Also add `working_dir` to the explicit
`PipelineDetailResponse(...)` construction at the bottom of `get_pipeline` and to the
`PipelineResponse.model_validate(pipeline)` calls — but since those use `model_validate` with
`from_attributes=True`, they pick up new ORM fields automatically; no change needed there.
The explicit `PipelineDetailResponse(...)` constructor call in `get_pipeline` does enumerate
fields, so add `working_dir=pipeline.working_dir` there.

Generate and apply the Alembic migration:

    cd backend
    uv run alembic revision --autogenerate -m "add working_dir to pipeline"
    uv run alembic upgrade head

Review the generated migration file to confirm it adds a nullable `VARCHAR(500)` column
named `working_dir` to the `pipelines` table.

Write tests first (TDD). New tests in `backend/app/tests/test_pipelines_router.py`:
- `test_create_pipeline_with_working_dir` — POST with `working_dir="/tmp/test"`, assert the
  response includes `working_dir="/tmp/test"`.
- `test_create_pipeline_without_working_dir` — POST without `working_dir`, assert
  `working_dir` is `None` in the response.

### Milestone 2 — PipelineRunner Wiring

Modify `run_step` in `backend/app/services/pipeline_runner.py` to accept
`working_dir: str | None = None`. When set, build the prompt as:

    preamble = f"Working directory: {working_dir} — treat this as the project root for all file operations.\n\n"
    full_prompt = preamble + (f"{agent_profile.system_prompt_additions}\n\n{prompt}" if agent_profile.system_prompt_additions else prompt)

When not set, keep existing behaviour unchanged.

Modify `_execute_steps` to forward `working_dir=pipeline.working_dir` in the `run_step` call.
`pipeline` is already available as a parameter, so no further signature changes are needed.

Write tests first (TDD). New tests in `backend/app/tests/test_pipeline_runner.py`:
- `test_run_step_with_working_dir` — assert the `send_message` mock receives a prompt that
  starts with `Working directory: /some/path`.
- `test_run_step_without_working_dir` — assert the prompt does NOT contain the preamble (no
  regression).
- `test_execute_steps_forwards_working_dir` — use a pipeline with `working_dir` set and assert
  `send_message` gets the preamble.

### Milestone 3 — Frontend

In `frontend/src/types/api.ts`, add `working_dir?: string` to the `PipelineCreateRequest`
interface and add `working_dir: string | null` to the `Pipeline` interface.

In `frontend/src/components/NewPipelineModal.tsx`, add a controlled text input for
`working_dir`. It should be optional — an empty string should be sent as `undefined` (omitted)
so that the backend receives `null`. The label should read "Working Directory (optional)" with
a placeholder of `/path/to/project`.

Wire the field into the existing form state (the pattern used for `branch` or other optional
fields), and include it in the `mutate(...)` call to the pipeline creation API.

## Concrete Steps

### M1 Steps

    # 1. Edit backend/app/models.py — add working_dir to Pipeline
    # 2. Edit backend/app/schemas/pipeline.py — add working_dir to PipelineCreateRequest and PipelineResponse
    # 3. Edit backend/app/routers/pipelines.py — pass working_dir when constructing Pipeline ORM + PipelineDetailResponse
    # 4. Generate migration:
    cd backend
    uv run alembic revision --autogenerate -m "add working_dir to pipeline"
    uv run alembic upgrade head
    # 5. Write failing tests, run them, fix, green.
    npx nx run backend:test -- -k "working_dir"

### M2 Steps

    # 1. Edit backend/app/services/pipeline_runner.py — add working_dir param to run_step, wire in _execute_steps
    # 2. Write failing tests, run them, fix, green.
    npx nx run backend:test -- -k "working_dir"
    # 3. Run full backend test suite.
    npx nx run backend:test

### M3 Steps

    # 1. Edit frontend/src/types/api.ts
    # 2. Edit frontend/src/components/NewPipelineModal.tsx
    # 3. Type-check:
    npx nx run frontend:type-check

## Validation and Acceptance

After all milestones:

1. Run full backend tests — all pass:

       npx nx run backend:test

2. Run frontend type-check — no errors:

       npx nx run frontend:type-check

3. Manual smoke test (requires a running backend and OpenCode server):
   - POST `http://localhost:8000/pipelines` with body:
     `{ "template": "...", "title": "WD test", "prompt": "hello", "working_dir": "/tmp/smoke" }`
   - GET the created pipeline and confirm `working_dir` is `/tmp/smoke`.
   - Observe that agent steps receive a prompt starting with
     `Working directory: /tmp/smoke`.

4. Regression: POST without `working_dir` — confirm `working_dir` is `null` in the response
   and no preamble appears in the prompt.

## Idempotence and Recovery

The Alembic migration adds a nullable column — it is safe to re-run `alembic upgrade head`
multiple times (it will be a no-op after the first run). If the migration must be rolled back,
run `uv run alembic downgrade -1` from `backend/`.

All other changes are additive (new optional fields, new optional parameter). No existing
functionality is removed or altered for calls that omit `working_dir`.

## Artifacts and Notes

OpenCode `/session` API body (confirmed from live docs):

    POST /session
    body: { parentID?: string, title?: string }

There is no `cwd`, `path`, or working-directory field. Working directory must be communicated
to the agent via the prompt text.

## Interfaces and Dependencies

In `backend/app/models.py`, `Pipeline` gains:

    working_dir: Mapped[str | None] = mapped_column(String(500), nullable=True)

In `backend/app/schemas/pipeline.py`:

    class PipelineCreateRequest(BaseModel):
        ...
        working_dir: str | None = None

    class PipelineResponse(BaseModel):
        ...
        working_dir: str | None = None

In `backend/app/services/pipeline_runner.py`, `run_step` gains:

    async def run_step(
        self,
        step: Step,
        agent_profile: AgentProfile,
        prompt: str,
        model: str | None = None,
        working_dir: str | None = None,
    ) -> tuple[str, HandoffSchema | None]:

In `frontend/src/types/api.ts`:

    interface PipelineCreateRequest {
      ...
      working_dir?: string
    }

    interface Pipeline {
      ...
      working_dir: string | null
    }
