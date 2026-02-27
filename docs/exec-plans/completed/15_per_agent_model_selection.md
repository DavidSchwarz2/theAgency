# Per-Agent Model Selection in Pipeline Steps

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

Currently every pipeline step calls OpenCode with no explicit model, meaning OpenCode picks
whatever its configured default is. This change lets each agent definition in `agents.yaml`
carry an optional `default_model` field (e.g. `claude-opus-4-5`), and lets a pipeline run
override the model per step via the `PipelineCreateRequest`. When execution reaches a step,
`PipelineRunner.run_step` passes the resolved model string to `OpenCodeClient.send_message`,
which already supports a `model` parameter. If no model is configured anywhere, nothing
changes — OpenCode continues using its own default.

To see it working: after implementation, add `default_model: claude-opus-4-5` to an agent in
`agents.yaml`, start a pipeline, and observe in test that `send_message` is called with
`model="claude-opus-4-5"`. The frontend creation modal gains an optional model text field
per step in Issue #16; this plan covers only the backend data model and runtime wiring, plus
exposing model info to the frontend via the `AgentProfileResponse`.

## Progress

- [x] (2026-02-27 11:00Z) ExecPlan written.
- [x] Milestone 1: Add `default_model` to `AgentProfile` schema and `AgentProfileResponse`; add `model` to `AgentStep`.
- [x] Milestone 2: Add `model` to `AgentStep` and wire step-level override storage (`Step.model` column + migration `f9486768fea8`).
- [x] Milestone 3: Pass model to `PipelineRunner.run_step`; wire from `_execute_steps`.
- [x] Milestone 4: Thread `step_models` through `PipelineCreateRequest` → `Step` creation in router.
- [x] All tests pass: `npx nx run backend:test` — 138 passed.
- [x] Frontend type-check passes: `npx nx run frontend:type-check` — zero errors.
- [x] ExecPlan finalized: outcomes written, plan moved to completed location per AGENTS.md.

## Surprises & Discoveries

- Existing `send_message` mock side-effects in `test_pipeline_runner.py` used named local functions
  (`capturing_send`, `send_message`) that referenced the old name in the `side_effect` assignment
  after rename — required careful targeted edits to fix all references.
- FastAPI's `status.HTTP_422_UNPROCESSABLE_ENTITY` is deprecated in newer FastAPI; switched to
  `status.HTTP_422_UNPROCESSABLE_CONTENT`.
- `StepStatus` in `frontend/src/types/api.ts` was missing the `'skipped'` variant — caught by the
  code-quality review and fixed.

## Decision Log

- Decision: Store the resolved model on the `Step` ORM row as a nullable `model` column rather
  than re-reading it from `AgentProfile` at run time.
  Rationale: The step-level override wins over the agent default; storing it on `Step` means
  the decision is captured at pipeline-creation time and survives a registry reload. It also
  makes the audit log accurate — if the registry YAML changes mid-run, the stored value still
  reflects what was actually used. A DB migration adds the column.
  Date/Author: 2026-02-27 / agent

- Decision: Accept step-level model overrides in `PipelineCreateRequest` as an optional
  `step_models: dict[int, str] | None` (keyed by `order_index`), rather than as a flat list.
  Rationale: The dict is sparse — most steps won't override. Using `order_index` as the key
  matches how the router iterates the template steps (`enumerate`).
  Date/Author: 2026-02-27 / agent

- Decision: Do not add a `/models` endpoint in this issue. The frontend modal (Issue #16)
  will use a free-text input for model overrides; a curated dropdown can be added later.
  Rationale: Issue #15 AC says "hardcoded curated list or fetched from backend"; a text field
  satisfies the AC with minimal scope.
  Date/Author: 2026-02-27 / agent

- Decision: Use Alembic for the DB migration to add `Step.model`.
  Rationale: SQLite allows `ALTER TABLE … ADD COLUMN` for nullable columns; Alembic wraps
  this cleanly and keeps the migration history consistent with the existing setup.
  Date/Author: 2026-02-27 / agent

## Outcomes & Retrospective

All 5 milestones completed. 138 backend tests pass, 0 frontend type errors.

The model resolution invariant (router owns it at creation time, runner trusts `Step.model` in
normal operation with a fallback for crash recovery) is documented inline in `pipeline_runner.py`.

The implementation is fully additive — no breaking changes to existing pipelines (all new fields
default to `None`). The Alembic migration (`f9486768fea8_add_model_to_steps.py`) is safe for
existing databases.

Next: Issue #16 (Free agent composition in pipeline creation UI) can wire up the frontend UI to
send `step_models` in the create request, now that the backend fully supports it.

## Context and Orientation

The project is a Python/FastAPI backend (`backend/`) + Vite/React/TypeScript frontend
(`frontend/`). The backend follows Hexagonal architecture: domain schemas in
`backend/app/schemas/`, ORM models in `backend/app/models.py`, service logic in
`backend/app/services/`, HTTP adapters in `backend/app/adapters/`.

Key files and their current state:

`backend/app/schemas/registry.py` — Pydantic schemas for the agent and pipeline registry.
`AgentProfile` is the domain model for an agent definition. It currently has `name`,
`description`, `opencode_agent`, `system_prompt_additions`. `AgentProfileResponse` is the
API-facing subset (omits `system_prompt_additions`). `AgentStep` is a Pydantic model for one
step inside a `PipelineTemplate`; it has `type`, `agent`, `description`.

`backend/app/models.py` — SQLAlchemy ORM. `Step` stores one row per pipeline step: `id`,
`pipeline_id`, `agent_name`, `order_index`, `status`, `started_at`, `finished_at`. There is
no `model` column yet.

`backend/app/services/pipeline_runner.py` — `PipelineRunner` orchestrates step execution.
`run_step(step, agent_profile, prompt)` calls `self._client.send_message(session_id, prompt,
agent=agent_profile.opencode_agent)`. The `model` keyword argument is never passed today.
`_execute_steps` loops through sorted steps, looks up the agent profile from the registry by
`step.agent_name`, then calls `run_step`.

`backend/app/adapters/opencode_client.py` — `OpenCodeClient.send_message` already accepts
`model: str | None = None` and forwards it in the JSON body. No changes needed here.

`backend/app/schemas/pipeline.py` — `PipelineCreateRequest` is the POST body for creating a
pipeline: `template`, `title`, `prompt`, `branch`. It needs an optional `step_models` field.

`backend/app/routers/pipelines.py` — `create_pipeline` endpoint: iterates `template.steps`
with `enumerate`, creates `Step` rows, then launches a background task. It will need to store
the resolved model on each `Step` row.

`backend/app/tests/test_pipeline_runner.py` — comprehensive TDD tests for `PipelineRunner`.
All mock `send_message` side-effects accept `(session_id, prompt, agent=None)` — they need to
also tolerate `model=None` (or be updated to accept `**kwargs`). New tests cover model passing.

Database migrations live in `backend/migrations/versions/`. Alembic is configured in
`backend/alembic.ini` and `backend/migrations/env.py`. Run `alembic upgrade head` from
`backend/` to apply.

Testing: run `npx nx run backend:test` from the repo root. The test suite uses
`asyncio_mode = "auto"` (set in `backend/pyproject.toml`). Use `AsyncMock(spec=OpenCodeClient)`
for client mocks.

## Plan of Work

The implementation proceeds across four milestones, each independently committable.

**Milestone 1 — Schema changes: `AgentProfile.default_model` and `AgentStep.model`.**

In `backend/app/schemas/registry.py`, add `default_model: str | None = None` to `AgentProfile`
(before `system_prompt_additions`), and add `model: str | None = None` to `AgentStep`. Also
add `default_model: str | None = None` to `AgentProfileResponse` so the frontend can display
the agent's configured default.

No YAML changes are needed for existing files — the field is optional and defaults to `None`.
The test YAML in `conftest.py` doesn't need updating.

Write one failing test first: `test_agent_profile_default_model_defaults_to_none` —
instantiate `AgentProfile(name="x", description="d", opencode_agent="x")` and assert
`profile.default_model is None`. Run it — it fails because the field doesn't exist. Add the
field. Run again — it passes. That's the red/green for Milestone 1.

**Milestone 2 — ORM column: `Step.model` and Alembic migration.**

In `backend/app/models.py`, add to `Step`:

    model: Mapped[str | None] = mapped_column(String(255), nullable=True)

Generate an Alembic migration:

    alembic revision --autogenerate -m "add model to steps"

Then apply it with `alembic upgrade head` (from `backend/`). The migration adds a single
nullable `VARCHAR(255)` column to the `steps` table.

Write one failing test: `test_step_model_column_nullable` — create a `Step` in-memory
(SQLite), persist it without a model, assert `step.model is None`. Passes after the column
is added.

**Milestone 3 — `PipelineRunner.run_step` passes `model`.**

Change the `run_step` signature to accept an optional `model: str | None = None` parameter.
Inside `run_step`, pass `model=model` to `send_message`. The call becomes:

    self._client.send_message(session_id, prompt=full_prompt,
                              agent=agent_profile.opencode_agent, model=model)

In `_execute_steps`, resolve the model for each step: prefer `step.model` (the stored
per-step override) over `agent_profile.default_model`. Pass it to `run_step`:

    model = step.model or agent_profile.default_model
    output_text, handoff_schema = await self.run_step(step, agent_profile, current_prompt,
                                                      model=model)

Write failing tests:
1. `test_run_step_passes_model_to_send_message` — set `model="claude-opus-4-5"`, call
   `run_step(..., model="claude-opus-4-5")`, assert `mock_client.send_message` was called with
   `model="claude-opus-4-5"`.
2. `test_run_step_passes_model_none_when_not_set` — call without `model`, assert
   `send_message` was called with `model=None`.
3. `test_execute_steps_uses_agent_default_model` — create a pipeline where the agent profile
   has `default_model="gpt-4o"` and the step has `step.model = None`; assert
   `send_message` is called with `model="gpt-4o"`.
4. `test_execute_steps_uses_step_model_over_agent_default` — step has `model="claude-sonnet"`,
   agent profile has `default_model="gpt-4o"`; assert `send_message` is called with
   `model="claude-sonnet"`.

Existing tests use `side_effect = async def send_message(session_id, prompt, agent=None):` —
these will break at runtime because `send_message` is now called with `model=` keyword arg.
Update all such side-effects to accept `**kwargs` or add `model=None`.

**Milestone 4 — `PipelineCreateRequest.step_models` → Step creation.**

In `backend/app/schemas/pipeline.py`, add to `PipelineCreateRequest`:

    step_models: dict[int, str] | None = None

This is a mapping of `order_index → model_string`.

In `backend/app/routers/pipelines.py`, inside `create_pipeline`, when building each `Step`,
resolve the model:

    step_model = (body.step_models or {}).get(idx)
    if step_model is None:
        agent_profile = registry.get_agent(step_def.agent) if isinstance(step_def, AgentStep) else None
        step_model = agent_profile.default_model if agent_profile else None
    step = Step(..., model=step_model)

This bakes the resolved model into the `Step` row at creation time.

Write a router test: `test_create_pipeline_stores_step_model` — POST with
`step_models={"0": "claude-sonnet"}` (JSON keys are always strings; the Pydantic type
`dict[int, str]` will coerce them), then query the DB and assert `step.model == "claude-sonnet"`.

Also add `model: str | None` to `StepStatusResponse` so the API exposes the stored model.
Update the frontend `Step` interface in `frontend/src/types/api.ts` to add `model?: string`.

## Concrete Steps

Run all commands from the repo root unless otherwise noted.

**Step 1: Write failing test for Milestone 1, then implement.**

    npx nx run backend:test -- -k "test_agent_profile_default_model"

Expect 1 failed (field missing). Add the fields to schemas. Run again — expect 1 passed.

**Step 2: Write failing test for Milestone 2, then implement.**

Generate migration (from `backend/`):

    alembic revision --autogenerate -m "add model to steps"
    alembic upgrade head

    npx nx run backend:test -- -k "test_step_model_column"

**Step 3: Write failing tests for Milestone 3, then implement.**

    npx nx run backend:test -- -k "test_run_step_passes_model or test_execute_steps_uses"

Fix existing `send_message` side-effects in tests to tolerate `model=None`. Then run full suite:

    npx nx run backend:test

**Step 4: Write failing router test for Milestone 4, then implement.**

    npx nx run backend:test -- -k "test_create_pipeline_stores_step_model"

Then run full suite.

**Step 5: Frontend type update, then type-check.**

    npx nx run frontend:type-check

## Validation and Acceptance

Run the full backend test suite from the repo root:

    npx nx run backend:test

Expect all tests to pass (no failures, no skips). The new tests are:
- `test_agent_profile_default_model_defaults_to_none`
- `test_agent_step_model_defaults_to_none`
- `test_step_model_column_nullable`
- `test_run_step_passes_model_to_send_message`
- `test_run_step_passes_model_none_when_not_set`
- `test_execute_steps_uses_agent_default_model`
- `test_execute_steps_uses_step_model_over_agent_default`
- `test_create_pipeline_stores_step_model`

Run `npx nx run frontend:type-check` — expect zero errors.

## Idempotence and Recovery

The Alembic migration adds a nullable column — safe to apply on an existing database. Running
it twice is safe (Alembic checks the current revision). If the migration fails, delete the
generated file and regenerate. All other changes are additive Pydantic fields with defaults.

## Artifacts and Notes

`OpenCodeClient.send_message` signature (already in place, no changes needed):

    async def send_message(self, session_id: str, prompt: str,
                           agent: str | None = None,
                           model: str | None = None) -> MessageResponse: ...

Existing `send_message` side-effects in tests use positional / keyword args without `model`.
The safest fix is to add `model=None` to each mock coroutine's signature, or use `**kwargs`.
Example before:

    async def send_message(session_id, prompt, agent=None):
        ...

After:

    async def send_message(session_id, prompt, agent=None, model=None):
        ...

## Interfaces and Dependencies

In `backend/app/schemas/registry.py`:

    class AgentProfile(_RegistryBase):
        name: str
        description: str
        opencode_agent: str
        default_model: str | None = None
        system_prompt_additions: str = ""

    class AgentStep(_RegistryBase):
        type: Literal["agent"] = "agent"
        agent: str
        description: str = ""
        model: str | None = None   # per-step model override in template definition

    class AgentProfileResponse(_ResponseBase):
        name: str
        description: str
        opencode_agent: str
        default_model: str | None = None

In `backend/app/models.py` (`Step`):

    model: Mapped[str | None] = mapped_column(String(255), nullable=True)

In `backend/app/schemas/pipeline.py`:

    class PipelineCreateRequest(BaseModel):
        template: str
        title: str
        prompt: str
        branch: str | None = None
        step_models: dict[int, str] | None = None

    class StepStatusResponse(BaseModel):
        ...
        model: str | None = None

In `backend/app/services/pipeline_runner.py`:

    async def run_step(self, step, agent_profile, prompt, model: str | None = None) -> ...:
        ...
        self._client.send_message(session_id, prompt=full_prompt,
                                  agent=agent_profile.opencode_agent, model=model)

In `frontend/src/types/api.ts` (Step interface):

    export interface Step {
      ...
      model: string | null
    }
