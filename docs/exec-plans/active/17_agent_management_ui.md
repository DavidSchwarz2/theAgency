# Add Agent Management UI (#17)

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

After this change, users can create, edit, and delete agent profiles from the web UI instead of
editing `backend/config/agents.yaml` by hand. An "Agents" page at `/agents` lists all configured
agents. A modal lets users create a new agent or edit an existing one. A delete button (with a
confirmation step) removes an agent. All changes are persisted immediately to `agents.yaml` and
hot-reloaded by the running server — no server restart needed.

## Progress

- [ ] M1: Backend write endpoints (POST/PUT/DELETE for agents) — TDD, all tests green
- [ ] M2: Frontend Agents page with create/edit/delete modals + NavBar link
- [ ] ExecPlan finalized: outcomes written, plan moved to completed location per AGENTS.md.

## Surprises & Discoveries

_(fill in as work proceeds)_

## Decision Log

- Decision: `system_prompt_additions` is included in the write request schemas even though it is
  omitted from `AgentProfileResponse` (read schema). The field is internal but must be settable.
  Rationale: users need a way to supply per-agent system prompt additions via the UI.
  Date/Author: 2026-02-27 / Josie

- Decision: YAML writes use atomic rename (write to `.tmp` file then `os.replace`) so the
  hot-reload file watcher never reads a partial write.
  Rationale: the existing `watch_and_reload` watcher calls `registry.reload()` on any file change;
  a non-atomic write would cause parse errors during the rename window.
  Date/Author: 2026-02-27 / Josie

- Decision: Deletion is blocked (HTTP 409) when an agent name is referenced by any pipeline step.
  Rationale: `RegistryConfig._steps_reference_known_agents` enforces referential integrity on every
  write; we expose this as a user-friendly error rather than a cryptic 422.
  Date/Author: 2026-02-27 / Josie

## Outcomes & Retrospective

_(fill in at completion)_

## Context and Orientation

### What is the AgentRegistry?

`backend/app/services/agent_registry.py` — `AgentRegistry` is an in-memory registry of agent
profiles and pipeline templates. On startup it reads two YAML files:

- `backend/config/agents.yaml` — a dict `{ agents: [...] }` where each item matches `AgentProfile`
- `backend/config/pipelines.yaml` — a dict `{ pipelines: [...] }` where each item matches
  `PipelineTemplate`

It exposes `agents()`, `pipelines()`, `get_agent()`, `get_pipeline()`, and `merge_with_local()`.
The `watch_and_reload` coroutine (called from `main.py` lifespan) watches both files via
`watchfiles.awatch` and calls `registry.reload()` asynchronously whenever either file changes.

The `reload()` method performs blocking I/O. It must never be called directly from async code;
use `asyncio.to_thread(registry.reload)` instead (as `watch_and_reload` already does).

### What is RegistryConfig?

`backend/app/schemas/registry.py` — `RegistryConfig` is a Pydantic model that holds validated
lists of `AgentProfile` and `PipelineTemplate`. Its `@model_validator` `_steps_reference_known_agents`
checks that every `AgentStep.agent` value in any pipeline refers to a known agent name. This validator
fires on every `model_validate` call, so every write must pass through it.

`AgentProfile` fields: `name: str`, `description: str`, `opencode_agent: str`,
`default_model: str | None = None`, `system_prompt_additions: str = ""`.

### Existing read endpoints

`backend/app/routers/registry.py` currently has:

- `GET /registry/agents` → `list[AgentProfileResponse]`
- `GET /registry/pipelines` → `list[PipelineTemplateResponse]`
- `GET /registry/github-issue` → `GitHubIssueResponse`

The `AgentProfileResponse` intentionally omits `system_prompt_additions`. The write request
schemas (defined in this plan) must include it so users can set it via the UI.

### Atomic YAML writes

When writing `agents.yaml`, the pattern is:

1. Load current pipelines from file (or from registry) — needed to run `RegistryConfig` validation
2. Build the new `RegistryConfig` (both agents + pipelines) and call `model_validate` — this runs
   the referential integrity check
3. Serialize agents to YAML: `yaml.dump({"agents": [a.model_dump() for a in new_agents]}, default_flow_style=False)`
4. Write to a temp path (`agents.yaml.tmp`) then `os.replace(tmp, agents.yaml)` — atomic on POSIX
5. `watch_and_reload` picks up the change and calls `registry.reload()` automatically

### How the registry is injected

`app.state.registry` holds the global `AgentRegistry` instance. The dependency `get_registry`
in `registry.py` reads it from `request.app.state`. Write endpoints need both the registry (to
read current state) and the config paths (to write files). The paths are available on the
registry as `registry._agents_path` and `registry._pipelines_path`.

### Test infrastructure

`backend/app/tests/conftest.py` provides `make_registry` — a factory fixture that creates an
`AgentRegistry` from temp YAML files. Fixtures override `get_registry` via
`app.dependency_overrides`. Tests use `AsyncClient(transport=ASGITransport(app=app))`.

The test runner is: `npx nx run backend:test` from the repo root.

### Frontend stack

- Vite + React + TypeScript, path alias `@/` → `src/`
- TanStack Query v5 for all data fetching (hooks in `frontend/src/hooks/`)
- `frontend/src/api/client.ts` contains typed wrappers around `fetch`
- `frontend/src/types/api.ts` contains shared TypeScript interfaces
- `frontend/src/pages/` has page components; `frontend/src/components/` has shared components
- `frontend/src/App.tsx` declares routes with `react-router-dom`
- NavBar is `frontend/src/components/NavBar.tsx` — add `<NavLink to="/agents">` here
- Frontend type-check: `npx nx run frontend:type-check`

## Plan of Work

### M1: Backend write endpoints

Add three new endpoints to `backend/app/routers/registry.py`:

**`POST /registry/agents`** — create an agent. Request body: `AgentCreateRequest` (all
`AgentProfile` fields). Checks that name is not already taken (409 Conflict). Writes updated
agents list to `agents.yaml` atomically. Returns 201 `AgentProfileResponse`.

**`PUT /registry/agents/{name}`** — update an existing agent. Request body: `AgentUpdateRequest`
(same fields as create). Returns 404 if not found. Writes updated agents list to `agents.yaml`
atomically. Returns 200 `AgentProfileResponse`.

**`DELETE /registry/agents/{name}`** — delete an agent. Returns 404 if not found. Returns 409
Conflict if the agent is referenced in any pipeline step (because `RegistryConfig` validation
would fail). Writes updated agents list atomically. Returns 204 No Content.

New request schemas go in `backend/app/schemas/registry.py`:

    class AgentWriteRequest(_RegistryBase):
        name: str
        description: str
        opencode_agent: str
        default_model: str | None = None
        system_prompt_additions: str = ""

This single schema covers both create and update (the name in the path for PUT is authoritative;
the body name is used for create).

The YAML write helper is a module-level function in `registry.py` (or a small helper module):

    def _write_agents_yaml(path: Path, agents: list[AgentProfile]) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        data = {"agents": [a.model_dump() for a in agents]}
        tmp.write_text(yaml.dump(data, default_flow_style=False))
        os.replace(tmp, path)

TDD: write a failing test first, make it pass, then refactor. Tests go in
`backend/app/tests/test_registry_router.py`. Use the existing `make_registry` fixture.
For write-endpoint tests, the fixture's `tmp_path` files are the actual files the registry
holds, so writing through the endpoint changes real files — verify by reading the registry
again or checking the file content.

### M2: Frontend Agents page

**New file: `frontend/src/pages/AgentsPage.tsx`**

Displays a list of agent cards (name, description, opencode_agent, default_model). Each card
has "Edit" and "Delete" buttons. A "New Agent" button at the top opens a create modal.

The page uses TanStack Query: a `useAgents` hook (upgrade the existing raw-fetch version in
`frontend/src/hooks/useAgents.ts` to use `useQuery`) and a new `useAgentMutations` hook that
wraps `useQueryClient` + `useMutation` for create/update/delete.

**`frontend/src/hooks/useAgents.ts`** — replace raw fetch with:

    export function useAgents() {
      return useQuery({ queryKey: ['agents'], queryFn: fetchAgents })
    }

**`frontend/src/api/client.ts`** — add three new functions:

    createAgent(req: AgentWriteRequest): Promise<AgentProfileResponse>
    updateAgent(name: string, req: AgentWriteRequest): Promise<AgentProfileResponse>
    deleteAgent(name: string): Promise<void>

**`frontend/src/types/api.ts`** — add:

    export interface AgentWriteRequest {
      name: string
      description: string
      opencode_agent: string
      default_model: string | null
      system_prompt_additions: string
    }

**Modal**: a single `AgentFormModal` component (in `frontend/src/components/AgentFormModal.tsx`)
used for both create and edit. Props: `agent?: AgentProfileResponse` (undefined = create mode),
`onClose: () => void`. On submit calls `createAgent` or `updateAgent` then invalidates `['agents']`.

**Delete confirmation**: an inline confirmation in the card ("Are you sure?" / "Yes, Delete" /
"Cancel") rather than a separate modal. On confirm calls `deleteAgent` then invalidates `['agents']`.

**NavBar**: add `<NavLink to="/agents">Agents</NavLink>` in `NavBar.tsx`.

**App.tsx**: add `<Route path="/agents" element={<AgentsPage />} />`.

## Concrete Steps

All commands run from the repo root (`/Users/vwqd2w2/code/iandi/theAgency`).

**M1 — Backend:**

    # 1. Run existing tests (should be green before we start)
    npx nx run backend:test

    # 2. Write failing tests in test_registry_router.py, then implement, then run again
    npx nx run backend:test

    # 3. Lint + type-check
    npx nx run backend:lint
    npx nx run backend:type-check

**M2 — Frontend:**

    # After implementing all frontend changes:
    npx nx run frontend:type-check

## Validation and Acceptance

**M1:** Running `npx nx run backend:test` passes. New test class `TestAgentWriteEndpoints` covers:
- POST creates agent, returns 201, file contains new agent
- POST with duplicate name returns 409
- PUT updates agent, returns 200
- PUT with unknown name returns 404
- DELETE removes agent, returns 204
- DELETE with unknown name returns 404
- DELETE agent used in a pipeline returns 409

**M2:** `npx nx run frontend:type-check` exits 0. Visually: navigating to `/agents` shows the
agent list; creating/editing/deleting an agent reflects immediately in the list (TanStack Query
invalidation); the NavBar shows "Agents" link.

## Idempotence and Recovery

YAML writes are atomic (`.tmp` + `os.replace`) so a crash mid-write leaves the original file
intact. The hot-reload watcher picks up the rename automatically. Tests write to `tmp_path` so
no production files are touched during test runs.

## Interfaces and Dependencies

In `backend/app/schemas/registry.py`, add:

    class AgentWriteRequest(_RegistryBase):
        name: str
        description: str
        opencode_agent: str
        default_model: str | None = None
        system_prompt_additions: str = ""

In `backend/app/routers/registry.py`, add (import `os`, `yaml`, `Path`):

    @router.post("/agents", response_model=AgentProfileResponse, status_code=201)
    async def create_agent(body: AgentWriteRequest, registry: ...) -> AgentProfileResponse

    @router.put("/agents/{name}", response_model=AgentProfileResponse)
    async def update_agent(name: str, body: AgentWriteRequest, registry: ...) -> AgentProfileResponse

    @router.delete("/agents/{name}", status_code=204)
    async def delete_agent(name: str, registry: ...) -> None
