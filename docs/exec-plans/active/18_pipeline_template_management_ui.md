# Add Pipeline Template Management UI (#18)

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

After this change, users can create, edit, and delete pipeline templates from the web UI instead
of editing `backend/config/pipelines.yaml` by hand. A "Templates" page at `/templates` lists all
configured pipeline templates with their steps. A modal lets users build or edit a template by
adding/removing agent steps and approval steps. A delete button (with confirmation) removes a
template. All changes persist immediately to `pipelines.yaml` and are hot-reloaded by the running
server.

## Progress

- [x] M1: Backend write endpoints (POST/PUT/DELETE for pipelines) — TDD, all tests green
- [x] M2: Frontend Templates page with create/edit/delete + NavBar link
- [x] Code quality review — all MUST FIX and SHOULD FIX items resolved
- [x] ExecPlan finalized: outcomes written, plan moved to completed location per AGENTS.md.

## Surprises & Discoveries

- `PipelineTemplate.model_validate(body.model_dump())` correctly handles the discriminated union
  steps — Pydantic v2 serializes and deserializes them cleanly.
- The `_write_pipelines_yaml` helper was consolidated into `AgentRegistry.save_pipelines()`,
  matching the pattern established for agents.
- `TemplateFormModal` uses a parallel `stepKeys` array of `crypto.randomUUID()` values as stable
  React keys for the step list, avoiding index-key reconciliation bugs on reorder/remove.
- `useTemplates` hook extracted into its own file (`frontend/src/hooks/useTemplates.ts`) with
  both `useTemplates` and `useTemplateMutations`.

## Decision Log

- Decision: The `AgentStepResponse` omits `model` in the read schema, but write request schemas
  must include it because users should be able to set a per-step model override.
  Rationale: The domain `AgentStep` has `model: str | None = None`; the response schema dropped it.
  For write operations we need the full domain schema.
  Date/Author: 2026-02-27 / Josie

- Decision: Pipeline writes validate the full `RegistryConfig` (agents + pipelines) to enforce
  referential integrity before writing.
  Rationale: `RegistryConfig._steps_reference_known_agents` validates that all `AgentStep.agent`
  values reference known agent names. We run this check before any file write.
  Date/Author: 2026-02-27 / Josie

- Decision: Deletion is unconditional — no referential check needed because pipelines do not
  reference each other.
  Rationale: Unlike agents (which are referenced by pipeline steps), pipeline templates are not
  referenced by any other domain object in the current schema.
  Date/Author: 2026-02-27 / Josie

## Outcomes & Retrospective

All milestones complete. 200/200 backend tests pass. Frontend type-check clean.

- `GET/POST/PUT/DELETE /registry/pipelines` fully implemented and tested.
- `/templates` page live with create/edit/delete UI including step editor (add/remove/reorder
  agent and approval steps).
- `AgentRegistry.save_pipelines()` encapsulates file write + reload.
- Total new backend tests: 9 in `TestPipelineWriteEndpoints`.

## Context and Orientation

### What is a PipelineTemplate?

`backend/app/schemas/registry.py` — `PipelineTemplate` is a Pydantic model:

    class PipelineTemplate(_RegistryBase):
        name: str
        description: str
        steps: list[PipelineStep]   # PipelineStep = AgentStep | ApprovalStep (discriminated union)

`AgentStep`: `type: "agent"`, `agent: str`, `description: str = ""`, `model: str | None = None`
`ApprovalStep`: `type: "approval"`, `description: str = ""`

The `@field_validator("steps", mode="before")` on `PipelineTemplate` backfills `type: "agent"` for
legacy step dicts that omit the type field.

### The referential integrity constraint

`RegistryConfig._steps_reference_known_agents` is a `@model_validator(mode="after")` that runs
when `RegistryConfig.model_validate(...)` is called. It checks that every `AgentStep.agent` value
is in the set of known agent names. This means: when writing `pipelines.yaml`, we must also load
the current agents list, combine them into a `RegistryConfig`, and validate before writing.

### Atomic YAML writes

Same pattern as for agents (see ExecPlan #17). When writing pipelines:

1. Load current agents from the registry (in memory — no need to re-read file)
2. Build the new `RegistryConfig` and call `model_validate` — runs the referential integrity check
3. Serialize: `yaml.dump({"pipelines": [p.model_dump() for p in new_pipelines]}, default_flow_style=False)`
4. Write to `.tmp` then `os.replace` to `pipelines.yaml`

`model_dump()` on a `PipelineTemplate` will produce the correct nested dict including discriminated
steps. Pydantic v2 serializes discriminated unions correctly by default.

### Existing infrastructure

The registry, dependency injection, test fixtures, and frontend patterns are described in ExecPlan
#17. The short version: `app.state.registry` holds the registry; `get_registry` is the FastAPI
dependency; `make_registry` is the pytest fixture; `npx nx run backend:test` runs tests.

### YAML write helper pattern

    def _write_pipelines_yaml(path: Path, pipelines: list[PipelineTemplate]) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        data = {"pipelines": [p.model_dump() for p in pipelines]}
        tmp.write_text(yaml.dump(data, default_flow_style=False))
        os.replace(tmp, path)

### Frontend patterns

Same as ExecPlan #17: TanStack Query, `useQuery`/`useMutation`, `apiFetch` wrapper in
`frontend/src/api/client.ts`, types in `frontend/src/types/api.ts`, pages in `frontend/src/pages/`,
NavBar in `frontend/src/components/NavBar.tsx`, routes in `frontend/src/App.tsx`.

Existing `fetchPipelineTemplates()` in `client.ts` already calls `GET /registry/pipelines`.

## Plan of Work

### M1: Backend write endpoints

Add three new endpoints to `backend/app/routers/registry.py`:

**`POST /registry/pipelines`** — create a pipeline template. Request body: `PipelineWriteRequest`.
Checks that name is not already taken (409 Conflict). Validates referential integrity (422 if an
agent step references an unknown agent). Writes updated pipelines list atomically. Returns 201
`PipelineTemplateResponse`.

**`PUT /registry/pipelines/{name}`** — update an existing pipeline template. Request body:
`PipelineWriteRequest`. Returns 404 if not found. Validates referential integrity. Writes
atomically. Returns 200 `PipelineTemplateResponse`.

**`DELETE /registry/pipelines/{name}`** — delete a pipeline template. Returns 404 if not found.
Writes atomically. Returns 204 No Content.

New request schemas in `backend/app/schemas/registry.py`:

    class AgentStepWrite(_RegistryBase):
        type: Literal["agent"] = "agent"
        agent: str
        description: str = ""
        model: str | None = None

    class ApprovalStepWrite(_RegistryBase):
        type: Literal["approval"]
        description: str = ""

    PipelineStepWrite = Annotated[AgentStepWrite | ApprovalStepWrite, Field(discriminator="type")]

    class PipelineWriteRequest(_RegistryBase):
        name: str
        description: str
        steps: list[PipelineStepWrite]

When converting `PipelineWriteRequest` to `PipelineTemplate` for writing, convert each step
to the domain type: `AgentStep(**step.model_dump())` or `ApprovalStep(**step.model_dump())`.

TDD: write failing tests first in `test_registry_router.py`, make them pass, refactor.

### M2: Frontend Templates page

**New file: `frontend/src/pages/TemplatesPage.tsx`**

Displays a list of template cards. Each card shows the template name, description, and steps
(as a numbered list: step type badge + agent name or "approval" + description). Each card has
"Edit" and "Delete" buttons. A "New Template" button opens a create modal.

The page uses TanStack Query. Upgrade the existing `fetchPipelineTemplates` to be used via
`useQuery({ queryKey: ['templates'], queryFn: fetchPipelineTemplates })` in a new hook
`frontend/src/hooks/useTemplates.ts`.

**`frontend/src/api/client.ts`** — add:

    createTemplate(req: PipelineWriteRequest): Promise<PipelineTemplateResponse>
    updateTemplate(name: string, req: PipelineWriteRequest): Promise<PipelineTemplateResponse>
    deleteTemplate(name: string): Promise<void>

**`frontend/src/types/api.ts`** — add:

    export interface AgentStepWrite {
      type: 'agent'
      agent: string
      description: string
      model: string | null
    }

    export interface ApprovalStepWrite {
      type: 'approval'
      description: string
    }

    export type PipelineStepWrite = AgentStepWrite | ApprovalStepWrite

    export interface PipelineWriteRequest {
      name: string
      description: string
      steps: PipelineStepWrite[]
    }

**Modal: `frontend/src/components/TemplateFormModal.tsx`**

Used for both create and edit. Renders a step editor: a list of current steps, each with a
delete button and editable fields (type selector, agent selector for agent steps, description,
model). An "Add agent step" button and "Add approval step" button append to the list. Steps can
be reordered by clicking up/down arrows. The agent selector is populated from `useAgents()`.

**Delete confirmation**: inline "Are you sure? / Yes, Delete / Cancel" within the card.

**NavBar**: add `<NavLink to="/templates">Templates</NavLink>`.

**App.tsx**: add `<Route path="/templates" element={<TemplatesPage />} />`.

## Concrete Steps

All commands run from the repo root (`/Users/vwqd2w2/code/iandi/theAgency`).

**M1 — Backend:**

    # 1. Confirm baseline green
    npx nx run backend:test

    # 2. Write failing tests, implement, confirm green
    npx nx run backend:test
    npx nx run backend:lint
    npx nx run backend:type-check

**M2 — Frontend:**

    npx nx run frontend:type-check

## Validation and Acceptance

**M1:** `npx nx run backend:test` passes. New test class `TestPipelineWriteEndpoints` covers:
- POST creates template, returns 201
- POST with duplicate name returns 409
- POST with unknown agent in step returns 422
- PUT updates template, returns 200
- PUT with unknown name returns 404
- DELETE removes template, returns 204
- DELETE with unknown name returns 404

**M2:** `npx nx run frontend:type-check` exits 0. Visually: navigating to `/templates` shows the
template list with steps; creating/editing/deleting a template reflects immediately; NavBar shows
"Templates" link.

## Interfaces and Dependencies

In `backend/app/schemas/registry.py`, add:

    class AgentStepWrite(_RegistryBase): ...
    class ApprovalStepWrite(_RegistryBase): ...
    PipelineStepWrite = Annotated[AgentStepWrite | ApprovalStepWrite, Field(discriminator="type")]
    class PipelineWriteRequest(_RegistryBase): ...

In `backend/app/routers/registry.py`, add:

    @router.post("/pipelines", response_model=PipelineTemplateResponse, status_code=201)
    async def create_pipeline(...) -> PipelineTemplateResponse

    @router.put("/pipelines/{name}", response_model=PipelineTemplateResponse)
    async def update_pipeline(...) -> PipelineTemplateResponse

    @router.delete("/pipelines/{name}", status_code=204)
    async def delete_pipeline(...) -> None
