# Feature: Pipeline Engine (Core Orchestrator)

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

theAgency orchestrates chains of specialised AI agents to work through a software feature
autonomously. After this feature, a developer can call a single HTTP endpoint with a pipeline
template name (e.g. `full_feature`) and a prompt (e.g. "Add dark mode toggle"), and the
system will execute each agent in the defined sequence — creating an OpenCode session per
step, sending the prompt enriched with context from the previous step, waiting for completion,
and persisting the result. If the server crashes mid-run, the pipeline can be resumed from
the last completed step. If a step fails, the pipeline is marked as failed with a human-readable
reason. The status of any pipeline and its individual steps is queryable at any time via REST.

A developer verifies the feature by running `npx nx run backend:test` (all tests pass), then
starting the server with `npx nx run backend:serve` and calling:

    curl -X POST http://localhost:8000/pipelines \
      -H "Content-Type: application/json" \
      -d '{"template": "quick_fix", "title": "Fix login bug", "prompt": "The login button is broken."}'

This returns a pipeline ID. The developer then polls `GET /pipelines/{id}` and watches the
status progress from `pending` → `running` → `done`. Each step is visible under `steps[*].status`.

## Progress

- [x] (2026-02-27 20:00Z) ExecPlan drafted
- [x] (2026-02-27) ExecPlan review — 4 MUST FIX, 6 SHOULD FIX, 6 CONSIDER findings
- [x] (2026-02-27) Review findings incorporated into revised plan
- [x] (2026-02-27) ExecPlan reviewed and approved by user ("leg los")
- [x] (2026-02-27) Milestone 0: Alembic migration for `prompt` column on Pipeline ✅
- [x] (2026-02-27) Milestone 1: PipelineRunner service (execute one step, persist state) — 7 tests ✅
- [x] (2026-02-27) Milestone 2: Full pipeline execution (sequential steps, handoff passing) — 4 tests ✅
- [x] (2026-02-27) Milestone 3: Crash recovery (resume from last completed step) — 4 tests ✅
- [x] (2026-02-27) Milestone 4: REST API (POST /pipelines, GET /pipelines/{id}, POST /pipelines/{id}/abort) — 7 tests ✅
- [x] (2026-02-27) Post-impl code-quality review — all MUST FIX resolved (assert→ValueError, datetime.utcnow→UTC, request lifetime, AsyncSessionLocal via app.state, delete_session guarded, duplication extracted to _execute_steps, abort cancels task)
- [ ] ExecPlan finalized: outcomes written, plan moved to completed/

## Surprises & Discoveries

- Production `AsyncSessionLocal` in `database.py` already uses `expire_on_commit=False`.
  The test `db_session` fixture must also set this to avoid `DetachedInstanceError` after
  commits in tests.
- `structlog.get_logger()` must be used instead of `logging.getLogger()` in service files.
- `step_timeout` parameter should be `float` not `int` to support sub-second timeouts in tests.
- SQLAlchemy lazy-loading raises `MissingGreenlet` when accessing relationships outside an async
  greenlet context. Fix: use `selectinload()` in an explicit `select()` query.
- SQLAlchemy identity map means `loaded_pipeline` (from eager query) and original `pipeline` arg
  are the same object — status updates are shared.
- `asyncio.TimeoutError` was aliased to builtin `TimeoutError` in Python 3.11 — ruff UP041 prefers
  the builtin form.
- `recover_interrupted_pipelines` session factory should be called *inside* the task closure to avoid
  leaking session objects if `create_task` fails.
- `db_session_factory` must be stored on `app.state` and injected into background tasks instead of
  importing `AsyncSessionLocal` directly in the router — this is the testable seam.
- Background task closures must capture `app.state` (long-lived) before `request` goes out of scope.

## Outcomes & Retrospective

All 66 tests pass. Lint clean. Frontend type-check clean.

Key architectural improvements made during post-impl review:
- Extracted `_execute_steps` private method to eliminate run_pipeline/resume_pipeline duplication
- All `assert` runtime guards replaced with `if ... raise ValueError`
- `datetime.utcnow()` replaced with `datetime.now(UTC)` throughout
- `_persist_success` no longer accepts unused `session_id` param
- `delete_session` in `finally` block guarded with try/except to prevent cleanup masking real error
- `abort_pipeline` now cancels the background task to prevent status overwrite race condition
- Background task captures `app_state` before `Request` goes out of scope
- `AsyncSessionLocal` removed from router imports; background sessions use `app.state.db_session_factory`

## Context and Orientation

The repo root is `theAgency/`. The backend is a Python 3.11 / FastAPI application in
`backend/`. All Python commands run inside `backend/` with `uv run`. NX targets are run
from the repo root. All NX backend targets set `cwd: "backend"`.

**Hexagonal architecture**: domain logic in `backend/app/services/`, external integrations
in `backend/app/adapters/`, thin HTTP wrappers in `backend/app/routers/`, shared Pydantic
schemas in `backend/app/schemas/`. New files follow this layout.

**Existing ORM models** (in `backend/app/models.py`): `Pipeline`, `Step`, `Handoff`,
`AuditEvent`, `Approval`. These are SQLAlchemy 2.x mapped classes using async sessions
(`AsyncSession` from `sqlalchemy.ext.asyncio`). The DB is SQLite via `aiosqlite`. The
`database_url` comes from `settings.database_url` in `backend/app/config/config.py`.

`Pipeline` has: `id`, `title`, `template` (name of the pipeline template), `prompt` (the
initial user prompt — **new column, added in Milestone 0**), `branch`, `status`
(PipelineStatus enum: pending/running/waiting_for_approval/done/failed), `created_at`,
`updated_at`, `steps` (relationship, ordered by `order_index`).

`Step` has: `id`, `pipeline_id`, `agent_name`, `order_index`, `status` (StepStatus
enum: pending/running/done/failed/skipped), `started_at`, `finished_at`, `handoffs`
(relationship), `approvals` (relationship).

`Handoff` has: `id`, `step_id`, `content_md` (text content produced by the agent),
`metadata_json` (optional JSON string), `created_at`.

**Database session** is obtained via the FastAPI dependency `get_db` which is defined in
`backend/app/database.py`. The production `AsyncSessionLocal` already uses
`expire_on_commit=False`. In tests, the `db_session` fixture must also set this.

**AgentRegistry** (already implemented, `backend/app/services/agent_registry.py`):
`registry.get_pipeline(name)` returns a `PipelineTemplate` with a list of `PipelineStep`
objects (each has `agent: str` and `description: str`). `registry.get_agent(name)` returns
an `AgentProfile` with `opencode_agent: str` (the OpenCode agent name) and
`system_prompt_additions: str`.

**OpenCodeClient** (already implemented, `backend/app/adapters/opencode_client.py`):
the HTTP client for the OpenCode server. Key methods used in this feature:
- `create_session(title)` → `SessionInfo(id, title)` — creates a new OpenCode session
- `send_message(session_id, prompt, agent)` → `MessageResponse` — **synchronous, blocks
  until the agent completes**. This is our primary completion mechanism for MVP.
- `abort_session(session_id)` → `bool` — aborts a running agent in a specific session
- `delete_session(session_id)` → `bool` — cleanup

Methods NOT used in this feature (deferred to future SSE-based approach):
- `send_message_async` — fire-and-forget, requires SSE for completion detection
- `stream_events` / `stop_streaming` — SSE stream with shared `_stop_event`

**OpenCodeProcessManager** (already implemented,
`backend/app/adapters/opencode_process.py`): manages the lifecycle of the `opencode serve`
subprocess. **Not used in MVP** — OpenCode must be running externally. The lifespan creates
an `OpenCodeClient` directly from `settings.opencode_base_url`.

**Existing test infrastructure**: `backend/app/tests/conftest.py` has shared fixtures.
PipelineRunner tests use `AsyncMock` on `OpenCodeClient` methods (hexagonal boundary), NOT
`respx` HTTP mocking. `asyncio_mode = auto` is set in `pyproject.toml`.

**Database in tests**: use a real in-memory SQLite DB with
`create_async_engine("sqlite+aiosqlite:///:memory:")` and `Base.metadata.create_all`.
The `db_session` fixture must set `expire_on_commit=False` to match production behavior
and avoid `DetachedInstanceError` after commits.

**Settings** (`backend/app/config/config.py`): add `opencode_base_url: str =
"http://localhost:4096"` (new, replaces the idea of auto-starting ProcessManager) and
`step_timeout_seconds: int = 600` (new, 10-minute default per-step timeout).

## Plan of Work

### Milestone 0 — Alembic migration: add `prompt` column to Pipeline

The Pipeline model needs a `prompt` column to persist the initial user prompt for crash
recovery. Without it, `resume_pipeline` cannot know what prompt to use.

1. Add `prompt: Mapped[str] = mapped_column(Text, nullable=False, server_default="")` to
   the `Pipeline` class in `backend/app/models.py`. The `server_default=""` handles existing
   rows (there shouldn't be any in practice, but migrations must be safe).

2. Add `order_by="Step.order_index"` to the `Pipeline.steps` relationship to make step
   ordering explicit.

3. Add `opencode_base_url: str = "http://localhost:4096"` and `step_timeout_seconds: int = 600`
   to `Settings` in `backend/app/config/config.py`.

4. Generate an Alembic migration:
   `npx nx run backend:makemigration -- -m "add_prompt_to_pipeline"`

5. Run the migration: `npx nx run backend:migrate`

6. Verify: `npx nx run backend:test` — all 44 existing tests still pass.

No TDD tests for the migration itself — the existing test suite validates nothing breaks.

### Milestone 1 — PipelineRunner service: execute one step and persist state

This milestone delivers the core execution unit: a service that takes a single pipeline step,
creates an OpenCode session, sends the prompt using synchronous `send_message`, saves the
handoff content to the database, and updates the step status.

Create `backend/app/services/pipeline_runner.py`. The `PipelineRunner` class is
constructed with an `OpenCodeClient`, an `AsyncSession`, and an `AgentRegistry`. It
exposes one public method:

    async def run_step(
        self,
        step: Step,             # the ORM Step object (already persisted, status=running)
        agent_profile: AgentProfile,  # from the registry
        prompt: str,            # the user prompt or previous handoff content
    ) -> str:
        """Execute one step. Returns the assistant's final output text.
        Updates step.status to done or failed and persists a Handoff record.
        Raises StepExecutionError on unrecoverable failure."""

The `PipelineRunner` also exposes a `current_session_id: str | None` property so the abort
endpoint can target the active OpenCode session.

The implementation:

1. Call `self._client.create_session(title=f"{step.agent_name}-{step.id}")` to get a
   `SessionInfo`. Store the session ID on `self._current_session_id`.

2. Build the full prompt: if `agent_profile.system_prompt_additions` is non-empty, prepend it
   as `"<system additions>\n\n{prompt}"`. Otherwise use `prompt` as-is.

3. Call `send_message` synchronously, wrapped in `asyncio.wait_for` with
   `settings.step_timeout_seconds` timeout:

       response = await asyncio.wait_for(
           self._client.send_message(session_id, prompt=full_prompt,
               agent=agent_profile.opencode_agent),
           timeout=self._step_timeout,
       )

   On `asyncio.TimeoutError`: call `self._client.abort_session(session_id)`, set
   `step.status = StepStatus.failed`, `step.finished_at = utcnow()`. Commit. Raise
   `StepExecutionError("Step timed out after {timeout}s")`.

4. Extract the output text from `MessageResponse`. The `MessageResponse` model contains
   the assistant's response. Use `response.content` (or however the model exposes it).
   If extraction fails, use an empty string and log a warning.

5. Persist a `Handoff(step_id=step.id, content_md=output_text)` via the session. Set
   `step.status = StepStatus.done` and `step.finished_at = datetime.utcnow()`. Commit.
   Return the output text.

6. On `OpenCodeClientError` during `send_message`: set `step.status = StepStatus.failed`,
   `step.finished_at = datetime.utcnow()`. Commit. Raise `StepExecutionError(...)`.

7. Always call `await self._client.delete_session(session_id)` in a `finally` block for
   cleanup. Reset `self._current_session_id = None` in finally as well.

Define `StepExecutionError(Exception)` at the top of the module.

**Known limitation**: `system_prompt_additions` is simply concatenated as a prefix to the
user prompt. This is a crude approach — a proper system prompt injection mechanism would
require OpenCode API support for system messages. Documented as acceptable for MVP.

TDD tests in `backend/app/tests/test_pipeline_runner.py`. Mock `OpenCodeClient` using
`AsyncMock` (the hexagonal boundary), NOT `respx` HTTP mocking. Use a real in-memory
SQLite database for the `AsyncSession`. Fixture pattern:

    @pytest.fixture
    async def db_session():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session
        await engine.dispose()

    @pytest.fixture
    def mock_client():
        client = AsyncMock(spec=OpenCodeClient)
        client.create_session.return_value = SessionInfo(id="test-session", title="test")
        client.send_message.return_value = MessageResponse(...)  # appropriate mock
        client.delete_session.return_value = True
        return client

Test order (one at a time, red/green/refactor):

1. `test_run_step_success` — mock `create_session`, `send_message`, `delete_session`.
   Assert step.status is `done`, a `Handoff` row exists in DB, method returns output text.

2. `test_run_step_failure_raises_error` — mock `send_message` to raise
   `OpenCodeClientError`. Assert `StepExecutionError` raised, step.status is `failed`.

3. `test_run_step_deletes_session_on_success` — assert `delete_session` is called even on
   success.

4. `test_run_step_deletes_session_on_failure` — assert `delete_session` is called even when
   the step fails.

5. `test_run_step_includes_system_prompt_additions` — agent profile has non-empty
   `system_prompt_additions`. Assert the prompt sent via `send_message` starts with the
   additions text.

6. `test_run_step_timeout_aborts_session` — mock `send_message` to block forever (use
   `asyncio.sleep(9999)` as side effect). Set timeout to 0.1s. Assert `StepExecutionError`
   raised with "timed out", `abort_session` called, step.status is `failed`.

7. `test_current_session_id_set_during_execution` — verify that `current_session_id` is
   set to the session ID during step execution and reset to `None` after.

### Milestone 2 — Full pipeline execution: sequential steps with handoff passing

This milestone adds `run_pipeline` to `PipelineRunner`, which iterates over all steps in order,
runs each with `run_step`, passes the output of step N as the prompt for step N+1, and
updates the `Pipeline` ORM status throughout.

Add to `PipelineRunner`:

    async def run_pipeline(
        self,
        pipeline: Pipeline,        # ORM object, already status=running
        template: PipelineTemplate, # from registry
    ) -> None:
        """Execute all steps sequentially. Updates pipeline.status to done or failed.
        Uses pipeline.prompt as the initial prompt (persisted on the Pipeline ORM)."""

The implementation:

1. `current_prompt = pipeline.prompt` (persisted on the ORM, set when pipeline was created).

2. Steps are already sorted by `order_index` via the relationship `order_by`.

3. For each step:
   a. Set `step.status = StepStatus.running`, `step.started_at = datetime.utcnow()`. Commit.
   b. Look up the `AgentProfile` from the registry by `step.agent_name`. If not found, set
      step and pipeline to failed, raise `StepExecutionError`.
   c. Call `output = await self.run_step(step, agent_profile, current_prompt)`.
   d. `current_prompt = output` (the handoff content becomes the next step's prompt).
   e. On `StepExecutionError`: set `pipeline.status = PipelineStatus.failed`,
      `pipeline.updated_at = datetime.utcnow()`. Commit. Return (do not re-raise — the
      background task should complete gracefully, the pipeline status tells the story).

4. After all steps succeed: set `pipeline.status = PipelineStatus.done`,
   `pipeline.updated_at = datetime.utcnow()`. Commit.

Note: `run_pipeline` no longer accepts `initial_prompt` as a parameter — it reads from
`pipeline.prompt`. This ensures crash recovery always has access to the original prompt.

TDD tests in `test_pipeline_runner.py` (continue in same file):

8. `test_run_pipeline_success` — two-step pipeline, mock both steps completing successfully.
   Assert `pipeline.status == PipelineStatus.done`, both steps have status `done`, the second
   step received the first step's output as its prompt.

9. `test_run_pipeline_step_failure_marks_pipeline_failed` — first step fails. Assert
   `pipeline.status == PipelineStatus.failed`, second step remains `pending`.

10. `test_run_pipeline_passes_handoff_as_next_prompt` — verify that the second step's prompt
    equals the first step's output text (inspect `send_message` call args).

11. `test_run_pipeline_unknown_agent_marks_pipeline_failed` — step references an agent not
    in the registry. Assert pipeline is failed with appropriate error.

### Milestone 3 — Crash recovery: resume from last completed step

After a server crash, a pipeline that was in `running` state with some steps already `done`
should be resumable. This milestone adds a `resume_pipeline` method and the startup logic that
detects and re-queues interrupted pipelines.

Add to `PipelineRunner`:

    async def resume_pipeline(
        self,
        pipeline: Pipeline,
        template: PipelineTemplate,
    ) -> None:
        """Resume a pipeline from the first non-done step.
        If all steps are done, marks the pipeline as done immediately.
        Uses the last Handoff content as the prompt for the next pending step,
        or pipeline.prompt if no steps have completed yet."""

The implementation:

1. Steps are already sorted by `order_index` via the relationship.
2. Find the last `done` step (if any). Load its `handoffs` and use the most recent
   `content_md` as `current_prompt`. If no done steps, use `pipeline.prompt`.
3. Find the first step that is not `done`. If none, set `pipeline.status = PipelineStatus.done`
   and return.
4. For each remaining step (starting from the first non-done step), execute as in
   `run_pipeline` — set running, call `run_step`, pass handoff forward.

Add a startup utility function `recover_interrupted_pipelines` in the same module:

    async def recover_interrupted_pipelines(
        db_session_factory: async_sessionmaker[AsyncSession],
        client: OpenCodeClient,
        registry: AgentRegistry,
        task_set: set[asyncio.Task],
        step_timeout: int,
    ) -> None:
        """Find all pipelines stuck in 'running' status and re-queue them as background tasks."""

This function:
1. Creates its own DB session from `db_session_factory`.
2. Queries for pipelines with `status == PipelineStatus.running`.
3. For each one, creates a new `PipelineRunner` with its own DB session, and launches
   `asyncio.create_task(runner.resume_pipeline(...))`.
4. Adds each task to `task_set` with a done callback for cleanup.
5. Is called from the FastAPI lifespan after the registry and OpenCode client are initialized.

TDD tests:

12. `test_resume_pipeline_skips_completed_steps` — pipeline with step 1 done, step 2 pending.
    Assert only step 2 is executed (mock verifies `send_message` called once).

13. `test_resume_pipeline_uses_last_handoff_as_prompt` — step 1 is done with a handoff
    containing "prev output". Assert step 2 receives "prev output" as its prompt.

14. `test_resume_pipeline_all_done_marks_done` — all steps are already done.
    Assert `pipeline.status == PipelineStatus.done` and no `send_message` call made.

15. `test_resume_pipeline_no_done_steps_uses_pipeline_prompt` — no steps are done.
    Assert first step receives `pipeline.prompt` as its prompt.

### Milestone 4 — REST API

This milestone exposes the pipeline engine via HTTP. Three endpoints:

`POST /pipelines` — Create and start a pipeline run. Request body:
`{"template": str, "title": str, "prompt": str, "branch": str | None}`.
Validates that the template exists in the registry. Creates `Pipeline` (with `prompt`
persisted) and all `Step` ORM records (status=pending). Sets `pipeline.status =
PipelineStatus.running`. Launches a background task that:
1. Creates its own DB session from `AsyncSessionLocal`.
2. Re-fetches the Pipeline by ID.
3. Creates a `PipelineRunner` with the new session.
4. Calls `runner.run_pipeline(pipeline, template)`.
The background task is added to `app.state.pipeline_tasks` with a done callback.
Returns `201 Created` with a `PipelineResponse` body.

`GET /pipelines/{id}` — Retrieve pipeline status and all step statuses.
Returns `200 OK` with `PipelineDetailResponse` or `404 Not Found`.

`POST /pipelines/{id}/abort` — Abort a running pipeline. Sets `pipeline.status = failed`,
sets any `running` steps to `failed`. To interrupt the currently running OpenCode agent,
the abort endpoint needs to find the active `PipelineRunner` for this pipeline and call
`client.abort_session(runner.current_session_id)`. This requires a mapping from pipeline ID
to runner instance, stored in `app.state.active_runners: dict[int, PipelineRunner]`.
Returns `200 OK`.

Create `backend/app/schemas/pipeline.py` with request and response Pydantic models:

    class PipelineCreateRequest(BaseModel):
        template: str
        title: str
        prompt: str
        branch: str | None = None

    class StepStatusResponse(BaseModel):
        model_config = ConfigDict(from_attributes=True)
        id: int
        agent_name: str
        order_index: int
        status: StepStatus
        started_at: datetime | None
        finished_at: datetime | None

    class PipelineResponse(BaseModel):
        model_config = ConfigDict(from_attributes=True)
        id: int
        title: str
        template: str
        status: PipelineStatus
        created_at: datetime
        updated_at: datetime

    class PipelineDetailResponse(PipelineResponse):
        steps: list[StepStatusResponse]

Create `backend/app/routers/pipelines.py`. The router needs three FastAPI dependencies:
`get_db` (from `backend/app/database.py`), `get_registry` (from `backend/app/routers/registry.py`),
and `get_opencode_client` (new, reads `request.app.state.opencode_client`).

Add `get_opencode_client` dependency in the pipelines router (same pattern as `get_registry`):

    def get_opencode_client(request: Request) -> OpenCodeClient:
        return request.app.state.opencode_client

In `backend/app/main.py` lifespan: after registry setup, create an `OpenCodeClient` from
`settings.opencode_base_url` (no ProcessManager). Store on `app.state.opencode_client`.
Initialize `app.state.pipeline_tasks: set[asyncio.Task] = set()` and
`app.state.active_runners: dict[int, PipelineRunner] = {}`.
On shutdown: cancel all tasks in `pipeline_tasks`, await them, close the OpenCodeClient.
Call `recover_interrupted_pipelines` after all state is initialized.

Mount the new router in `main.py`: `app.include_router(pipelines_router.router)`.

TDD tests in `backend/app/tests/test_pipelines_router.py`. Use `AsyncClient` with
`ASGITransport`. Override `get_db`, `get_registry`, and `get_opencode_client` via
`app.dependency_overrides`. Mock `PipelineRunner.run_pipeline` to avoid executing real
OpenCode calls (patch the `run_pipeline` method or mock the background task creation).

Test order:

16. `test_create_pipeline_returns_201` — POST with valid template name. Assert 201, response
    has `id` and `status == "running"`.

17. `test_create_pipeline_unknown_template_returns_422` — POST with a template name that
    doesn't exist in the registry. Assert 422.

18. `test_create_pipeline_persists_prompt` — POST, then GET the pipeline from DB. Assert
    `pipeline.prompt` matches the request body's prompt.

19. `test_get_pipeline_returns_200` — create pipeline record in DB, GET it. Assert 200,
    response contains `steps` list with correct enum values.

20. `test_get_pipeline_not_found_returns_404` — GET /pipelines/99999. Assert 404.

21. `test_abort_pipeline_returns_200` — create running pipeline, POST abort. Assert 200,
    pipeline status is `failed` in DB.

22. `test_abort_pipeline_not_running_returns_409` — abort a pipeline that's already `done`.
    Assert 409 Conflict.

## Concrete Steps

All NX commands from the repo root. Manual `uv` commands from `backend/`.

    # Check currently installed packages (aiosqlite already in deps from #10)
    # No new Python deps required for M0-M4.

    # Generate migration (M0)
    npx nx run backend:makemigration -- -m "add_prompt_to_pipeline"

    # Run migration
    npx nx run backend:migrate

    # Run tests
    npx nx run backend:test

    # Lint
    npx nx run backend:lint

    # Type-check frontend (should stay clean)
    npx nx run frontend:type-check

    # Start server for manual verification
    npx nx run backend:serve

    # Create a pipeline (requires OpenCode running separately)
    curl -X POST http://localhost:8000/pipelines \
      -H "Content-Type: application/json" \
      -d '{"template": "quick_fix", "title": "Fix bug", "prompt": "Button is broken."}'

    # Poll status
    curl http://localhost:8000/pipelines/1 | python3 -m json.tool

## Validation and Acceptance

After all milestones, the following must be true:

1. `npx nx run backend:test` passes — 44 existing + ~22 new = ~66 tests total.
2. `npx nx run backend:lint` exits clean.
3. `npx nx run frontend:type-check` exits clean.
4. `POST /pipelines` with `template: "quick_fix"` and a prompt creates a pipeline, returns 201
   with an `id`. `GET /pipelines/{id}` returns the pipeline with `steps` array.
5. If OpenCode is running and reachable, the quick_fix pipeline executes both steps sequentially
   and reaches `status: "done"`.
6. Crash recovery: start a pipeline, kill the server mid-execution (Ctrl+C), restart — the
   pipeline is automatically resumed from the last completed step.

## Idempotence and Recovery

One new Alembic migration adds the `prompt` column to the `pipelines` table. The migration
uses `server_default=""` so it is safe to run on an existing database with rows. The
`PipelineRunner` is stateless between runs (no caches), so re-running tests is safe. The
in-memory SQLite fixture used in tests is created fresh for each test and disposed after.
The `recover_interrupted_pipelines` function is safe to run multiple times: re-queueing a
pipeline that is already running is prevented by the `running` status filter (a resumed
pipeline transitions immediately out of `running` on its first step).

## Artifacts and Notes

**Template snapshot risk**: The `AgentRegistry` supports hot-reload via file watching. If a
pipeline template is modified while a pipeline is running, the remaining steps could reference
agents that no longer exist or have changed configuration. This is a known limitation for MVP.
Mitigation: the registry lookup in `run_pipeline` will fail gracefully if an agent is not
found, marking the pipeline as failed. A proper solution (snapshotting the template at pipeline
creation time) is deferred.

**MessageResponse shape**: The `send_message` method returns a `MessageResponse` Pydantic
model (defined in `backend/app/adapters/opencode_models.py`). The exact field containing the
assistant output text needs to be verified when implementing Milestone 1 — inspect the model
definition and test against a real OpenCode instance if possible.

**Test count**: The estimate of ~22 new tests is a minimum. Additional edge case tests may
be added during TDD as needed.

## Interfaces and Dependencies

No new Python packages required. All dependencies are already present:
`sqlalchemy[asyncio]`, `aiosqlite`, `fastapi`, `httpx`, `pydantic`, `structlog`.

New files:

    backend/app/services/pipeline_runner.py
    backend/app/schemas/pipeline.py
    backend/app/routers/pipelines.py
    backend/app/tests/test_pipeline_runner.py
    backend/app/tests/test_pipelines_router.py

Modified files:

    backend/app/models.py          — add prompt column, add order_by on steps relationship
    backend/app/config/config.py   — add opencode_base_url, step_timeout_seconds settings
    backend/app/main.py            — lifespan: add OpenCodeClient, task tracking, recovery
    backend/app/database.py        — (no changes needed, already has expire_on_commit=False)
    backend/app/schemas/__init__.py — (no change needed, stays empty)

Key signatures at end of Milestone 4:

In `backend/app/services/pipeline_runner.py`:

    class StepExecutionError(Exception): ...

    class PipelineRunner:
        def __init__(self, client: OpenCodeClient, db: AsyncSession,
                     registry: AgentRegistry, step_timeout: int = 600) -> None: ...
        @property
        def current_session_id(self) -> str | None: ...
        async def run_step(self, step: Step, agent_profile: AgentProfile, prompt: str) -> str: ...
        async def run_pipeline(self, pipeline: Pipeline, template: PipelineTemplate) -> None: ...
        async def resume_pipeline(self, pipeline: Pipeline, template: PipelineTemplate) -> None: ...

    async def recover_interrupted_pipelines(
        db_session_factory: async_sessionmaker[AsyncSession],
        client: OpenCodeClient,
        registry: AgentRegistry,
        task_set: set[asyncio.Task],
        step_timeout: int,
    ) -> None: ...

In `backend/app/routers/pipelines.py`:

    router = APIRouter(prefix="/pipelines", tags=["pipelines"])

    def get_opencode_client(request: Request) -> OpenCodeClient: ...

    @router.post("/", response_model=PipelineResponse, status_code=201) ...
    @router.get("/{pipeline_id}", response_model=PipelineDetailResponse) ...
    @router.post("/{pipeline_id}/abort", response_model=PipelineResponse) ...
