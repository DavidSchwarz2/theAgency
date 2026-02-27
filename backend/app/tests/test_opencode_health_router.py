"""TDD tests for GET /health/opencode and POST /health/opencode/start."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routers.health import get_opencode_client


@pytest.fixture
def mock_opencode_client():
    client = MagicMock()
    client.health_check = AsyncMock(return_value=True)
    return client


@pytest.fixture
async def test_client(mock_opencode_client):
    app.dependency_overrides[get_opencode_client] = lambda: mock_opencode_client
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, mock_opencode_client
    app.dependency_overrides.clear()


class TestOpenCodeStatusEndpoint:
    async def test_returns_200_when_available(self, test_client):
        client, mock = test_client
        mock.health_check = AsyncMock(return_value=True)
        response = await client.get("/health/opencode")
        assert response.status_code == 200

    async def test_body_available_true(self, test_client):
        client, mock = test_client
        mock.health_check = AsyncMock(return_value=True)
        body = (await client.get("/health/opencode")).json()
        assert body["available"] is True

    async def test_returns_200_when_unavailable(self, test_client):
        client, mock = test_client
        mock.health_check = AsyncMock(return_value=False)
        response = await client.get("/health/opencode")
        assert response.status_code == 200

    async def test_body_available_false(self, test_client):
        client, mock = test_client
        mock.health_check = AsyncMock(return_value=False)
        body = (await client.get("/health/opencode")).json()
        assert body["available"] is False


class TestOpenCodeStartEndpoint:
    async def test_start_returns_200_when_already_running(self, test_client):
        client, mock = test_client
        mock.health_check = AsyncMock(return_value=True)
        response = await client.post("/health/opencode/start")
        assert response.status_code == 200

    async def test_start_body_when_already_running(self, test_client):
        client, mock = test_client
        mock.health_check = AsyncMock(return_value=True)
        body = (await client.post("/health/opencode/start")).json()
        assert body["available"] is True
        assert body["started"] is False

    async def test_start_launches_process_when_not_running(self, test_client):
        client, mock = test_client
        # First call (pre-check): not running. Remaining calls (poll loop): running.
        mock.health_check = AsyncMock(side_effect=[False] + [True] * 10)
        with patch("app.routers.health.asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_proc:
            with patch("app.routers.health.asyncio.sleep", new_callable=AsyncMock):
                mock_proc.return_value = MagicMock()
                response = await client.post("/health/opencode/start")
        assert response.status_code == 200
        mock_proc.assert_called_once_with("opencode", "serve", "--port", "4096")

    async def test_start_body_started_true(self, test_client):
        client, mock = test_client
        mock.health_check = AsyncMock(side_effect=[False] + [True] * 10)
        with patch("app.routers.health.asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_proc:
            with patch("app.routers.health.asyncio.sleep", new_callable=AsyncMock):
                mock_proc.return_value = MagicMock()
                body = (await client.post("/health/opencode/start")).json()
        assert body["started"] is True
        assert body["available"] is True

    async def test_start_returns_503_if_launch_fails(self, test_client):
        client, mock = test_client
        mock.health_check = AsyncMock(return_value=False)
        with patch("app.routers.health.asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_proc:
            with patch("app.routers.health.asyncio.sleep", new_callable=AsyncMock):
                mock_proc.return_value = MagicMock()
                response = await client.post("/health/opencode/start")
        assert response.status_code == 503
