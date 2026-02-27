import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


class TestHealthEndpoint:
    async def test_health_returns_200(self, client: AsyncClient):
        response = await client.get("/health")
        assert response.status_code == 200

    async def test_health_returns_expected_body(self, client: AsyncClient):
        response = await client.get("/health")
        body = response.json()
        assert body["status"] == "ok"
        assert "version" in body
