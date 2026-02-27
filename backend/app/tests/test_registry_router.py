import pytest
import respx
import httpx
import yaml
from httpx import ASGITransport, AsyncClient

from app.adapters.github_client import GitHubClient
from app.main import app
from app.routers.registry import get_registry


@pytest.fixture
async def client(make_registry):
    """Create test client with a registry injected via dependency override."""
    registry = make_registry()
    app.dependency_overrides[get_registry] = lambda: registry
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def client_with_github(make_registry):
    """Test client that also sets up a GitHubClient on app.state."""
    registry = make_registry()
    app.dependency_overrides[get_registry] = lambda: registry
    github_client = GitHubClient(token="test-token")
    app.state.github_client = github_client
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
        app.state.github_client = None
        await github_client.close()


@pytest.fixture
async def client_no_github(make_registry):
    """Test client without a GitHubClient (token not configured)."""
    registry = make_registry()
    app.dependency_overrides[get_registry] = lambda: registry
    app.state.github_client = None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


class TestRegistryRouterAgents:
    async def test_get_agents_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/registry/agents")
        assert response.status_code == 200
        agents = response.json()
        assert len(agents) == 2

    async def test_get_agents_response_shape(self, client: AsyncClient) -> None:
        response = await client.get("/registry/agents")
        agent = response.json()[0]
        assert "name" in agent
        assert "description" in agent
        assert "opencode_agent" in agent
        assert "system_prompt_additions" not in agent


class TestRegistryRouterPipelines:
    async def test_get_pipelines_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/registry/pipelines")
        assert response.status_code == 200
        pipelines = response.json()
        assert len(pipelines) == 1

    async def test_get_pipelines_response_shape(self, client: AsyncClient) -> None:
        response = await client.get("/registry/pipelines")
        pipeline = response.json()[0]
        assert "name" in pipeline
        assert "description" in pipeline
        assert "steps" in pipeline
        step = pipeline["steps"][0]
        assert "agent" in step
        assert "description" in step


class TestRegistryRouterGitHubIssue:
    @respx.mock
    async def test_get_github_issue_returns_200(self, client_with_github: AsyncClient) -> None:
        """GET /registry/github-issue returns 200 with issue data when token is configured."""
        respx.get("https://api.github.com/repos/owner/repo/issues/42").mock(
            return_value=httpx.Response(
                200,
                json={
                    "number": 42,
                    "title": "Test Issue",
                    "body": "This is the body",
                    "labels": [{"name": "bug"}, {"name": "enhancement"}],
                },
            )
        )
        response = await client_with_github.get("/registry/github-issue?repo=owner/repo&number=42")
        assert response.status_code == 200
        data = response.json()
        assert data["number"] == 42
        assert data["title"] == "Test Issue"
        assert data["body"] == "This is the body"
        assert data["labels"] == ["bug", "enhancement"]

    async def test_get_github_issue_no_token_returns_503(self, client_no_github: AsyncClient) -> None:
        """GET /registry/github-issue returns 503 when no GitHub token is configured."""
        response = await client_no_github.get("/registry/github-issue?repo=owner/repo&number=42")
        assert response.status_code == 503

    @respx.mock
    async def test_get_github_issue_not_found_returns_404(self, client_with_github: AsyncClient) -> None:
        """GET /registry/github-issue returns 404 when the GitHub issue does not exist."""
        respx.get("https://api.github.com/repos/owner/repo/issues/999").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )
        response = await client_with_github.get("/registry/github-issue?repo=owner/repo&number=999")
        assert response.status_code == 404


class TestAgentWriteEndpoints:
    async def test_create_agent_returns_201(self, client: AsyncClient) -> None:
        """POST /registry/agents creates a new agent and returns 201."""
        payload = {
            "name": "tester",
            "description": "Runs tests.",
            "opencode_agent": "tester",
            "default_model": None,
            "system_prompt_additions": "",
        }
        response = await client.post("/registry/agents", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "tester"
        assert data["description"] == "Runs tests."
        assert "system_prompt_additions" not in data

    async def test_create_agent_persists_to_file(self, make_registry, client: AsyncClient) -> None:
        """POST /registry/agents writes the new agent to the YAML file."""
        payload = {
            "name": "tester",
            "description": "Runs tests.",
            "opencode_agent": "tester",
        }
        await client.post("/registry/agents", json=payload)
        registry = app.dependency_overrides[get_registry]()
        agents_path = registry._agents_path
        with open(agents_path) as f:
            data = yaml.safe_load(f)
        names = [a["name"] for a in data["agents"]]
        assert "tester" in names

    async def test_create_agent_duplicate_name_returns_409(self, client: AsyncClient) -> None:
        """POST /registry/agents returns 409 when the agent name already exists."""
        payload = {
            "name": "developer",
            "description": "Duplicate.",
            "opencode_agent": "developer",
        }
        response = await client.post("/registry/agents", json=payload)
        assert response.status_code == 409

    async def test_update_agent_returns_200(self, client: AsyncClient) -> None:
        """PUT /registry/agents/{name} updates an existing agent and returns 200."""
        payload = {
            "name": "developer",
            "description": "Updated description.",
            "opencode_agent": "developer",
        }
        response = await client.put("/registry/agents/developer", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "Updated description."

    async def test_update_agent_not_found_returns_404(self, client: AsyncClient) -> None:
        """PUT /registry/agents/{name} returns 404 when the agent does not exist."""
        payload = {
            "name": "ghost",
            "description": "Does not exist.",
            "opencode_agent": "ghost",
        }
        response = await client.put("/registry/agents/ghost", json=payload)
        assert response.status_code == 404

    async def test_delete_agent_returns_204(self, make_registry) -> None:
        """DELETE /registry/agents/{name} removes an unreferenced agent and returns 204."""
        # Create a registry where 'freelancer' exists but is not used in any pipeline
        registry = make_registry(
            agents={
                "agents": [
                    {
                        "name": "developer",
                        "description": "Implements.",
                        "opencode_agent": "developer",
                        "system_prompt_additions": "",
                    },
                    {
                        "name": "reviewer",
                        "description": "Reviews.",
                        "opencode_agent": "reviewer",
                        "system_prompt_additions": "",
                    },
                    {
                        "name": "freelancer",
                        "description": "Extra agent.",
                        "opencode_agent": "freelancer",
                        "system_prompt_additions": "",
                    },
                ]
            }
        )
        app.dependency_overrides[get_registry] = lambda: registry
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.delete("/registry/agents/freelancer")
        finally:
            app.dependency_overrides.clear()
        assert response.status_code == 204

    async def test_delete_agent_not_found_returns_404(self, client: AsyncClient) -> None:
        """DELETE /registry/agents/{name} returns 404 when the agent does not exist."""
        response = await client.delete("/registry/agents/nobody")
        assert response.status_code == 404

    async def test_delete_agent_used_in_pipeline_returns_409(self, client: AsyncClient) -> None:
        """DELETE /registry/agents/{name} returns 409 when the agent is referenced in a pipeline."""
        # 'developer' is used in the quick_fix pipeline's first step
        response = await client.delete("/registry/agents/developer")
        assert response.status_code == 409


class TestPipelineWriteEndpoints:
    async def test_create_pipeline_returns_201(self, client: AsyncClient) -> None:
        """POST /registry/pipelines creates a new pipeline and returns 201."""
        payload = {
            "name": "hotfix",
            "description": "Emergency hotfix flow.",
            "steps": [{"type": "agent", "agent": "developer", "description": "Fix it."}],
        }
        response = await client.post("/registry/pipelines", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "hotfix"
        assert len(data["steps"]) == 1

    async def test_create_pipeline_persists_to_file(self, client: AsyncClient) -> None:
        """POST /registry/pipelines writes the new pipeline to the YAML file."""
        payload = {
            "name": "hotfix",
            "description": "Emergency hotfix flow.",
            "steps": [{"type": "agent", "agent": "developer", "description": "Fix it."}],
        }
        await client.post("/registry/pipelines", json=payload)
        registry = app.dependency_overrides[get_registry]()
        pipelines_path = registry._pipelines_path
        with open(pipelines_path) as f:
            data = yaml.safe_load(f)
        names = [p["name"] for p in data["pipelines"]]
        assert "hotfix" in names

    async def test_create_pipeline_duplicate_name_returns_409(self, client: AsyncClient) -> None:
        """POST /registry/pipelines returns 409 when the pipeline name already exists."""
        payload = {
            "name": "quick_fix",
            "description": "Duplicate.",
            "steps": [{"type": "agent", "agent": "developer", "description": "dup."}],
        }
        response = await client.post("/registry/pipelines", json=payload)
        assert response.status_code == 409

    async def test_create_pipeline_unknown_agent_returns_422(self, client: AsyncClient) -> None:
        """POST /registry/pipelines returns 422 when a step references an unknown agent."""
        payload = {
            "name": "broken",
            "description": "References unknown agent.",
            "steps": [{"type": "agent", "agent": "nobody", "description": "boom."}],
        }
        response = await client.post("/registry/pipelines", json=payload)
        assert response.status_code == 422

    async def test_update_pipeline_returns_200(self, client: AsyncClient) -> None:
        """PUT /registry/pipelines/{name} updates an existing pipeline and returns 200."""
        payload = {
            "name": "quick_fix",
            "description": "Updated description.",
            "steps": [{"type": "agent", "agent": "developer", "description": "New step."}],
        }
        response = await client.put("/registry/pipelines/quick_fix", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "Updated description."

    async def test_update_pipeline_not_found_returns_404(self, client: AsyncClient) -> None:
        """PUT /registry/pipelines/{name} returns 404 when the pipeline does not exist."""
        payload = {
            "name": "ghost",
            "description": "Does not exist.",
            "steps": [],
        }
        response = await client.put("/registry/pipelines/ghost", json=payload)
        assert response.status_code == 404

    async def test_delete_pipeline_returns_204(self, client: AsyncClient) -> None:
        """DELETE /registry/pipelines/{name} removes a pipeline and returns 204."""
        response = await client.delete("/registry/pipelines/quick_fix")
        assert response.status_code == 204

    async def test_delete_pipeline_not_found_returns_404(self, client: AsyncClient) -> None:
        """DELETE /registry/pipelines/{name} returns 404 when the pipeline does not exist."""
        response = await client.delete("/registry/pipelines/nobody")
        assert response.status_code == 404

    async def test_create_pipeline_with_approval_step(self, client: AsyncClient) -> None:
        """POST /registry/pipelines accepts approval steps."""
        payload = {
            "name": "gated",
            "description": "Pipeline with human gate.",
            "steps": [
                {"type": "agent", "agent": "developer", "description": "Implement."},
                {"type": "approval", "description": "Human review."},
            ],
        }
        response = await client.post("/registry/pipelines", json=payload)
        assert response.status_code == 201
        steps = response.json()["steps"]
        assert steps[1]["type"] == "approval"
