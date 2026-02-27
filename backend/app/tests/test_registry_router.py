import pytest
from httpx import ASGITransport, AsyncClient

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
