import pytest
import respx
import httpx
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
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
