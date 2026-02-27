# Feature: Agent Registry (YAML-based)

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

theAgency orchestrates chains of specialised AI agents. Right now the set of agents and
pipeline shapes is hard-coded nowhere — there is no registry at all. After this feature, a
developer can open two YAML files — `config/agents.yaml` and `config/pipelines.yaml` inside
the `backend/` directory — and define which agents exist, what they do, and how they are
chained together, **without touching Python code or restarting the server**. The dashboard
will show the live list of agents and available pipeline templates. Adding a new agent to the
system becomes a YAML edit, not a deployment.

A developer verifies the feature by running `npx nx run backend:test` (all tests pass),
starting the server with `npx nx run backend:serve`, and hitting `GET /registry/agents` and
`GET /registry/pipelines` to see the loaded configuration returned as JSON. Hot-reload is
verified by editing `agents.yaml` while the server runs — within seconds, the new agent
appears in the API response.

## Progress

- [x] (2026-02-27 14:00Z) ExecPlan drafted
- [x] (2026-02-27 15:00Z) ExecPlan revised: all 9 review findings incorporated (see Decision Log)
- [x] (2026-02-27 16:00Z) Milestone 1: Pydantic schema + AgentRegistry service + YAML configs (TDD) — 11 tests
- [x] (2026-02-27 17:00Z) Milestone 2: Hot-reload via file watcher — 2 tests
- [x] (2026-02-27 17:30Z) Milestone 3: REST router (`/registry/agents`, `/registry/pipelines`) — 4 tests
- [x] (2026-02-27 18:00Z) Milestone 4: Dashboard integration (agents list visible in frontend) — tsc clean
- [x] (2026-02-27 18:30Z) Post-impl code-quality review (round 1): 2 MUST FIX + 5 SHOULD FIX resolved
- [x] (2026-02-27 19:00Z) Post-impl code-quality review (round 2): 2 MUST FIX + 5 SHOULD FIX resolved
- [x] (2026-02-27 19:30Z) ExecPlan finalized: outcomes written, plan moved to completed/

## Surprises & Discoveries

- `model_validate(from_attributes=True)` requires `ConfigDict(from_attributes=True)` on the
  model class — the kwarg alone is not enough for consistent behavior.
- `get_registry` FastAPI dependency belongs in the router module (not services) to keep
  services framework-agnostic per hexagonal architecture.
- `asyncio.to_thread(registry.reload)` is needed in `watch_and_reload` to avoid blocking the
  event loop with synchronous file I/O during hot-reload.
- `app.dependency_overrides[get_registry]` is the proper test pattern instead of directly
  mutating `app.state` — prevents test state leaking.
- Shared test fixtures (VALID_AGENTS, VALID_PIPELINES, write_yaml, make_registry) were
  extracted to `conftest.py` to reduce duplication across test files.
- The `@/` path alias convention documented in `frontend.md` was not actually configured in
  tsconfig — we added it to both `tsconfig.app.json` and `vite.config.ts`.

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
  Rationale: It contains business logic (validation, lookup) and no external I/O beyond
  reading local files. Adapters wrap external services; services contain domain logic.
  Date/Author: 2026-02-27 / Josie

- Decision: YAML config files live in `backend/config/` (a new top-level directory inside
  `backend/`), not inside `app/`. They are deployment artefacts (edited by operators), not
  source code. They are committed to the repo so the app can start without manual setup.
  Date/Author: 2026-02-27 / Josie

- Decision: Frontend milestone (Milestone 4) is limited to a read-only agents list on the
  dashboard — no pipeline template UI yet.
  Rationale: The pipeline template UI belongs with the Pipeline Engine (Issue #1), which
  consumes the registry. Doing more here would block progress on the critical path.
  Date/Author: 2026-02-27 / Josie

- Decision (rev.1): Use `app.state.registry` instead of `@lru_cache` singleton.
  Rationale: `docs/backend.md` says "No global state or singletons." `@lru_cache` on a factory
  is a disguised singleton with mutable internal state — violates the convention. Instead, the
  `AgentRegistry` is created in the FastAPI lifespan and stored on `app.state.registry`. The
  dependency function reads from `request.app.state.registry`. Tests override via
  `app.dependency_overrides` or by setting `app.state.registry` directly.
  Date/Author: 2026-02-27 / Josie

- Decision (rev.1): Extract `watch_and_reload()` as a standalone async function.
  Rationale: The registry is a pure in-memory data container with lookup logic. File-watching
  is an I/O concern. Putting `watch()` on the registry class violates SRP — if the reload
  trigger changes (polling, config API, signal), the registry class must change. A standalone
  function `watch_and_reload(registry, paths, stop_event)` in the same module keeps concerns
  separate. The lifespan starts this function as a background task.
  Date/Author: 2026-02-27 / Josie

- Decision (rev.1): Atomic swap via single `self._config: RegistryConfig` attribute.
  Rationale: `reload()` builds a new `RegistryConfig` object. Only if validation succeeds does
  it assign `self._config = new_config` (single attribute swap). All accessor methods
  (`agents()`, `get_agent()`, etc.) read from `self._config`, so they always see a consistent
  snapshot. In CPython, single attribute assignment is GIL-protected and thus atomic. In asyncio
  (single-threaded event loop), there is no preemption between `await` points, so consistency
  is guaranteed even without the GIL.
  Date/Author: 2026-02-27 / Josie

- Decision (rev.1): Registry models live in `backend/app/schemas/registry.py`.
  Rationale: `docs/backend.md` says "Define in the file where used." These models are used by
  both the service and the router, so they cannot live in either. A dedicated `schemas/`
  package is the conventional Pydantic location. The router response models also live here.
  Date/Author: 2026-02-27 / Josie

- Decision (rev.1): Failed reload keeps old state, logs a structured warning.
  Rationale: A typo in `agents.yaml` should not crash the running server. `reload()` catches
  `Exception`, logs `registry_reload_failed` via structlog with the error details, and leaves
  `self._config` unchanged. The API keeps serving the last-known-good config. This is
  consistent with how uvicorn handles reload errors (keeps old module, logs traceback).
  Date/Author: 2026-02-27 / Josie

- Decision (rev.1): Config paths resolved relative to `backend/` (the CWD).
  Rationale: All NX targets set `cwd: "backend"` (verified in `backend/project.json`). When
  running manually, the developer is in `backend/`. The default values
  `agents_config_path: str = "config/agents.yaml"` resolve relative to this CWD. The plan
  explicitly documents this, and the `AgentRegistry` constructor resolves paths via
  `pathlib.Path(path).resolve()` at init time to make the resolved path unambiguous in logs.
  Date/Author: 2026-02-27 / Josie

- Decision (rev.1): Use `extra="forbid"` on registry models, not `extra="ignore"`.
  Rationale: These models parse our own YAML files, not a third-party API that might add
  fields. Typos in YAML keys (e.g. `decription` instead of `description`) should fail loudly
  at load time, not be silently ignored.
  Date/Author: 2026-02-27 / Josie

- Decision (rev.1): Merge old Milestones 1+2 into a single Milestone 1.
  Rationale: Schema-only without a service produces no observable behavior and cannot be
  meaningfully TDD'd. The smallest testable unit is "load YAML + validate + lookup." The
  revised Milestone 1 includes models, service, YAML files, and all TDD tests for loading and
  lookup. Milestone 2 covers hot-reload separately.
  Date/Author: 2026-02-27 / Josie

## Outcomes & Retrospective

**Delivered:** All 4 milestones complete. 17 new tests (13 service + 4 router), all 44 total
tests passing, lint clean, frontend type-check clean.

**What went well:**
- TDD drove clean separation between schema validation, service logic, and routing.
- `extra="forbid"` on Pydantic models immediately caught YAML typos during development.
- The `watch_and_reload` standalone function pattern kept the registry class focused on
  in-memory state, making it trivially testable without file-watching complexity.
- Two rounds of code-quality review caught real issues: singleton convention gap,
  missing sync I/O documentation, redundant guard clauses, unconfigured path alias.

**What could be better:**
- The ExecPlan was very detailed but some of the specifics (exact field names, test names)
  were determined during TDD anyway. A slightly lighter plan would have been equally effective.
- Settings singleton pattern is a known pre-existing tension with the "no singletons"
  convention. We documented the exception rather than refactoring — acceptable for now but
  should be revisited if more singletons appear.

**Files delivered:**
- `backend/app/schemas/__init__.py`, `backend/app/schemas/registry.py`
- `backend/app/services/agent_registry.py`
- `backend/app/routers/registry.py`
- `backend/config/agents.yaml`, `backend/config/pipelines.yaml`
- `backend/app/tests/conftest.py`, `backend/app/tests/test_agent_registry.py`,
  `backend/app/tests/test_registry_router.py`
- `frontend/src/hooks/useAgents.ts`, `frontend/src/components/AgentList.tsx`
- Modified: `backend/app/main.py`, `backend/app/config/config.py`, `backend/pyproject.toml`,
  `frontend/src/App.tsx`, `frontend/tsconfig.app.json`, `frontend/vite.config.ts`,
  `docs/backend.md`

## Context and Orientation

The repo root is `theAgency/`. The backend is a Python 3.11 / FastAPI application in
`backend/`. All Python commands run inside `backend/` with `uv run`. NX targets can be run
from the repo root: `npx nx run backend:test` runs pytest, `npx nx run backend:lint` runs
ruff. All NX backend targets set `cwd: "backend"` (defined in `backend/project.json`), so
relative paths in configuration are always resolved from `backend/`.

**Hexagonal Architecture**: domain/business logic lives in `backend/app/services/`, external
integrations in `backend/app/adapters/`, thin HTTP wrappers in `backend/app/routers/`, shared
Pydantic schemas in `backend/app/schemas/`. This feature adds a schema module, a service
(`AgentRegistry`), and a router (`/registry/...`). No adapter is needed — reading local YAML
is not an external integration.

**Existing relevant files:**

`backend/app/config/config.py` — the `Settings` class (pydantic-settings). Currently has
`database_url`, `app_version`, `cors_origins`, `opencode_base_port`. We add
`agents_config_path` and `pipelines_config_path` here.

`backend/app/main.py` — the FastAPI app with lifespan context manager. Currently runs Alembic
migrations on startup. We add registry initialization and the file-watcher background task to
the lifespan.

`backend/app/routers/health.py` — example of how a thin router looks: imports a dependency,
defines a response model, returns it.

`backend/app/services/__init__.py` — empty; we add `agent_registry.py` here.

`backend/app/tests/` — existing test files: `test_health.py` (2 tests),
`test_opencode_client.py` (17 tests), `test_opencode_process.py` (8 tests). We add
`test_agent_registry.py` and `test_registry_router.py`.

`backend/pyproject.toml` — Python dependencies. We add `pyyaml` and `watchfiles`.

**OpenCode Custom Agents** (background): OpenCode supports custom agents defined via
`AGENTS.md` or per-session via its API. A "custom agent" in OpenCode's terms is essentially
a named system-prompt override that tells the LLM to take a particular role. In theAgency,
we represent each such agent as a profile in `agents.yaml`. The `opencode_agent` field maps
to the agent name OpenCode knows about (e.g. `"developer"`, `"architect"`). The
`system_prompt_additions` field is extra instruction text that theAgency can inject on top of
the base OpenCode agent prompt when starting a pipeline step.

**pydantic-settings** (already in deps): reads environment variables and `.env` files into a
typed `Settings` object. The `Settings` class in `backend/app/config/config.py` is the single
source of all runtime configuration.

**`watchfiles`** (new dep): a Python library (backed by Rust) that watches file-system paths
for changes and yields change events. It is already used internally by uvicorn for
hot-reload. We use its `awatch` async generator to watch the YAML files in a background
asyncio task. Usage pattern:

    import asyncio
    from watchfiles import awatch

    async def watch_and_reload(registry, paths, stop_event):
        async for changes in awatch(*paths, stop_event=stop_event):
            registry.reload()

`awatch` accepts a `stop_event` parameter (an `asyncio.Event`) and exits cleanly when it is
set. This is how we stop the watcher during FastAPI shutdown.

**`pyyaml`** (new dep): standard YAML parser for Python. `yaml.safe_load(file)` returns a
Python dict. We feed this dict into `RegistryConfig.model_validate()` for Pydantic parsing.

**Prior ExecPlan**: This plan builds upon the completed ExecPlan #2 (OpenCode HTTP Client),
which is checked in at `docs/exec-plans/completed/2_opencode_http_client.md`. That plan
delivered `OpenCodeClient` and `OpenCodeProcessManager` in `backend/app/adapters/`. The
Agent Registry does not directly depend on those adapters, but the Pipeline Engine (Issue #1,
next after this) will consume both the registry and the adapters together.

## Plan of Work

**Milestone 1 — Pydantic schema + AgentRegistry service + YAML configs.**

This milestone delivers the core of the feature: models, service, YAML files, and full TDD
test coverage for loading, validation, and lookup. After this milestone, all service-level
tests pass, but there is no HTTP endpoint yet.

First, create the `backend/app/schemas/` package (add `__init__.py`). Then create
`backend/app/schemas/registry.py` with the Pydantic models. All models inherit from a shared
`_RegistryBase` class that sets `model_config = ConfigDict(extra="forbid")`. This means any
typo in YAML keys (e.g. `decription`) will fail loudly at parse time rather than being
silently ignored.

`AgentProfile` has `name: str`, `description: str`, `opencode_agent: str`, and
`system_prompt_additions: str = ""`. `PipelineStep` has `agent: str` and
`description: str = ""`. `PipelineTemplate` has `name: str`, `description: str`, and
`steps: list[PipelineStep]` (must be non-empty). `RegistryConfig` has
`agents: list[AgentProfile]` and `pipelines: list[PipelineTemplate]`. It carries a
`@model_validator(mode="after")` that checks every step's `agent` field references a name
that exists in the `agents` list. If not, it raises a `ValueError` naming the offending
pipeline and agent.

Next, create the two YAML files under `backend/config/`:

`backend/config/agents.yaml` defines the initial seven agents: `product_owner`, `architect`,
`designer`, `developer`, `senior_reviewer`, `issue_creator`, `qa`. Each has a `name`,
`description`, `opencode_agent` (the OpenCode agent name, e.g. `"product-owner"`), and
`system_prompt_additions` (empty string for now — these will be fleshed out when the Pipeline
Engine is implemented).

`backend/config/pipelines.yaml` defines three initial templates: `full_feature` (all seven
agents in order: product_owner, architect, designer, developer, senior_reviewer, qa,
issue_creator), `quick_fix` (developer, senior_reviewer), and `issue_only` (issue_creator).

Then create `backend/app/services/agent_registry.py`. The `AgentRegistry` class takes
`agents_path: str` and `pipelines_path: str` in its constructor. The constructor resolves
both paths to absolute paths via `pathlib.Path(path).resolve()` and stores them. It then
calls `self.reload()` to perform the initial load.

`reload()` reads both YAML files, feeds the combined dict into
`RegistryConfig.model_validate({"agents": agents_data, "pipelines": pipelines_data})`, and
on success assigns `self._config = new_config`. If any exception occurs (file not found,
YAML parse error, Pydantic validation error), it logs a structured warning via structlog
(`registry_reload_failed`, with the exception message) and leaves `self._config` unchanged.
On initial load (when `self._config` is not yet set), the exception propagates — the server
should not start with invalid config.

Accessor methods: `agents() -> list[AgentProfile]` returns `self._config.agents`.
`pipelines() -> list[PipelineTemplate]` returns `self._config.pipelines`.
`get_agent(name) -> AgentProfile | None` does a linear scan (7 agents — no need for a dict).
`get_pipeline(name) -> PipelineTemplate | None` likewise.

A module-level `get_registry` function (no cache, no decorator) is defined for use as a
FastAPI dependency. It reads from `request.app.state.registry`:

    def get_registry(request: Request) -> AgentRegistry:
        return request.app.state.registry

Add `agents_config_path: str = "config/agents.yaml"` and
`pipelines_config_path: str = "config/pipelines.yaml"` to `Settings` in
`backend/app/config/config.py`.

Write TDD tests in `backend/app/tests/test_agent_registry.py`. Use `tmp_path` (pytest
built-in fixture) to create temp YAML files for each test — no mocking of file I/O. Test
order (one at a time, red/green/refactor):

1. `test_load_valid_config` — write valid agents + pipelines YAML to temp files, construct
   `AgentRegistry`, assert `len(registry.agents()) == N` and `len(registry.pipelines()) == M`.
2. `test_agents_returns_agent_profiles` — load valid config, assert first agent has expected
   `name`, `description`, `opencode_agent`.
3. `test_pipelines_returns_pipeline_templates` — load valid config, assert first pipeline has
   expected `name` and `len(steps)`.
4. `test_get_agent_found` — call `get_agent("developer")`, assert returns `AgentProfile` with
   correct name.
5. `test_get_agent_not_found` — call `get_agent("nonexistent")`, assert returns `None`.
6. `test_get_pipeline_found` — call `get_pipeline("quick_fix")`, assert returns
   `PipelineTemplate`.
7. `test_get_pipeline_not_found` — call `get_pipeline("nonexistent")`, assert returns `None`.
8. `test_validation_fails_on_unknown_step_agent` — write a pipeline referencing agent `"ghost"`,
   assert `AgentRegistry(...)` raises `ValueError`.
9. `test_validation_fails_on_extra_yaml_key` — write YAML with a typo key like `decription`,
   assert constructor raises (Pydantic `extra="forbid"` catches it).
10. `test_reload_picks_up_changes` — construct registry, then overwrite the YAML file with a
    new agent, call `reload()`, assert the new agent appears in `agents()`.
11. `test_reload_keeps_old_state_on_error` — construct registry, then overwrite YAML with
    invalid content, call `reload()`, assert original agents still returned (no crash).

**Milestone 2 — Hot-reload via file watcher.**

This milestone adds the `watch_and_reload` async function and wires it into the FastAPI
lifespan. After this milestone, editing a YAML file while the server runs triggers an
automatic reload visible in the structlog output and in subsequent API calls (once the router
exists in Milestone 3, but we can verify reload via the test).

Create the standalone async function `watch_and_reload` in
`backend/app/services/agent_registry.py` (same module, not a method on the class):

    async def watch_and_reload(
        registry: AgentRegistry,
        paths: list[str],
        stop_event: asyncio.Event,
    ) -> None:

It uses `watchfiles.awatch(*paths, stop_event=stop_event)`. On each change set, it calls
`registry.reload()`. If `awatch` raises (e.g. watched path deleted), it logs and breaks.

Update `backend/app/main.py` lifespan: after migrations, construct the `AgentRegistry` from
`settings.agents_config_path` and `settings.pipelines_config_path`. Store it on
`app.state.registry`. Create a `stop_event = asyncio.Event()`, launch
`watch_and_reload(registry, [...], stop_event)` as a background task via
`asyncio.create_task()`. In the shutdown phase (`yield` → cleanup), set `stop_event` and
cancel the task.

TDD tests (continuing the numbering):

12. `test_watch_and_reload_triggers_on_file_change` — create temp YAML, construct registry,
    run `watch_and_reload` as a task, write a new agent to the file, wait briefly, assert the
    new agent appears. Then set `stop_event` to clean up.
13. `test_watch_and_reload_stops_on_event` — start `watch_and_reload`, immediately set
    `stop_event`, assert the function exits without error.

**Milestone 3 — REST router.**

Create `backend/app/routers/registry.py`. Mount it in `main.py` with
`app.include_router(registry.router)`. Two endpoints:

`GET /registry/agents` returns `list[AgentProfileResponse]`. The response model has `name`,
`description`, `opencode_agent` — deliberately omits `system_prompt_additions` since that is
an internal implementation detail not for dashboard consumers.

`GET /registry/pipelines` returns `list[PipelineTemplateResponse]` with `name`,
`description`, and `steps: list[PipelineStepResponse]` (each step has `agent` and
`description`).

The response models live in `backend/app/schemas/registry.py` alongside the domain models.
Both endpoints use `Annotated[AgentRegistry, Depends(get_registry)]` for dependency
injection.

Add tests in `backend/app/tests/test_registry_router.py` using `httpx.AsyncClient` (same
pattern as `test_health.py`). The tests set up `app.state.registry` with a known test config
before calling the endpoints.

TDD test order:

14. `test_get_agents_returns_200` — hit `GET /registry/agents`, assert status 200 and
    response is a list with the expected number of agents.
15. `test_get_agents_response_shape` — assert each agent object has keys `name`,
    `description`, `opencode_agent` and does NOT have `system_prompt_additions`.
16. `test_get_pipelines_returns_200` — hit `GET /registry/pipelines`, assert status 200 and
    correct count.
17. `test_get_pipelines_response_shape` — assert each pipeline has `name`, `description`,
    `steps`; each step has `agent`, `description`.

**Milestone 4 — Dashboard frontend.**

In the frontend (`frontend/src/`) add an `AgentList` component that fetches
`GET /api/registry/agents` on mount and renders each agent as a card showing `name` and
`description`. The Vite dev server already proxies `/api/*` to `http://localhost:8000`
(configured in `frontend/vite.config.ts`), so the frontend calls `/api/registry/agents` and
Vite strips the `/api` prefix before forwarding.

Wire the component into `App.tsx` below the existing SSE status area. Use `fetch` with
`useEffect` — no external state library needed at this stage. Define a TypeScript interface:

    interface Agent {
      name: string;
      description: string;
      opencode_agent: string;
    }

After this milestone, running `npx nx run frontend:dev` and opening `http://localhost:5173`
shows the agent list cards. `npx nx run frontend:type-check` must pass clean.

## Concrete Steps

All NX commands from the repo root. Manual `uv` commands from `backend/`.

    # Add Python dependencies (run from backend/)
    uv add pyyaml watchfiles

    # Run tests at any point
    npx nx run backend:test

    # Lint
    npx nx run backend:lint

    # Type-check frontend
    npx nx run frontend:type-check

    # Start server for manual verification
    npx nx run backend:serve
    # Then in another terminal:
    curl http://localhost:8000/registry/agents | python3 -m json.tool
    curl http://localhost:8000/registry/pipelines | python3 -m json.tool

## Validation and Acceptance

After all milestones, the following is true:

1. `npx nx run backend:test` passes — total expected: 27 existing + 17 new = 44 tests.
2. `npx nx run backend:lint` exits clean.
3. `npx nx run frontend:type-check` exits clean.
4. Start the server with `npx nx run backend:serve`. Then:
   - `curl http://localhost:8000/registry/agents` returns a JSON array with 7 agent objects.
     Each has `name`, `description`, `opencode_agent`. None has `system_prompt_additions`.
   - `curl http://localhost:8000/registry/pipelines` returns a JSON array with 3 pipeline
     objects. `full_feature` has 7 steps, `quick_fix` has 2, `issue_only` has 1.
5. Hot-reload: edit `backend/config/agents.yaml`, add a dummy agent at the end, and save.
   Within ~2 seconds the server logs show `registry_reloaded`. Hitting `/registry/agents`
   returns 8 agents. Remove the dummy agent and save — back to 7.
6. Hot-reload error handling: break `agents.yaml` syntax (e.g. delete a colon), save. The
   server logs `registry_reload_failed` with the parse error. `/registry/agents` still
   returns the last-known-good 7 agents. Fix the YAML — reload succeeds.
7. `npx nx run frontend:dev`, open `http://localhost:5173` — 7 agent cards visible.

## Idempotence and Recovery

`uv add` is safe to re-run. The YAML files and Pydantic models are new files — no existing
files are modified except `main.py`, `config.py`, and `pyproject.toml`. Tests are idempotent:
they create temp YAML files via `tmp_path` and never touch real config. If YAML validation
fails at startup, the server raises a clear error rather than starting in a broken state. If
YAML validation fails during hot-reload, the old state is preserved.

## Artifacts and Notes

Expected `backend/config/agents.yaml`:

    agents:
      - name: product_owner
        description: >-
          Turns a feature request into a structured requirement document
          with acceptance criteria and scope boundaries.
        opencode_agent: product-owner
        system_prompt_additions: ""
      - name: architect
        description: >-
          Designs the technical solution: module boundaries, data flow,
          API contracts, and integration points.
        opencode_agent: architect
        system_prompt_additions: ""
      - name: designer
        description: >-
          Creates UI/UX specifications and component designs for
          frontend features.
        opencode_agent: designer
        system_prompt_additions: ""
      - name: developer
        description: >-
          Implements the feature according to the architecture and
          design specs, following TDD.
        opencode_agent: developer
        system_prompt_additions: ""
      - name: senior_reviewer
        description: >-
          Reviews the implementation for correctness, code quality,
          and adherence to conventions.
        opencode_agent: senior-reviewer
        system_prompt_additions: ""
      - name: issue_creator
        description: >-
          Creates well-structured GitHub issues from vague feature
          requests or bug reports.
        opencode_agent: issue-creator
        system_prompt_additions: ""
      - name: qa
        description: >-
          Validates the implementation against acceptance criteria,
          runs tests, and verifies edge cases.
        opencode_agent: qa
        system_prompt_additions: ""

Expected `backend/config/pipelines.yaml`:

    pipelines:
      - name: full_feature
        description: >-
          Full pipeline from requirement analysis to QA for a new feature.
          All seven agents run in sequence.
        steps:
          - agent: product_owner
            description: Analyse the feature request and produce a requirements document.
          - agent: architect
            description: Design the technical solution based on requirements.
          - agent: designer
            description: Create UI/UX specifications if the feature has a frontend component.
          - agent: developer
            description: Implement the feature following TDD.
          - agent: senior_reviewer
            description: Review the implementation for quality and correctness.
          - agent: qa
            description: Validate the feature against acceptance criteria.
          - agent: issue_creator
            description: Create follow-up issues for discovered gaps or improvements.
      - name: quick_fix
        description: >-
          Fast path for small bug fixes. Developer implements, reviewer validates.
        steps:
          - agent: developer
            description: Implement the fix.
          - agent: senior_reviewer
            description: Review the fix.
      - name: issue_only
        description: >-
          Create a structured GitHub issue without implementation.
        steps:
          - agent: issue_creator
            description: Analyse the request and create a well-structured GitHub issue.

## Interfaces and Dependencies

New Python deps: `pyyaml>=6.0`, `watchfiles>=1.0`.

New settings in `backend/app/config/config.py`:

    agents_config_path: str = "config/agents.yaml"
    pipelines_config_path: str = "config/pipelines.yaml"

New `backend/app/schemas/` package with `__init__.py` and `registry.py`.

Domain models in `backend/app/schemas/registry.py`:

    from pydantic import BaseModel, ConfigDict, model_validator

    class _RegistryBase(BaseModel):
        model_config = ConfigDict(extra="forbid")

    class AgentProfile(_RegistryBase):
        name: str
        description: str
        opencode_agent: str
        system_prompt_additions: str = ""

    class PipelineStep(_RegistryBase):
        agent: str
        description: str = ""

    class PipelineTemplate(_RegistryBase):
        name: str
        description: str
        steps: list[PipelineStep]

    class RegistryConfig(_RegistryBase):
        agents: list[AgentProfile]
        pipelines: list[PipelineTemplate]

        @model_validator(mode="after")
        def _steps_reference_known_agents(self) -> "RegistryConfig":
            known = {a.name for a in self.agents}
            for pipeline in self.pipelines:
                for step in pipeline.steps:
                    if step.agent not in known:
                        raise ValueError(
                            f"Pipeline '{pipeline.name}' step references "
                            f"unknown agent '{step.agent}'"
                        )
            return self

Response models (same file, below the domain models):

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

Service in `backend/app/services/agent_registry.py`:

    class AgentRegistry:
        def __init__(self, agents_path: str, pipelines_path: str) -> None: ...
        def agents(self) -> list[AgentProfile]: ...
        def pipelines(self) -> list[PipelineTemplate]: ...
        def get_agent(self, name: str) -> AgentProfile | None: ...
        def get_pipeline(self, name: str) -> PipelineTemplate | None: ...
        def reload(self) -> None: ...

    async def watch_and_reload(
        registry: AgentRegistry,
        paths: list[str],
        stop_event: asyncio.Event,
    ) -> None: ...

    def get_registry(request: Request) -> AgentRegistry: ...

New files summary:

    backend/config/agents.yaml
    backend/config/pipelines.yaml
    backend/app/schemas/__init__.py
    backend/app/schemas/registry.py
    backend/app/services/agent_registry.py
    backend/app/routers/registry.py
    backend/app/tests/test_agent_registry.py
    backend/app/tests/test_registry_router.py
    frontend/src/components/AgentList.tsx
