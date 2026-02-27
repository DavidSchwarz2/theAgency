# Approval Gates — Issue #4

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

After this change an operator can define an "approval" step inside a pipeline template.
When the pipeline engine reaches that step it pauses execution, records an `Approval`
row in the database, and sets the pipeline status to `waiting_for_approval`. A human
(or automated caller) then calls `POST /pipelines/{id}/approve` or
`POST /pipelines/{id}/reject`. On approval the pipeline resumes from the next agent
step, forwarding an optional comment as extra context. On rejection the pipeline is
permanently marked failed.

The net effect: pipelines can require a human checkpoint before continuing, enabling
oversight of long-running or high-stakes AI work.

## Progress

- [x] (2026-02-27 10:00Z) ExecPlan written.
- [x] (2026-02-27 10:30Z) Milestone 1: registry schema extended to support `type: approval` steps — tests pass.
- [x] (2026-02-27 11:00Z) Milestone 2: PipelineRunner detects approval steps, pauses pipeline, writes Approval record — tests pass.
- [x] (2026-02-27 11:30Z) Milestone 3: `POST /approve` and `POST /reject` resume/fail the pipeline — tests pass.
- [x] (2026-02-27 12:00Z) Milestone 4: `GET /approvals` lists pending approvals — tests pass (4 tests).
- [x] (2026-02-27 14:00Z) Post-implementation code-quality review — all MUST FIX / SHOULD FIX resolved.
  - MUST FIX #1: `pipeline_tasks` changed from `set` to `dict[int, asyncio.Task]` so abort only cancels the target pipeline's task.
  - MUST FIX #2: Extracted `_handle_approval_decision` helper in `routers/pipelines.py` — approve/reject endpoints now ~5 lines each.
  - MUST FIX #3: `_execute_approval_step` now uses explicit `elif approved / elif rejected / else` branches; unexpected status logs an error.
  - MUST FIX #4: Duplicated `_make_waiting_pipeline` extracted to module-level async helper shared by `TestApprovePipeline` and `TestRejectPipeline`.
  - SHOULD FIX #5: `all` query param renamed to `include_all` to avoid shadowing built-in; test updated.
  - SHOULD FIX #6: `_mark_pipeline_failed(pipeline, step)` helper extracted in `pipeline_runner.py`; three call sites simplified.
  - SHOULD FIX #7: Blocking `subprocess.run` in `main.py` lifespan replaced with `asyncio.create_subprocess_exec`.
- [x] (2026-02-27 14:05Z) 109 tests passing, `ruff check` clean.
- [x] (2026-02-27 14:10Z) Commit (code + ExecPlan together).
- [ ] ExecPlan moved to completed/, issue closed.

## Surprises & Discoveries

- Observation: Two separate SQLAlchemy sessions are required for approval tests. The background runner holds one session awaiting the event; the approve/reject HTTP handler uses a completely separate session. Using a shared session causes `MissingGreenlet` errors.
  Evidence: Test failures during milestone 2 until the test was restructured with two distinct session factories.

- Observation: `PipelineStep` must remain a type alias (Annotated Union), not a concrete class. Tests that construct steps must use `AgentStep(agent=...)` or `ApprovalStep(type="approval", ...)` directly.
  Evidence: LSP errors when test code tried to instantiate `PipelineStep(...)` directly.

- Observation: The backwards-compatibility validator on `PipelineTemplate` injects `type: "agent"` for YAML steps that omit the `type` field, so existing YAML files need no migration.
  Evidence: All existing pipeline YAML fixture tests continued passing after the union schema was introduced.

- Observation: `recover_interrupted_pipelines` used `task_set.add(task)` expecting a `set` — this needed to be updated to `task_set[pipeline.id] = task` when we changed `pipeline_tasks` to a dict.
  Evidence: LSP error after the `main.py` change until `pipeline_runner.py` was updated too.

## Decision Log

- Decision: Approval steps are declared in `pipelines.yaml` as `{type: approval, description: "..."}` (no `agent` field required).
  Rationale: keeps the registry schema readable; approval is not an agent invocation so forcing an agent name would be misleading.
  Date/Author: 2026-02-27 / agent

- Decision: The `PipelineStep` schema uses a `type` discriminator (`agent` | `approval`) rather than making `agent` optional with a sentinel.
  Rationale: explicit union is cleaner and statically checkable; avoids ambiguous states.
  Date/Author: 2026-02-27 / agent

- Decision: When a pipeline is paused for approval its `Step` row keeps `status=running` (started but not finished). The `Approval` record carries its own `status=pending`. On approve/reject the Step status is updated accordingly.
  Rationale: keeps the step lifecycle consistent — running→done on approve, running→failed on reject.
  Date/Author: 2026-02-27 / agent

- Decision: `POST /approve` and `POST /reject` resume/cancel the background pipeline task by signalling an `asyncio.Event` stored in `app.state.approval_events[pipeline_id]`.
  Rationale: the background `_execute_steps` coroutine is already awaiting; signalling an event is the safest, non-blocking IPC mechanism within a single process.
  Date/Author: 2026-02-27 / agent

- Decision: `GET /approvals` query param renamed from `all` (shadows Python built-in) to `include_all`.
  Rationale: improves code quality; the old name would trigger linter warnings and is a footgun.
  Date/Author: 2026-02-27 / agent (SHOULD FIX from code review)

- Decision: `pipeline_tasks` changed from `set[asyncio.Task]` to `dict[int, asyncio.Task]` keyed by `pipeline_id`.
  Rationale: previously `abort_pipeline` cancelled all pipeline tasks regardless of which pipeline was being aborted. The dict allows O(1) targeted cancellation.
  Date/Author: 2026-02-27 / agent (MUST FIX from code review)

## Outcomes & Retrospective

All four milestones delivered and passing 109 tests. The approval gate feature enables a human (or caller) to pause a running pipeline at a designated checkpoint, review the work so far, and either approve (pipeline continues) or reject (pipeline fails). The implementation uses `asyncio.Event` for in-process signalling between the HTTP handler and the background runner — simple, zero-overhead, and test-friendly.

Code quality issues identified post-implementation (duplicate helper, bare `else`, wrong container type for tasks, blocking subprocess) were all resolved before committing. The refactors improved correctness (`pipeline_tasks` as dict) and maintainability (`_handle_approval_decision`, `_mark_pipeline_failed`, explicit `elif/else`).

## Context and Orientation

The repository is a Python/FastAPI backend (`backend/`) + Vite/React/TypeScript frontend
(`frontend/`), managed with NX. All backend work lives under `backend/app/`.

Key files for this feature:

- `backend/app/models.py` — SQLAlchemy ORM models. Relevant classes: `Pipeline`
  (has `status: PipelineStatus`, enum value `waiting_for_approval`), `Step`, `Approval`
  (has `status: ApprovalStatus` with values `pending/approved/rejected`, `comment`,
  `decided_by`, `decided_at`), `AuditEvent`.
- `backend/app/schemas/registry.py` — Pydantic models for the YAML config.
  `PipelineStep` currently has `agent: str` and `description: str`. We will extend it
  to support a `type` field distinguishing agent steps from approval steps.
- `backend/app/schemas/pipeline.py` — Pydantic schemas for the REST API responses.
  Contains `PipelineResponse`, `PipelineDetailResponse`, `StepStatusResponse`.
- `backend/app/services/pipeline_runner.py` — Core orchestration. The `_execute_steps`
  method loops over steps and calls `run_step` for each. We will add detection of
  approval steps here, pause the loop via an `asyncio.Event`, and resume when signalled.
- `backend/app/routers/pipelines.py` — FastAPI router. We will add three new endpoints:
  `POST /{id}/approve`, `POST /{id}/reject`, `GET /approvals` (this last one lives in a
  new router to avoid prefix confusion).
- `backend/app/main.py` — registers routers, manages `app.state`.
- `backend/app/tests/test_pipeline_runner.py` — unit tests for PipelineRunner.
- `backend/app/tests/test_pipelines_router.py` — integration tests for the router.

The test setup uses an in-memory SQLite database, `AsyncMock(spec=OpenCodeClient)` for
the OpenCode client, and `httpx.AsyncClient` over `ASGITransport` for HTTP tests.
`asyncio_mode = auto` is set in `pytest.ini` (or `pyproject.toml`) so all `async def`
test functions are automatically awaited. SQLAlchemy sessions use `expire_on_commit=False`.

An `asyncio.Event` (let's call it an "approval event") is a synchronisation primitive:
one coroutine calls `event.wait()` to pause until another coroutine calls `event.set()`.
We use one event per pipeline, keyed by `pipeline_id` in `app.state.approval_events`.

## Plan of Work

### Milestone 1 — Registry schema: approval step type

In `backend/app/schemas/registry.py`, replace the single `PipelineStep` model with a
union of two models: `AgentStep` (has `agent: str`, `description: str`, `type` literal
`"agent"`) and `ApprovalStep` (has `description: str`, `type` literal `"approval"`).
The top-level `PipelineStep` becomes an annotated union discriminated on `type`.

The `RegistryConfig` validator that checks steps reference known agents must be updated
to skip `ApprovalStep` instances.

Add a helper `is_approval_step` function or property so callers don't have to import
the union types directly.

Also add an `approval` step to the `VALID_PIPELINES` fixture in
`backend/app/tests/conftest.py` to enable pipeline-runner tests, and add a separate
`APPROVAL_PIPELINES` dict there for router tests that want an approval step.

### Milestone 2 — PipelineRunner: detect approval steps and pause

In `_execute_steps`, before calling `run_step`, check whether the step's agent_name is
the sentinel value `"__approval__"` (we will store this in the `Step.agent_name` column
when creating steps from an `ApprovalStep` template). When the sentinel is detected:

1. Create an `Approval` ORM record (`status=pending`, `step_id=step.id`).
2. Write an `AuditEvent` with `event_type="approval_requested"`.
3. Set `pipeline.status = PipelineStatus.waiting_for_approval`.
4. Commit.
5. `await approval_event.wait()` — the event is retrieved from
   `self._approval_events[pipeline.id]`.
6. After the event fires, re-read the `Approval` record from the DB to get the decision.
7. If `approved`: update the step to `done`, set `pipeline.status = running`, write audit
   event `approval_granted`, append the comment (if any) to `current_prompt`, continue.
8. If `rejected`: update the step to `failed`, set `pipeline.status = failed`, write
   audit event `approval_rejected`, commit, and return early.

The `PipelineRunner.__init__` gains an optional
`approval_events: dict[int, asyncio.Event] | None = None` parameter. When `None` the
runner creates its own empty dict (unit-test path). Production code passes
`app.state.approval_events`.

When the router creates steps for an `ApprovalStep`, it stores `agent_name="__approval__"`.

### Milestone 3 — Router: approve and reject endpoints

Add two endpoints to `backend/app/routers/pipelines.py`:

`POST /pipelines/{pipeline_id}/approve` (body: `ApproveRequest` with optional `comment:
str | None` and `decided_by: str | None`):
- Load pipeline, 404 if not found.
- 409 if `pipeline.status != waiting_for_approval`.
- Load the pending `Approval` for this pipeline's currently-running step (join via Step).
- Set `approval.status = approved`, `approval.comment = body.comment`,
  `approval.decided_by = body.decided_by`, `approval.decided_at = datetime.now(UTC)`.
- Commit.
- Signal `app.state.approval_events[pipeline_id].set()`.
- Return `PipelineResponse`.

`POST /pipelines/{pipeline_id}/reject` (body: `RejectRequest` same shape as ApproveRequest):
- Same load/guard as approve.
- Set `approval.status = rejected` + other fields.
- Commit.
- Signal the event (so the background task wakes up and reads the rejected status).
- Return `PipelineResponse`.

Add `ApproveRequest` and `RejectRequest` schemas to `backend/app/schemas/pipeline.py`.
Both have `comment: str | None = None` and `decided_by: str | None = None`.

Also add `ApprovalResponse` schema with fields `id`, `pipeline_id`, `step_id`, `status`,
`comment`, `decided_by`, `decided_at`. This is constructed manually (not ORM-mapped)
because `pipeline_id` lives on the related `Step`.

### Milestone 4 — Router: GET /approvals

Add a new file `backend/app/routers/approvals.py` with router prefix `/approvals`.

`GET /approvals` (optional query param `all: bool = False`): returns a list of
`ApprovalResponse` objects. Fetches `Approval` rows joined with their `Step` to get
`pipeline_id`. When `all=False` (default) filters by `status=pending`.

Register the new router in `backend/app/main.py`.

## Concrete Steps

All commands run from the `backend/` directory unless noted otherwise.

Run tests before any changes to establish a baseline:

    cd backend && uv run pytest app/tests/ -q

Expected: 88 passed.

After each milestone, run:

    uv run pytest app/tests/ -q

and verify the count increases and no regressions appear.

After all milestones:

    uv run ruff check app/ --fix
    uv run mypy app/ --ignore-missing-imports   # or whatever type-check command is configured

Check the NX type-check target:

    nx type-check backend

## Validation and Acceptance

### Unit test scenario (PipelineRunner, Milestone 2)

A pipeline template has two steps: step 0 is a normal agent step, step 1 is an approval step.

- `_execute_steps` runs step 0 normally.
- On reaching step 1 (sentinel `__approval__`), the runner creates an `Approval` record
  and sets `pipeline.status = waiting_for_approval`.
- A test helper sets the approval to `approved` and fires the event.
- The runner resumes, sets `pipeline.status = done`.

### HTTP test scenario (Milestone 3)

Create a pipeline whose template has an approval step. Mock the PipelineRunner so that
`_execute_steps` actually awaits an event (or use the real runner against the in-memory
DB with a controlled event). Then:

- `GET /pipelines/{id}` returns `status=waiting_for_approval`.
- `POST /pipelines/{id}/approve` returns 200.
- The pipeline eventually reaches `done`.

For the rejection path:
- `POST /pipelines/{id}/reject` returns 200, pipeline ends up `failed`.

### Edge cases to test

- `POST /approve` on a pipeline that is not `waiting_for_approval` → 409.
- `POST /approve` on a non-existent pipeline → 404.
- `GET /approvals` returns only pending by default; `?all=true` returns all.

## Idempotence and Recovery

- The approval_events dict is keyed by `pipeline_id`. If the server restarts while a
  pipeline is `waiting_for_approval`, a new event is never created, so `approve`/`reject`
  will try to signal a missing key. We guard against this: if the key is missing from
  `app.state.approval_events`, the router creates a fresh `Event` that is already `set()`
  (so a hypothetical resumed background task would not deadlock). For now, restarted
  pipelines in `waiting_for_approval` are not auto-resumed on startup — that is a
  follow-on concern.

## Artifacts and Notes

### Sentinel value

`Step.agent_name = "__approval__"` is the machine-readable marker that tells
`_execute_steps` this is an approval gate, not a real agent invocation. The value starts
and ends with double underscores to make accidental collisions with real agent names
extremely unlikely.

### Approval event lifecycle

    approval_events[pipeline_id] = asyncio.Event()   # created in router when pipeline launches
    # ... background task runs steps ...
    await approval_events[pipeline_id].wait()          # blocks inside _execute_steps
    # ... router handler receives approve/reject ...
    approval_events[pipeline_id].set()                 # unblocks _execute_steps
    del approval_events[pipeline_id]                   # cleaned up after step resolves

## Interfaces and Dependencies

In `backend/app/schemas/pipeline.py`, define:

    class ApproveRequest(BaseModel):
        comment: str | None = None
        decided_by: str | None = None

    class RejectRequest(BaseModel):
        comment: str | None = None
        decided_by: str | None = None

    class ApprovalResponse(BaseModel):
        id: int
        pipeline_id: int
        step_id: int
        status: ApprovalStatus
        comment: str | None
        decided_by: str | None
        decided_at: datetime | None

In `backend/app/schemas/registry.py`, define:

    class AgentStep(_RegistryBase):
        type: Literal["agent"] = "agent"
        agent: str
        description: str = ""

    class ApprovalStep(_RegistryBase):
        type: Literal["approval"]
        description: str = ""

    PipelineStep = Annotated[Union[AgentStep, ApprovalStep], Field(discriminator="type")]

In `backend/app/services/pipeline_runner.py`, the `PipelineRunner.__init__` gains:

    approval_events: dict[int, asyncio.Event] | None = None

In `backend/app/routers/approvals.py`, define:

    router = APIRouter(prefix="/approvals", tags=["approvals"])

    @router.get("", response_model=list[ApprovalResponse])
    async def list_approvals(all: bool = False, db: ...) -> list[ApprovalResponse]: ...
