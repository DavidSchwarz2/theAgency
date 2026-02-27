"""TDD tests for the /pipelines REST API (Milestone 4)."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import get_db
from app.main import app
from app.models import Base, Pipeline, PipelineStatus, Step, StepStatus
from app.routers.pipelines import get_opencode_client
from app.routers.registry import get_registry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def mock_opencode_client():
    client = MagicMock()
    client.abort_session = AsyncMock(return_value=True)
    return client


@pytest.fixture
async def test_client(db_engine, make_registry, mock_opencode_client):
    """Test client with overridden dependencies: in-memory DB, real registry, mock OC client."""
    registry = make_registry()

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_registry] = lambda: registry
    app.dependency_overrides[get_opencode_client] = lambda: mock_opencode_client
    # Also inject pipeline_tasks, active_runners, db_session_factory, and step_timeout into app.state
    app.state.pipeline_tasks = set()
    app.state.active_runners = {}
    app.state.db_session_factory = session_factory
    app.state.step_timeout = 600.0

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, session_factory

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test 16: POST /pipelines returns 201
# ---------------------------------------------------------------------------


class TestCreatePipeline:
    async def test_create_pipeline_returns_201(self, test_client):
        """POST /pipelines with valid template returns 201 with id and status."""
        client, _ = test_client

        with patch("app.routers.pipelines.PipelineRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.run_pipeline = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            response = await client.post(
                "/pipelines",
                json={"template": "quick_fix", "title": "Fix bug", "prompt": "Button broken"},
            )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["status"] == "running"
        assert data["title"] == "Fix bug"

    async def test_create_pipeline_unknown_template_returns_422(self, test_client):
        """POST /pipelines with unknown template returns 422."""
        client, _ = test_client

        response = await client.post(
            "/pipelines",
            json={"template": "nonexistent", "title": "Fix bug", "prompt": "Button broken"},
        )

        assert response.status_code == 422

    async def test_create_pipeline_persists_prompt(self, test_client):
        """POST /pipelines persists the prompt on the Pipeline ORM record."""
        client, session_factory = test_client

        with patch("app.routers.pipelines.PipelineRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.run_pipeline = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            response = await client.post(
                "/pipelines",
                json={"template": "quick_fix", "title": "Test", "prompt": "My prompt here"},
            )

        assert response.status_code == 201
        pipeline_id = response.json()["id"]

        async with session_factory() as session:
            pipeline = await session.get(Pipeline, pipeline_id)
            assert pipeline is not None
            assert pipeline.prompt == "My prompt here"


# ---------------------------------------------------------------------------
# Test 19: GET /pipelines/{id}
# ---------------------------------------------------------------------------


class TestGetPipeline:
    async def test_get_pipeline_returns_200(self, test_client):
        """GET /pipelines/{id} returns 200 with steps list."""
        client, session_factory = test_client

        # Create pipeline in DB
        async with session_factory() as session:
            pipeline = Pipeline(
                title="Test",
                template="quick_fix",
                prompt="prompt",
                status=PipelineStatus.running,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(pipeline)
            await session.flush()
            step = Step(
                pipeline_id=pipeline.id,
                agent_name="developer",
                order_index=0,
                status=StepStatus.pending,
            )
            session.add(step)
            await session.commit()
            pipeline_id = pipeline.id

        response = await client.get(f"/pipelines/{pipeline_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == pipeline_id
        assert "steps" in data
        assert len(data["steps"]) == 1
        assert data["steps"][0]["agent_name"] == "developer"

    async def test_get_pipeline_not_found_returns_404(self, test_client):
        """GET /pipelines/99999 returns 404."""
        client, _ = test_client
        response = await client.get("/pipelines/99999")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Test 21: POST /pipelines/{id}/abort
# ---------------------------------------------------------------------------


class TestAbortPipeline:
    async def test_abort_pipeline_returns_200(self, test_client):
        """POST /pipelines/{id}/abort returns 200 and marks pipeline failed."""
        client, session_factory = test_client

        async with session_factory() as session:
            pipeline = Pipeline(
                title="Running",
                template="quick_fix",
                prompt="prompt",
                status=PipelineStatus.running,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(pipeline)
            await session.flush()
            step = Step(
                pipeline_id=pipeline.id,
                agent_name="developer",
                order_index=0,
                status=StepStatus.running,
            )
            session.add(step)
            await session.commit()
            pipeline_id = pipeline.id

        response = await client.post(f"/pipelines/{pipeline_id}/abort")
        assert response.status_code == 200

        async with session_factory() as session:
            refreshed = await session.get(Pipeline, pipeline_id)
            assert refreshed.status == PipelineStatus.failed

    async def test_abort_pipeline_not_running_returns_409(self, test_client):
        """POST /pipelines/{id}/abort on a done pipeline returns 409."""
        client, session_factory = test_client

        async with session_factory() as session:
            pipeline = Pipeline(
                title="Done",
                template="quick_fix",
                prompt="prompt",
                status=PipelineStatus.done,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(pipeline)
            await session.commit()
            pipeline_id = pipeline.id

        response = await client.post(f"/pipelines/{pipeline_id}/abort")
        assert response.status_code == 409
