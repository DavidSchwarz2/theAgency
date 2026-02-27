"""TDD tests for the /approvals REST API (Milestone 4)."""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import get_db
from app.main import app
from app.models import Approval, ApprovalStatus, Base, Pipeline, PipelineStatus, Step, StepStatus
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
async def test_client(db_engine, make_registry):
    """Test client wired to in-memory DB and real registry."""
    registry = make_registry()
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_registry] = lambda: registry
    app.state.pipeline_tasks = {}  # dict[int, asyncio.Task]
    app.state.active_runners = {}
    app.state.approval_events = {}
    app.state.db_session_factory = session_factory
    app.state.step_timeout = 600.0

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, session_factory

    app.dependency_overrides.clear()


async def _make_pipeline_with_approval(session_factory, approval_status: ApprovalStatus) -> tuple[int, int]:
    """Create a pipeline, step, and approval record. Returns (pipeline_id, approval_id)."""
    async with session_factory() as session:
        pipeline = Pipeline(
            title="Test",
            template="quick_fix",
            prompt="prompt",
            status=PipelineStatus.waiting_for_approval,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(pipeline)
        await session.flush()
        step = Step(
            pipeline_id=pipeline.id,
            agent_name="__approval__",
            order_index=0,
            status=StepStatus.running,
            started_at=datetime.now(UTC),
        )
        session.add(step)
        await session.flush()
        approval = Approval(
            step_id=step.id,
            status=approval_status,
            decided_at=datetime.now(UTC) if approval_status != ApprovalStatus.pending else None,
        )
        session.add(approval)
        await session.commit()
        return pipeline.id, approval.id


# ---------------------------------------------------------------------------
# Tests: GET /approvals
# ---------------------------------------------------------------------------


class TestListApprovals:
    async def test_get_approvals_returns_pending_by_default(self, test_client):
        """GET /approvals returns only pending approvals by default."""
        client, session_factory = test_client

        await _make_pipeline_with_approval(session_factory, ApprovalStatus.pending)
        await _make_pipeline_with_approval(session_factory, ApprovalStatus.approved)

        response = await client.get("/approvals")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == "pending"

    async def test_get_approvals_all_true_returns_all(self, test_client):
        """GET /approvals?include_all=true returns all approvals regardless of status."""
        client, session_factory = test_client

        await _make_pipeline_with_approval(session_factory, ApprovalStatus.pending)
        await _make_pipeline_with_approval(session_factory, ApprovalStatus.approved)
        await _make_pipeline_with_approval(session_factory, ApprovalStatus.rejected)

        response = await client.get("/approvals?include_all=true")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    async def test_get_approvals_returns_pipeline_id(self, test_client):
        """Each approval in the list includes pipeline_id from the associated step."""
        client, session_factory = test_client

        pipeline_id, approval_id = await _make_pipeline_with_approval(session_factory, ApprovalStatus.pending)

        response = await client.get("/approvals")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["pipeline_id"] == pipeline_id
        assert data[0]["id"] == approval_id

    async def test_get_approvals_empty_when_no_pending(self, test_client):
        """GET /approvals returns empty list when there are no pending approvals."""
        client, session_factory = test_client

        await _make_pipeline_with_approval(session_factory, ApprovalStatus.approved)

        response = await client.get("/approvals")
        assert response.status_code == 200
        assert response.json() == []
