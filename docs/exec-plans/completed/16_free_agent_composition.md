# Issue #16 — Free Agent Composition

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

Today the only way to create a pipeline is to pick a named template (like `quick_fix` or
`full_feature`). Issue #16 lets users compose a pipeline step-by-step from scratch. In the
New Pipeline modal, users can switch to "Custom" mode, pick individual agents from a list,
reorder them with up/down buttons, insert approval gates, optionally override the model
per step, and submit. The backend accepts these custom steps directly, builds an in-memory
pipeline definition, and runs it exactly like a template-based pipeline.

After this change, a user can create a one-off pipeline with exactly the agents they need
without adding a new YAML template to the repository.

## Progress

- [x] (2026-02-27 12:00Z) Write ExecPlan (this file)
- [x] (2026-02-27 14:00Z) Backend M1: Add CustomStepInput schema + update PipelineCreateRequest (template optional, model_validator)
- [x] (2026-02-27 14:10Z) Backend M1: Update create_pipeline router to handle custom steps; build in-memory PipelineTemplate
- [x] (2026-02-27 14:20Z) Backend M1: Tests pass (red → green) — 7 tests in TestCreatePipelineCustomSteps; 158 total passing
- [x] (2026-02-28 10:20Z) Frontend M2: Add AgentProfileResponse type + fetchAgents() client function
- [x] (2026-02-28 10:20Z) Frontend M2: Add custom_steps to PipelineCreateRequest TS interface (template now optional)
- [x] (2026-02-28 10:25Z) Frontend M2: Add mode toggle (Template | Custom) + custom step builder to NewPipelineModal
- [x] (2026-02-28 10:30Z) Frontend M2: tsc --noEmit passes with 0 errors
- [x] (2026-02-27 15:00Z) ExecPlan finalized: all code-quality fixes applied, 164 tests pass, type-check passes, plan moved to completed/

## Surprises & Discoveries

- Discovery: `APPROVAL_SENTINEL = "__approval__"` is defined in `pipeline_runner.py` and must be imported in `test_pipelines_router.py` to assert on the stored `agent_name` of approval steps. The sentinel is not part of the schema — it's a convention the runner uses to identify approval steps.
  Evidence: `test_custom_steps_creates_correct_step_records` asserts `steps[1].agent_name == APPROVAL_SENTINEL`.

- Discovery: `FastAPI`'s `status.HTTP_422_UNPROCESSABLE_ENTITY` is deprecated in favour of `status.HTTP_422_UNPROCESSABLE_CONTENT`. The new constant was used throughout.
  Evidence: No deprecation warnings in the test run.

- Discovery: The Pydantic `model_validator(mode="after")` on `PipelineCreateRequest` enforces mutual exclusivity at schema-parse time, so the router never needs to check for the "both" or "neither" case explicitly.
  Evidence: `test_neither_template_nor_custom_steps_returns_422` and `test_both_template_and_custom_steps_returns_422` both pass without any router-level guard code for these cases.

- Discovery: An empty `custom_steps: []` list passes Pydantic validation (it satisfies `list[CustomStepInput] | None` and is not `None`), so the router must explicitly check for emptiness and return 422. The schema cannot enforce non-empty lists without a field_validator.
  Evidence: `test_empty_custom_steps_returns_422` passes after adding the explicit router check.

## Decision Log

- Decision: Use up/down buttons for step reordering rather than drag-and-drop. No DnD
  library is currently in the frontend. Per the issue AC both are acceptable, and buttons
  keep the dependency footprint small.
  Date/Author: 2026-02-27 / Josie

- Decision: When template is None and custom_steps is provided, store `pipeline.template`
  as the string `"__custom__"` in the database so the column (which is NOT NULL) has a value
  and existing list views continue to work. The frontend should display `"__custom__"` as
  "Custom" in the UI.
  Date/Author: 2026-02-27 / Josie

- Decision: Validate that all agent names in custom_steps exist in the (effective) registry.
  Return HTTP 422 if any are unknown, same as the behaviour for unknown templates.
  Date/Author: 2026-02-27 / Josie

- Decision: `template` in PipelineCreateRequest becomes Optional (None allowed). Either
  `template` or `custom_steps` must be provided; providing both is an error. Validated via
  a Pydantic model_validator.
  Date/Author: 2026-02-27 / Josie

## Outcomes & Retrospective

Both milestones are complete. Users can now create pipelines in "Custom" mode by picking agents from a dropdown, adding approval gates, reordering steps with up/down buttons, and optionally overriding the model per agent step. The backend validates all agent names against the effective registry and stores the pipeline with `template="__custom__"`. The existing template-based flow is fully preserved.

164 backend tests pass. Frontend type-check passes with 0 errors. No regressions.

## Context and Orientation

`PipelineCreateRequest` (in `backend/app/schemas/pipeline.py`) currently has `template: str`
as a required field. The `create_pipeline` endpoint in `backend/app/routers/pipelines.py`
uses `registry.get_pipeline(body.template)` to resolve the template, and raises 422 if not
found. The `PipelineTemplate` object is then passed to `PipelineRunner`.

`PipelineTemplate` (in `backend/app/schemas/registry.py`) has `name`, `description`, and
`steps: list[PipelineStep]`. `PipelineStep` is a discriminated union of `AgentStep` (has
`agent` and optional `model`) and `ApprovalStep` (has `type="approval"`).

The `AgentRegistry` is available in the endpoint via `Depends(get_registry)`. To check if
an agent name is valid, call `registry.get_agent(name)`.

Key frontend files are at `frontend/src/types/api.ts`, `frontend/src/api/client.ts`, and
`frontend/src/components/NewPipelineModal.tsx`. The modal uses `@tanstack/react-query` for
data fetching and `useCreatePipeline` (a custom mutation hook in
`frontend/src/hooks/useCreatePipeline.ts`) for the POST call.

## Plan of Work

### Milestone 1 — Backend: custom steps schema + router

Add `CustomStepInput` to `backend/app/schemas/pipeline.py` (or `registry.py`; put it in
`pipeline.py` since it is a request schema, not a domain schema):

    class CustomStepInput(BaseModel):
        type: Literal["agent", "approval"] = "agent"
        agent: str | None = None  # required when type="agent"
        model: str | None = None

    # Add model_validator to enforce: type=="agent" requires agent to be non-None.

Update `PipelineCreateRequest`:
- Change `template: str` to `template: str | None = None`
- Add `custom_steps: list[CustomStepInput] | None = None`
- Add a Pydantic model_validator (mode="after") that enforces: exactly one of `template`
  or `custom_steps` must be provided, not both and not neither.

In `create_pipeline` endpoint:

If `body.template` is set, behaviour is unchanged: look up template, raise 422 if not found.

If `body.custom_steps` is set, validate agent names:

    for step in body.custom_steps:
        if step.type == "agent":
            if step.agent is None or effective_registry.get_agent(step.agent) is None:
                raise HTTPException(422, detail=f"Unknown agent: {step.agent!r}")

Then build an in-memory `PipelineTemplate`:

    from app.schemas.registry import AgentStep, ApprovalStep, PipelineTemplate
    steps = []
    for step in body.custom_steps:
        if step.type == "agent":
            steps.append(AgentStep(agent=step.agent, model=step.model))
        else:
            steps.append(ApprovalStep(type="approval"))
    template = PipelineTemplate(name="__custom__", description="", steps=steps)
    template_name = "__custom__"

When storing the Pipeline ORM record, use `template=template_name` (the string).

Write tests in `test_pipelines_router.py` (`TestCreatePipelineCustomSteps` class):
- POST with valid custom_steps returns 201 and creates the correct Step records.
- POST with neither template nor custom_steps returns 422.
- POST with both template and custom_steps returns 422.
- POST with an unknown agent in custom_steps returns 422.
- POST with an approval step in custom_steps creates an APPROVAL_SENTINEL step.
- POST with model override in custom_steps stores the model on the Step record.

### Milestone 2 — Frontend: agent list + custom step builder

In `frontend/src/types/api.ts` add:

    export interface AgentProfileResponse {
      name: string
      description: string
      opencode_agent: string
      default_model: string | null
    }

    export interface CustomStepInput {
      type: 'agent' | 'approval'
      agent?: string
      model?: string
    }

Update `PipelineCreateRequest` interface: change `template: string` to
`template?: string` and add `custom_steps?: CustomStepInput[]`.

In `frontend/src/api/client.ts` add:

    export function fetchAgents(): Promise<AgentProfileResponse[]> {
      return apiFetch<AgentProfileResponse[]>('/registry/agents')
    }

In `NewPipelineModal.tsx`, add a mode toggle at the top of the form: "Template" | "Custom".
Default mode is "Template" (existing behaviour).

In "Custom" mode, show:
- A "Steps" section. Starts empty. Shows an "Add step" row with two buttons: "+ Agent Step"
  (opens an inline agent picker select) and "+ Approval Gate" (adds an approval step directly).
- Each agent step shows: agent name (non-editable label), an optional model input, and up/
  down buttons to reorder, and a remove button.
- Each approval step shows: "Approval Gate" label, up/down buttons, remove button.
- Validation: at least one agent step required (show inline error if not).

On submit in custom mode, build `custom_steps` from the UI state and include it in the
`createPipeline.mutate(...)` call with `template` omitted.

The agent list is fetched via `useQuery` with `queryFn: fetchAgents`. Show a loading state
while agents load.

## Concrete Steps

1. Edit `backend/app/schemas/pipeline.py` — add CustomStepInput, update PipelineCreateRequest
2. Edit `backend/app/routers/pipelines.py` — handle custom steps
3. Write tests in `test_pipelines_router.py` — `TestCreatePipelineCustomSteps`
4. Run `npx nx run backend:test` — verify pass
5. Edit `frontend/src/types/api.ts` — add AgentProfileResponse, CustomStepInput, update request
6. Edit `frontend/src/api/client.ts` — add fetchAgents()
7. Edit `frontend/src/components/NewPipelineModal.tsx` — mode toggle + builder
8. Run `npx nx run frontend:type-check`

## Validation and Acceptance

- `npx nx run backend:test` passes.
- `npx nx run frontend:type-check` passes with no errors.
- POST /pipelines with `{"custom_steps": [{"type": "agent", "agent": "developer"}],
  "title": "Custom Run", "prompt": "Do the thing"}` returns 201 with
  `template == "__custom__"`.
- POST /pipelines with neither `template` nor `custom_steps` returns 422.
- POST /pipelines with both `template` and `custom_steps` returns 422.

## Idempotence and Recovery

All edits are additive. Tests can be re-run safely.

## Interfaces and Dependencies

In `backend/app/schemas/pipeline.py`:

    class CustomStepInput(BaseModel):
        type: Literal["agent", "approval"] = "agent"
        agent: str | None = None
        model: str | None = None

    class PipelineCreateRequest(BaseModel):
        template: str | None = None
        custom_steps: list[CustomStepInput] | None = None
        title: str
        prompt: str
        branch: str | None = None
        step_models: dict[int, str] | None = None
        working_dir: str | None = None
        github_issue_repo: str | None = None    # added by #13
        github_issue_number: int | None = None  # added by #13
