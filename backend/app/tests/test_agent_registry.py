import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.registry import AgentProfile, PipelineTemplate
from app.services.agent_registry import AgentRegistry, watch_and_reload
from app.tests.conftest import VALID_AGENTS, VALID_PIPELINES, write_yaml


class TestAgentRegistryLoad:
    def test_load_valid_config(self, make_registry) -> None:
        registry = make_registry()
        assert len(registry.agents()) == 2
        assert len(registry.pipelines()) == 1

    def test_agents_returns_agent_profiles(self, make_registry) -> None:
        registry = make_registry()
        agent = registry.agents()[0]
        assert isinstance(agent, AgentProfile)
        assert agent.name == "developer"
        assert agent.description == "Implements features."
        assert agent.opencode_agent == "developer"

    def test_pipelines_returns_pipeline_templates(self, make_registry) -> None:
        registry = make_registry()
        pipeline = registry.pipelines()[0]
        assert isinstance(pipeline, PipelineTemplate)
        assert pipeline.name == "quick_fix"
        assert len(pipeline.steps) == 2


class TestAgentRegistryLookup:
    def test_get_agent_found(self, make_registry) -> None:
        registry = make_registry()
        agent = registry.get_agent("developer")
        assert agent is not None
        assert agent.name == "developer"

    def test_get_agent_not_found(self, make_registry) -> None:
        registry = make_registry()
        assert registry.get_agent("nonexistent") is None

    def test_get_pipeline_found(self, make_registry) -> None:
        registry = make_registry()
        pipeline = registry.get_pipeline("quick_fix")
        assert pipeline is not None
        assert pipeline.name == "quick_fix"

    def test_get_pipeline_not_found(self, make_registry) -> None:
        registry = make_registry()
        assert registry.get_pipeline("nonexistent") is None


class TestAgentRegistryValidation:
    def test_validation_fails_on_unknown_step_agent(self, tmp_path: Path) -> None:
        agents_path = tmp_path / "agents.yaml"
        pipelines_path = tmp_path / "pipelines.yaml"
        write_yaml(agents_path, VALID_AGENTS)
        write_yaml(
            pipelines_path,
            {
                "pipelines": [
                    {
                        "name": "broken",
                        "description": "References ghost agent.",
                        "steps": [{"agent": "ghost", "description": "Spooky."}],
                    }
                ]
            },
        )
        with pytest.raises(ValueError, match="unknown agent 'ghost'"):
            AgentRegistry(agents_path=str(agents_path), pipelines_path=str(pipelines_path))

    def test_validation_fails_on_extra_yaml_key(self, tmp_path: Path) -> None:
        agents_path = tmp_path / "agents.yaml"
        pipelines_path = tmp_path / "pipelines.yaml"
        write_yaml(
            agents_path,
            {
                "agents": [
                    {
                        "name": "developer",
                        "decription": "Typo key!",  # <-- typo
                        "opencode_agent": "developer",
                    }
                ]
            },
        )
        write_yaml(pipelines_path, VALID_PIPELINES)
        with pytest.raises(ValidationError, match="decription"):
            AgentRegistry(agents_path=str(agents_path), pipelines_path=str(pipelines_path))


class TestAgentRegistryReload:
    def test_reload_picks_up_changes(self, tmp_path: Path) -> None:
        agents_path = tmp_path / "agents.yaml"
        pipelines_path = tmp_path / "pipelines.yaml"
        write_yaml(agents_path, VALID_AGENTS)
        write_yaml(pipelines_path, VALID_PIPELINES)
        registry = AgentRegistry(agents_path=str(agents_path), pipelines_path=str(pipelines_path))
        assert len(registry.agents()) == 2

        # Add a third agent
        updated_agents = {
            "agents": [
                *VALID_AGENTS["agents"],
                {
                    "name": "qa",
                    "description": "Runs QA checks.",
                    "opencode_agent": "qa",
                    "system_prompt_additions": "",
                },
            ]
        }
        write_yaml(agents_path, updated_agents)
        registry.reload()
        assert len(registry.agents()) == 3
        assert registry.get_agent("qa") is not None

    def test_reload_keeps_old_state_on_error(self, tmp_path: Path) -> None:
        agents_path = tmp_path / "agents.yaml"
        pipelines_path = tmp_path / "pipelines.yaml"
        write_yaml(agents_path, VALID_AGENTS)
        write_yaml(pipelines_path, VALID_PIPELINES)
        registry = AgentRegistry(agents_path=str(agents_path), pipelines_path=str(pipelines_path))
        assert len(registry.agents()) == 2

        # Break the YAML — invalid content
        agents_path.write_text("agents:\n  - this_is: broken\n")
        registry.reload()

        # Old state preserved
        assert len(registry.agents()) == 2
        assert registry.get_agent("developer") is not None


class TestWatchAndReload:
    async def test_watch_and_reload_triggers_on_file_change(self, tmp_path: Path) -> None:
        agents_path = tmp_path / "agents.yaml"
        pipelines_path = tmp_path / "pipelines.yaml"
        write_yaml(agents_path, VALID_AGENTS)
        write_yaml(pipelines_path, VALID_PIPELINES)
        registry = AgentRegistry(agents_path=str(agents_path), pipelines_path=str(pipelines_path))
        assert len(registry.agents()) == 2

        stop_event = asyncio.Event()
        task = asyncio.create_task(watch_and_reload(registry, [str(agents_path), str(pipelines_path)], stop_event))

        # Give the watcher time to start
        await asyncio.sleep(0.3)

        # Add a new agent to the YAML
        updated_agents = {
            "agents": [
                *VALID_AGENTS["agents"],
                {
                    "name": "qa",
                    "description": "QA agent.",
                    "opencode_agent": "qa",
                    "system_prompt_additions": "",
                },
            ]
        }
        write_yaml(agents_path, updated_agents)

        # Wait for the watcher to pick up the change
        await asyncio.sleep(1.0)

        assert len(registry.agents()) == 3
        assert registry.get_agent("qa") is not None

        stop_event.set()
        await asyncio.wait_for(task, timeout=3.0)

    async def test_watch_and_reload_stops_on_event(self, tmp_path: Path) -> None:
        agents_path = tmp_path / "agents.yaml"
        pipelines_path = tmp_path / "pipelines.yaml"
        write_yaml(agents_path, VALID_AGENTS)
        write_yaml(pipelines_path, VALID_PIPELINES)
        registry = AgentRegistry(agents_path=str(agents_path), pipelines_path=str(pipelines_path))

        stop_event = asyncio.Event()
        task = asyncio.create_task(watch_and_reload(registry, [str(agents_path), str(pipelines_path)], stop_event))

        # Immediately signal stop
        stop_event.set()
        await asyncio.wait_for(task, timeout=3.0)

        # Should exit cleanly without errors
        assert task.done()
        assert task.exception() is None
