from pathlib import Path

import pytest
import yaml

from app.services.agent_registry import AgentRegistry

VALID_AGENTS = {
    "agents": [
        {
            "name": "developer",
            "description": "Implements features.",
            "opencode_agent": "developer",
            "system_prompt_additions": "",
        },
        {
            "name": "reviewer",
            "description": "Reviews code.",
            "opencode_agent": "senior-reviewer",
            "system_prompt_additions": "",
        },
    ]
}

VALID_PIPELINES = {
    "pipelines": [
        {
            "name": "quick_fix",
            "description": "Fast path for small fixes.",
            "steps": [
                {"agent": "developer", "description": "Implement the fix."},
                {"agent": "reviewer", "description": "Review the fix."},
            ],
        }
    ]
}


def write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.dump(data, default_flow_style=False))


@pytest.fixture
def make_registry(tmp_path: Path):
    """Create an AgentRegistry from valid YAML in a temp directory."""

    def _factory(
        agents: dict | None = None,
        pipelines: dict | None = None,
    ) -> AgentRegistry:
        agents_path = tmp_path / "agents.yaml"
        pipelines_path = tmp_path / "pipelines.yaml"
        write_yaml(agents_path, agents or VALID_AGENTS)
        write_yaml(pipelines_path, pipelines or VALID_PIPELINES)
        return AgentRegistry(agents_path=str(agents_path), pipelines_path=str(pipelines_path))

    return _factory
