import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.registry import AgentProfile, AgentStep, ApprovalStep, PipelineTemplate
from app.services.agent_registry import AgentRegistry, watch_and_reload
from app.tests.conftest import APPROVAL_PIPELINES, VALID_AGENTS, VALID_PIPELINES, write_yaml


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


class TestApprovalStepSchema:
    def test_agent_step_parses_with_explicit_type(self) -> None:
        step = AgentStep(type="agent", agent="developer", description="Do it")
        assert step.agent == "developer"
        assert step.type == "agent"

    def test_agent_step_parses_without_explicit_type(self) -> None:
        """type defaults to 'agent' so existing YAML without a type field still works."""
        step = AgentStep(agent="developer")
        assert step.type == "agent"

    def test_approval_step_parses(self) -> None:
        step = ApprovalStep(type="approval", description="Human review")
        assert step.type == "approval"
        assert step.description == "Human review"

    def test_pipeline_step_discriminated_union_agent(self) -> None:
        """PipelineTemplate accepts steps with type='agent'."""
        template = PipelineTemplate(
            name="t",
            description="d",
            steps=[{"type": "agent", "agent": "developer", "description": "step1"}],
        )
        assert isinstance(template.steps[0], AgentStep)

    def test_pipeline_step_discriminated_union_approval(self) -> None:
        """PipelineTemplate accepts steps with type='approval'."""
        template = PipelineTemplate(
            name="t",
            description="d",
            steps=[{"type": "approval", "description": "Review me"}],
        )
        assert isinstance(template.steps[0], ApprovalStep)

    def test_pipeline_step_default_type_is_agent(self) -> None:
        """Steps without a type field default to AgentStep (backwards-compatible)."""
        template = PipelineTemplate(
            name="t",
            description="d",
            steps=[{"agent": "developer", "description": "step1"}],
        )
        assert isinstance(template.steps[0], AgentStep)

    def test_approval_step_does_not_require_agent_in_registry(self, tmp_path: Path) -> None:
        """A pipeline with an approval step passes registry validation without an 'approval' agent."""
        agents_path = tmp_path / "agents.yaml"
        pipelines_path = tmp_path / "pipelines.yaml"
        write_yaml(agents_path, VALID_AGENTS)
        write_yaml(pipelines_path, APPROVAL_PIPELINES)
        registry = AgentRegistry(agents_path=str(agents_path), pipelines_path=str(pipelines_path))
        pipeline = registry.get_pipeline("approval_flow")
        assert pipeline is not None
        assert len(pipeline.steps) == 3
        assert isinstance(pipeline.steps[1], ApprovalStep)


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
