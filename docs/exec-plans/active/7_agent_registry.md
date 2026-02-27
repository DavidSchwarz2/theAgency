# Feature: Agent Registry (YAML-based)

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

theAgency orchestrates chains of specialised AI agents. Right now the set of agents and
pipeline shapes is hard-coded. After this feature, a developer can open two YAML files —
`config/agents.yaml` and `config/pipelines.yaml` — and immediately change which agents exist,
what they do, and how they are chained together, **without touching Python code or restarting
the server**. The dashboard will show the live list of agents and available pipeline templates.
Adding a new agent to the system becomes a YAML edit, not a deployment.

A developer verifies the feature by running `nx run backend:test` (all tests pass), starting
the server with `nx run backend:serve`, and hitting `GET /registry/agents` and
`GET /registry/pipelines` to see the loaded configuration returned as JSON.

## Progress

- [x] (2026-02-27 14:00Z) ExecPlan drafted
- [ ] Milestone 1: YAML config files + Pydantic schema (no service, no router)
- [ ] Milestone 2: AgentRegistry service (load, validate, hot-reload)
- [ ] Milestone 3: REST router (`/registry/agents`, `/registry/pipelines`)
- [ ] Milestone 4: Dashboard integration (agents list visible in frontend)
- [ ] Post-impl code-quality review
- [ ] ExecPlan finalized: outcomes written, plan moved to completed/

## Surprises & Discoveries

_nothing yet_

## Decision Log

- Decision: Two separate YAML files (`agents.yaml` and `pipelines.yaml`) rather than one.
  Rationale: Agents and pipeline templates are owned by different roles (agent authors vs.
  pipeline designers). Keeping them separate avoids merge conflicts and keeps each file focused.
  Date/Author: 2026-02-27 / Josie

- Decision: Hot-reload via `watchfiles` (file-system watcher), triggered on YAML change.
  Rationale: Issue #7 explicitly requires "new agents can be loaded without restart". A
  background asyncio task watches the YAML files and reloads the registry on change.
  `watchfiles` is a lightweight async-compatible watcher used by uvicorn itself.
  Date/Author: 2026-02-27 / Josie

- Decision: AgentRegistry lives in `backend/app/services/`, not `adapters/`.
  Rationale: It contains business logic (validation, merging, selection) and no external I/O
  beyond reading local files. Adapters wrap external services; services contain domain logic.
  Date/Author: 2026-02-27 / Josie

- Decision: YAML config files live in `backend/config/` (a new top-level directory inside
  `backend/`), not inside `app/`. They are deployment artefacts (edited by operators), not
  source code. They are committed to the repo so the app can start without manual setup.
  Date/Author: 2026-02-27 / Josie

- Decision: The registry is exposed as a FastAPI dependency (singleton via `lru_cache`) rather
  than a global variable.
  Rationale: Avoids module-level state that is hard to test. Tests can override the dependency
  to inject a registry loaded from a temp file.
  Date/Author: 2026-02-27 / Josie

- Decision: Frontend milestone (Milestone 4) is limited to a read-only agents list on the
  dashboard — no pipeline template UI yet.
  Rationale: The pipeline template UI belongs with the Pipeline Engine (Issue #1), which
  consumes the registry. Doing more here would block progress on the critical path.
  Date/Author: 2026-02-27 / Josie

## Outcomes & Retrospective

_to be filled after completion_

## Context and Orientation

The repo root is `theAgency/`. The backend is a Python 3.11 / FastAPI application in
`backend/`. All Python commands run inside `backend/` with `uv run`. NX targets can be run
from the repo root: `npx nx run backend:test` runs pytest, `npx nx run backend:lint` runs ruff.

**Hexagonal Architecture**: domain/business logic lives in `backend/app/services/`, external
integrations in `backend/app/adapters/`, thin HTTP wrappers in `backend/app/routers/`. This
feature adds a service (`AgentRegistry`) and a router (`/registry/...`). No adapter is needed
— reading local YAML is not an external integration.

**Existing relevant files:**

- `backend/app/config/config.py` — `Settings` (pydantic-settings); we add
  `agents_config_path` and `pipelines_config_path` pointing to the new YAML files.
- `backend/app/main.py` — FastAPI app with lifespan. We mount the new router and start the
  file-watcher task in the lifespan context.
- `backend/app/routers/health.py` — example of how a thin router looks.
- `backend/app/services/__init__.py` — empty; we add `agent_registry.py` here.
- `backend/app/tests/` — TDD tests; we add `test_agent_registry.py`.
- `backend/pyproject.toml` — Python dependencies; we add `pyyaml` and `watchfiles`.

**OpenCode Custom Agents** (background): OpenCode supports custom agents defined via
`AGENTS.md` or per-session via its API. A "custom agent" in OpenCode's terms is essentially a
named system-prompt override that tells the LLM to take a particular role. In theAgency, we
represent each such agent as a profile in `agents.yaml`. The `opencode_agent` field maps to
the agent name OpenCode knows about (e.g. `"developer"`, `"architect"`). The
`system_prompt_additions` field is extra instruction text that theAgency can inject on top of
the base OpenCode agent prompt when starting a session step.

**pydantic-settings** (already in deps): reads environment variables and `.env` files into a
typed `Settings` object. The `Settings` class in `backend/app/config/config.py` is the single
source of all runtime configuration.

**`watchfiles`** (new dep): a Python library (backed by Rust) that watches file-system paths
for changes and yields change events. It is already used internally by uvicorn for hot-reload.
We use its `awatch` async generator to watch the YAML files in a background asyncio task.

## Plan of Work

**Milestone 1 — YAML files and Pydantic schema.**

Create two YAML files under `backend/config/`:

`backend/config/agents.yaml` defines all available agents. Each agent has a `name` (machine
identifier, snake_case), a human-readable `description`, an `opencode_agent` string (the agent
name to pass in the `agent` field of the OpenCode `POST /session/:id/message` API), and an
optional `system_prompt_additions` multiline string. The initial set is: `product_owner`,
`architect`, `designer`, `developer`, `senior_reviewer`, `issue_creator`, `qa`.

`backend/config/pipelines.yaml` defines pipeline templates. Each template has a `name`, a
`description`, and a `steps` list. Each step has an `agent` (must match a name from
`agents.yaml`) and an optional `description` string explaining what this step does in context.
The initial templates are: `full_feature` (all seven agents in sequence), `quick_fix`
(developer → senior_reviewer), `issue_only` (issue_creator alone).

Create Pydantic models in `backend/app/services/registry_models.py`:

`AgentProfile` holds `name: str`, `description: str`, `opencode_agent: str`, and
`system_prompt_additions: str = ""`. `PipelineStep` holds `agent: str` and
`description: str = ""`. `PipelineTemplate` holds `name: str`, `description: str`, and
`steps: list[PipelineStep]`. `RegistryConfig` holds `agents: list[AgentProfile]` and
`pipelines: list[PipelineTemplate]` and carries a validator that asserts every step agent
name references a known agent name.

There is no service or router in this milestone — just the YAML files and the schema. We
validate the YAML files are parse-correct by loading them in a small smoke test.

**Milestone 2 — AgentRegistry service.**

Create `backend/app/services/agent_registry.py`. `AgentRegistry` is a class that:

1. Loads `agents.yaml` and `pipelines.yaml` from paths it receives at construction time,
   validates them against `RegistryConfig`, and stores the result.
2. Exposes `agents() -> list[AgentProfile]`, `pipelines() -> list[PipelineTemplate]`,
   `get_agent(name: str) -> AgentProfile | None`, and
   `get_pipeline(name: str) -> PipelineTemplate | None`.
3. Exposes `reload() -> None` which re-reads and re-validates both YAML files in-place (atomic
   swap: only if validation succeeds does the live state change). This is what the file watcher
   calls.
4. Exposes an async `watch(stop_event: asyncio.Event) -> None` method that uses `watchfiles.awatch`
   to monitor both YAML files and calls `reload()` on any change. The loop exits when
   `stop_event` is set. This is started as a background task in the FastAPI lifespan.

`get_registry()` is a module-level function decorated with `@lru_cache(maxsize=1)` that
constructs an `AgentRegistry` from `Settings`. It is used as a FastAPI dependency. Tests
override it via `app.dependency_overrides`.

Write TDD tests in `backend/app/tests/test_agent_registry.py` covering: loading valid YAML,
validation failure on unknown step agent, `get_agent` hit/miss, `get_pipeline` hit/miss,
`reload()` picks up changes written to a temp file, cross-referencing step agents against
declared agents.

**Milestone 3 — REST router.**

Create `backend/app/routers/registry.py`. Mount it in `main.py` with prefix `/registry`. Two
endpoints:

`GET /registry/agents` returns `list[AgentProfileResponse]` — a Pydantic response model with
`name`, `description`, `opencode_agent` (deliberately omits `system_prompt_additions` since
that is an internal implementation detail not for external consumers).

`GET /registry/pipelines` returns `list[PipelineTemplateResponse]` with `name`, `description`,
and `steps: list[PipelineStepResponse]` (each step has `agent` and `description`).

Both endpoints use `Annotated[AgentRegistry, Depends(get_registry)]` for dependency injection.

Add tests in `backend/app/tests/test_registry_router.py` using FastAPI's `AsyncClient` +
`httpx` (same pattern as `test_health.py`) verifying that the endpoints return HTTP 200 and
the correct JSON shapes.

**Milestone 4 — Dashboard frontend.**

In the frontend (`frontend/src/`) add an `AgentList` component that fetches `GET /api/registry/agents`
on mount and renders each agent as a card showing `name` and `description`. Wire it into
`App.tsx` below the existing SSE status area. Use `fetch` with `useEffect` (no external state
library needed at this stage). TypeScript type: `interface Agent { name: string; description: string; opencode_agent: string; }`.

After this milestone, running `nx run frontend:dev` and opening `http://localhost:5173` shows
the agent list cards. `tsc --noEmit` must pass clean.

## Concrete Steps

All commands from the repo root unless stated otherwise. Run `npx nx run backend:test` at the
end of each milestone.

    # Add Python dependencies (run from backend/)
    uv add pyyaml watchfiles

    # Confirm new deps appear in pyproject.toml
    grep -E "pyyaml|watchfiles" pyproject.toml

    # Run tests at any point
    npx nx run backend:test

    # Lint
    npx nx run backend:lint

    # Type-check frontend
    npx nx run frontend:type-check

## Validation and Acceptance

After all milestones, the following is true:

1. `npx nx run backend:test` passes — total expected: 27 existing + ~12 new = ~39 tests.
2. `npx nx run backend:lint` exits clean.
3. `npx nx run frontend:type-check` exits clean.
4. Start the server: from `backend/`, run `uv run uvicorn app.main:app --reload`. Then:
   - `curl http://localhost:8000/registry/agents` returns a JSON array with 7 agent objects.
   - `curl http://localhost:8000/registry/pipelines` returns a JSON array with 3 pipeline objects.
5. Edit `backend/config/agents.yaml` to add a dummy agent and save. Within ~2 seconds the
   server logs show `registry_reloaded`; hitting `/registry/agents` returns the new agent.
6. `npx nx run frontend:dev`, open `http://localhost:5173` — 7 agent cards visible.

## Idempotence and Recovery

`uv add` is safe to re-run. The YAML files and Pydantic models are new files — no existing
files are modified except `main.py`, `config.py`, and `pyproject.toml`. Tests are idempotent
(no persistent state). If YAML validation fails at startup the server raises a clear error
rather than starting in a broken state.

## Artifacts and Notes

Expected `backend/config/agents.yaml` shape (abbreviated):

    agents:
      - name: product_owner
        description: Turns a feature request into a structured requirement document.
        opencode_agent: product-owner
        system_prompt_additions: ""
      - name: developer
        description: Implements the feature according to the architecture spec.
        opencode_agent: developer
        system_prompt_additions: ""
      # ... 5 more agents

Expected `backend/config/pipelines.yaml` shape:

    pipelines:
      - name: full_feature
        description: Full pipeline from requirement to QA for a new feature.
        steps:
          - agent: product_owner
            description: Define requirements
          - agent: architect
            description: Design solution
          # ... 5 more steps
      - name: quick_fix
        description: Fast path for small bug fixes.
        steps:
          - agent: developer
            description: Implement fix
          - agent: senior_reviewer
            description: Review fix

## Interfaces and Dependencies

New Python deps: `pyyaml>=6.0`, `watchfiles>=0.21`.

New setting additions in `backend/app/config/config.py`:

    agents_config_path: str = "config/agents.yaml"
    pipelines_config_path: str = "config/pipelines.yaml"

New files:

    backend/config/agents.yaml
    backend/config/pipelines.yaml
    backend/app/services/registry_models.py
    backend/app/services/agent_registry.py
    backend/app/routers/registry.py
    backend/app/tests/test_agent_registry.py
    backend/app/tests/test_registry_router.py
    frontend/src/components/AgentList.tsx

Key types in `backend/app/services/registry_models.py`:

    class AgentProfile(_Base):
        name: str
        description: str
        opencode_agent: str
        system_prompt_additions: str = ""

    class PipelineStep(_Base):
        agent: str
        description: str = ""

    class PipelineTemplate(_Base):
        name: str
        description: str
        steps: list[PipelineStep]

    class RegistryConfig(_Base):
        agents: list[AgentProfile]
        pipelines: list[PipelineTemplate]

        @model_validator(mode="after")
        def _steps_reference_known_agents(self) -> "RegistryConfig":
            known = {a.name for a in self.agents}
            for pipeline in self.pipelines:
                for step in pipeline.steps:
                    if step.agent not in known:
                        raise ValueError(
                            f"Pipeline '{pipeline.name}' step references unknown agent '{step.agent}'"
                        )
            return self

Key types in `backend/app/services/agent_registry.py`:

    class AgentRegistry:
        def __init__(self, agents_path: str, pipelines_path: str) -> None: ...
        def agents(self) -> list[AgentProfile]: ...
        def pipelines(self) -> list[PipelineTemplate]: ...
        def get_agent(self, name: str) -> AgentProfile | None: ...
        def get_pipeline(self, name: str) -> PipelineTemplate | None: ...
        def reload(self) -> None: ...
        async def watch(self, stop_event: asyncio.Event) -> None: ...

    @lru_cache(maxsize=1)
    def get_registry() -> AgentRegistry: ...

Router response types in `backend/app/routers/registry.py`:

    class AgentProfileResponse(BaseModel):
        name: str
        description: str
        opencode_agent: str

    class PipelineStepResponse(BaseModel):
        agent: str
        description: str

    class PipelineTemplateResponse(BaseModel):
        name: str
        description: str
        steps: list[PipelineStepResponse]
