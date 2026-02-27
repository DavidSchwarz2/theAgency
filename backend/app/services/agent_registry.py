from __future__ import annotations

import asyncio
from pathlib import Path

import structlog
import yaml
from watchfiles import awatch

from app.schemas.registry import AgentProfile, PipelineTemplate, RegistryConfig

logger = structlog.get_logger(__name__)


class AgentRegistry:
    """In-memory registry of agent profiles and pipeline templates, loaded from YAML."""

    def __init__(self, agents_path: str, pipelines_path: str) -> None:
        self._agents_path = Path(agents_path).resolve()
        self._pipelines_path = Path(pipelines_path).resolve()
        self._config: RegistryConfig | None = None
        self.reload()

    @classmethod
    def from_config(cls, config: RegistryConfig) -> "AgentRegistry":
        """Create an ephemeral AgentRegistry wrapping an already-built RegistryConfig.

        This factory bypasses file I/O and the file-watcher setup. Use it to create
        short-lived per-request registries (e.g. after merging local agents).
        """
        instance = object.__new__(cls)
        instance._agents_path = None
        instance._pipelines_path = None
        instance._config = config
        return instance

    def reload(self) -> None:
        """Reload configuration from YAML files (synchronous I/O).

        **This method performs blocking file I/O and must not be called directly
        from an async context.** Use ``asyncio.to_thread(registry.reload)`` instead
        (as ``watch_and_reload`` does). The only acceptable direct call site is the
        constructor, which runs during startup before the event loop serves requests.

        On initial load (self._config is None), exceptions propagate — the server should not
        start with invalid config. On subsequent reloads, errors are logged and the old config
        is preserved.
        """
        try:
            with open(self._agents_path) as f:
                agents_data = yaml.safe_load(f)
            with open(self._pipelines_path) as f:
                pipelines_data = yaml.safe_load(f)

            new_config = RegistryConfig.model_validate(
                {
                    "agents": agents_data.get("agents", []),
                    "pipelines": pipelines_data.get("pipelines", []),
                }
            )
            self._config = new_config
            logger.info(
                "registry_reloaded",
                agents=len(new_config.agents),
                pipelines=len(new_config.pipelines),
            )
        except Exception:
            if self._config is None:
                raise
            logger.warning("registry_reload_failed", exc_info=True)

    def _ensure_loaded(self) -> RegistryConfig:
        """Return the loaded config or raise if the registry was never successfully loaded."""
        if self._config is None:
            raise RuntimeError("Registry not initialized")
        return self._config

    def agents(self) -> list[AgentProfile]:
        return self._ensure_loaded().agents

    def pipelines(self) -> list[PipelineTemplate]:
        return self._ensure_loaded().pipelines

    def get_agent(self, name: str) -> AgentProfile | None:
        return next((a for a in self.agents() if a.name == name), None)

    def get_pipeline(self, name: str) -> PipelineTemplate | None:
        return next((p for p in self.pipelines() if p.name == name), None)

    def merge_with_local(self, working_dir: str) -> "AgentRegistry":
        """Return a new ephemeral AgentRegistry with local agents merged in.

        Scans ``{working_dir}/.opencode/agents/*.yaml`` for project-local agent definitions.
        Each YAML file must be a single agent document matching the AgentProfile schema.
        Local agents with the same name as a global agent override the global one; new names
        are appended. Malformed files are logged as warnings and skipped.

        The original registry is never mutated. The returned instance has no file paths and
        no file watcher.
        """
        agents_dir = Path(working_dir) / ".opencode" / "agents"
        if not agents_dir.is_dir():
            return self

        local_agents: list[AgentProfile] = []
        for yaml_file in sorted(agents_dir.glob("*.yaml")):
            try:
                with open(yaml_file) as f:
                    data = yaml.safe_load(f)
                agent = AgentProfile.model_validate(data)
                local_agents.append(agent)
            except Exception:
                logger.warning("local_agent_load_failed", path=str(yaml_file), exc_info=True)

        if not local_agents:
            return self

        # Merge: global agents as base, local agents override by name or extend.
        merged: dict[str, AgentProfile] = {a.name: a for a in self.agents()}
        for local_agent in local_agents:
            merged[local_agent.name] = local_agent

        merged_config = RegistryConfig.model_construct(
            agents=list(merged.values()),
            pipelines=self._ensure_loaded().pipelines,
        )
        return AgentRegistry.from_config(merged_config)


async def watch_and_reload(
    registry: AgentRegistry,
    paths: list[str],
    stop_event: asyncio.Event,
) -> None:
    """Watch YAML config files and reload the registry on changes.

    Runs as a background asyncio task. Exits cleanly when stop_event is set.
    """
    try:
        async for _changes in awatch(*paths, stop_event=stop_event):
            logger.info("config_file_changed", paths=paths)
            await asyncio.to_thread(registry.reload)
    except Exception:
        logger.warning("watch_and_reload_error", exc_info=True)
