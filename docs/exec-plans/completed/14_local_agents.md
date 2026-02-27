# Issue #14 — Local Agents from Working Directory

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

When a user specifies a `working_dir` for a pipeline, the backend scans that directory for
project-local agent definitions at `{working_dir}/.opencode/agents/*.yaml`. Any agents found
there are merged with the global registry: local agents with the same name override the
global ones; new names extend the list. The merged registry is used only for that pipeline
run — the global registry is never mutated.

After this change, a project can ship its own `developer` agent with a custom
`system_prompt_additions` (e.g., project-specific coding style) and that configuration
will be picked up automatically when a pipeline runs against that project's directory.

## Progress

- [x] (2026-02-27 12:00Z) Write ExecPlan (this file)
- [x] (2026-02-27 13:00Z) Backend M1: Add AgentRegistry.from_config() factory classmethod
- [x] (2026-02-27 13:05Z) Backend M1: Add AgentRegistry.merge_with_local() method
- [x] (2026-02-27 13:15Z) Backend M1: Tests pass (red → green) — 6 tests in TestMergeWithLocal
- [x] (2026-02-27 13:20Z) Backend M2: Wire merge_with_local into create_pipeline router; effective_registry used everywhere
- [x] (2026-02-27 13:25Z) Backend M2: Router tests pass — 1 test in TestLocalAgentMerge; 161 total passing
- [x] (2026-02-28 10:30Z) ExecPlan finalized: outcomes written, plan moved to completed/ per AGENTS.md

## Surprises & Discoveries

- Discovery: `RegistryConfig` has a model_validator that enforces referential integrity (every pipeline step agent must exist in the agents list). Using `model_construct` to bypass this validator was necessary when building the merged ephemeral config, since the merged config only adds agents — it does not add new pipeline templates — so the existing pipelines' step agents might not all be present in the local YAML files.
  Evidence: Using `model_validate` instead of `model_construct` would raise a ValidationError when the merged agents list doesn't include all agents referenced by pipeline templates.

- Discovery: `object.__new__` is the cleanest way to instantiate `AgentRegistry` without triggering `__init__` (which requires file paths and loads YAML). This is the established Python pattern for factory classmethods that bypass normal initialisation.
  Evidence: `test_from_config_classmethod_wraps_config` confirms the returned instance has the correct `_config`.

- Discovery: `merge_with_local` returns `self` unchanged when no `.opencode/agents/` directory exists, making it safe to call unconditionally on every pipeline create even when `working_dir` is set but has no local agents.
  Evidence: `test_no_opencode_agents_dir_returns_same_agents` passes.

## Decision Log

- Decision: Return a fresh AgentRegistry instance from merge_with_local() rather than
  mutating the global registry. The fresh instance has no file paths and no file watcher —
  it is ephemeral and used only for one pipeline run.
  Rationale: Immutability is safer for concurrent requests. Each pipeline run gets its own
  view of the registry.
  Date/Author: 2026-02-27 / Josie

- Decision: Local agent YAML files live at `{working_dir}/.opencode/agents/*.yaml`. Each
  file must define a single agent as a YAML document matching the `AgentProfile` schema
  (fields: name, description, opencode_agent, default_model?, system_prompt_additions?).
  Files that fail to parse are logged as warnings and skipped — they do not abort the run.
  Rationale: Graceful degradation. A typo in one local agent file should not kill the
  entire pipeline.
  Date/Author: 2026-02-27 / Josie

- Decision: Skip `RegistryConfig` referential-integrity validation when building the merged
  ephemeral registry. The merged registry contains only agents — there are no inline pipeline
  definitions for local agents. Pipeline steps reference the global agent names and any
  locally-overriding names.
  Rationale: RegistryConfig's model_validator checks that pipeline step agents exist in the
  agent list. Since we are not adding new pipelines — only agents — we must build the merged
  config manually without running the cross-entity validator again (which would fail because
  global pipeline steps might reference global agents that are not present in the local YAML).
  Instead, merge_with_local builds RegistryConfig directly from the merged agent list +
  existing pipelines.
  Date/Author: 2026-02-27 / Josie

## Outcomes & Retrospective

Both milestones are complete. `AgentRegistry` now has `from_config()` and `merge_with_local()`. The `create_pipeline` endpoint computes an effective registry for each request: when `working_dir` is set and contains `.opencode/agents/*.yaml` files, those agents override or extend the global registry for that run only. The global registry is never mutated. 164 backend tests pass. No frontend changes were required for this issue.

## Context and Orientation

`AgentRegistry` (in `backend/app/services/agent_registry.py`) is an in-memory registry loaded
from two YAML files at startup. Its constructor `__init__(agents_path, pipelines_path)` reads
both files and calls `self.reload()`. The loaded data is stored as a `RegistryConfig` Pydantic
model at `self._config`.

`RegistryConfig` (in `backend/app/schemas/registry.py`) contains `agents: list[AgentProfile]`
and `pipelines: list[PipelineTemplate]`. It has a model_validator that checks every AgentStep
in every pipeline references a known agent name.

`AgentProfile` has fields: `name`, `description`, `opencode_agent`, `default_model?`,
`system_prompt_additions`.

The `create_pipeline` endpoint in `backend/app/routers/pipelines.py` currently receives the
global `AgentRegistry` via FastAPI dependency injection (`Depends(get_registry)`). It passes
`registry=registry` to `PipelineRunner`. No changes are needed to `PipelineRunner` itself.

`working_dir` is already a field on `PipelineCreateRequest` and is stored on the `Pipeline`
ORM record. It is available in `create_pipeline` as `body.working_dir`.

All commands run from the repo root. Run tests with `npx nx run backend:test`.

## Plan of Work

### Milestone 1 — AgentRegistry.from_config() and merge_with_local()

Add a class method `AgentRegistry.from_config(config: RegistryConfig) -> AgentRegistry` to
`backend/app/services/agent_registry.py`. This method creates an instance that wraps an
already-constructed `RegistryConfig` without loading any files. It bypasses
`__init__` (which requires file paths) by using `object.__new__` to allocate the instance and
then manually setting `_config`:

    @classmethod
    def from_config(cls, config: RegistryConfig) -> "AgentRegistry":
        instance = object.__new__(cls)
        instance._agents_path = None
        instance._pipelines_path = None
        instance._config = config
        return instance

Add an instance method `merge_with_local(working_dir: str) -> AgentRegistry`:

    def merge_with_local(self, working_dir: str) -> "AgentRegistry":
        ...

This method:
1. Computes `agents_dir = Path(working_dir) / ".opencode" / "agents"`.
2. If `agents_dir` does not exist or is not a directory, returns `self` (no-op merge).
3. Iterates over `*.yaml` files in `agents_dir` (not recursive). For each file:
   a. Loads YAML with `yaml.safe_load`.
   b. Attempts `AgentProfile.model_validate(data)`.
   c. On failure, logs a warning with `exc_info=True` and skips the file.
4. Merges: start with the global agent list. For each local agent, if an agent with the same
   `name` already exists, replace it; otherwise, append it. The result is the merged list.
5. Builds a new `RegistryConfig`:

        merged_config = RegistryConfig.model_construct(
            agents=merged_agents,
            pipelines=self._ensure_loaded().pipelines,
        )

   Use `model_construct` (bypass validators) instead of `model_validate` to avoid triggering
   the cross-entity referential-integrity check (which re-validates that pipeline step agents
   exist — this is already guaranteed by the original config's validation).
6. Returns `AgentRegistry.from_config(merged_config)`.

Write tests in `backend/app/tests/test_agent_registry.py` (new `TestMergeWithLocal` class):
- When working_dir has no `.opencode/agents/` directory, returns a registry with the same
  agents as the original.
- When a local agent YAML defines a new agent, it appears in the merged registry.
- When a local agent YAML overrides a global agent by name, the local version wins.
- When a local YAML is malformed, it is skipped and other agents are still loaded.
- The merge does not mutate the original registry (check original is unchanged after merge).

### Milestone 2 — Wire into create_pipeline

In `backend/app/routers/pipelines.py`, in the `create_pipeline` endpoint, after resolving
the template and before creating the Pipeline ORM object, add:

    effective_registry = registry
    if body.working_dir:
        effective_registry = registry.merge_with_local(body.working_dir)

Then pass `effective_registry` everywhere `registry` is used inside the endpoint (agent
default model lookup and the `PipelineRunner` constructor). The two places are:
- `registry.get_agent(step_def.agent)` for default model resolution — change to
  `effective_registry.get_agent(step_def.agent)`.
- `runner = PipelineRunner(..., registry=registry, ...)` — change to
  `registry=effective_registry`.

Write tests in `test_pipelines_router.py` (new `TestLocalAgentMerge` class):
- POST /pipelines with a working_dir that has a local agent YAML uses the local agent's
  default_model when creating steps. Mock the filesystem using `tmp_path`.

## Concrete Steps

1. Edit `backend/app/services/agent_registry.py` — add `from_config()` and `merge_with_local()`
2. Write tests in `backend/app/tests/test_agent_registry.py` — `TestMergeWithLocal` class
3. Run `npx nx run backend:test` — verify new tests pass
4. Edit `backend/app/routers/pipelines.py` — add effective_registry logic
5. Add tests to `backend/app/tests/test_pipelines_router.py` — `TestLocalAgentMerge`
6. Run `npx nx run backend:test` — verify all pass

## Validation and Acceptance

- `npx nx run backend:test` passes all tests.
- Given `/tmp/myproject/.opencode/agents/custom_dev.yaml` with:

      name: developer
      description: Custom dev with project style
      opencode_agent: developer
      default_model: gpt-4o

  When POST /pipelines is called with `working_dir="/tmp/myproject"` and no `step_models`,
  the steps for the `developer` agent are created with `model="gpt-4o"`.

## Idempotence and Recovery

All steps are additive. Re-running tests is safe. `merge_with_local` never mutates the
global registry — it always returns a new instance.

## Interfaces and Dependencies

In `backend/app/services/agent_registry.py`:

    @classmethod
    def from_config(cls, config: RegistryConfig) -> "AgentRegistry": ...

    def merge_with_local(self, working_dir: str) -> "AgentRegistry": ...
