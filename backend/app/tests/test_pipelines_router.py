"""TDD tests for the /pipelines REST API (Milestone 4)."""

import asyncio
from datetime import UTC, datetime
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
    app.state.pipeline_tasks = {}  # dict[int, asyncio.Task]
    app.state.active_runners = {}
    app.state.approval_events = {}
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
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
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
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
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
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            session.add(pipeline)
            await session.commit()
            pipeline_id = pipeline.id

        response = await client.post(f"/pipelines/{pipeline_id}/abort")
        assert response.status_code == 409


# ---------------------------------------------------------------------------
# Tests 21-22: GET /pipelines/{id} includes latest_handoff (Milestone 3)
# ---------------------------------------------------------------------------


class TestGetPipelineHandoff:
    async def test_get_pipeline_includes_latest_handoff(self, test_client):
        """GET /pipelines/{id} response includes latest_handoff with metadata for a done step."""

        from app.models import Handoff
        from app.schemas.handoff import HandoffSchema

        client, session_factory = test_client

        async with session_factory() as session:
            pipeline = Pipeline(
                title="With Handoff",
                template="quick_fix",
                prompt="prompt",
                status=PipelineStatus.done,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            session.add(pipeline)
            await session.flush()

            step = Step(
                pipeline_id=pipeline.id,
                agent_name="developer",
                order_index=0,
                status=StepStatus.done,
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            )
            session.add(step)
            await session.flush()

            schema = HandoffSchema(
                what_was_done="Fixed the bug.",
                next_agent_context="Review the fix.",
            )
            handoff = Handoff(
                step_id=step.id,
                content_md="## What Was Done\nFixed the bug.\n\n## Next Agent Context\nReview the fix.",
                metadata_json=schema.model_dump_json(exclude_none=True),
            )
            session.add(handoff)
            await session.commit()
            pipeline_id = pipeline.id

        response = await client.get(f"/pipelines/{pipeline_id}")
        assert response.status_code == 200
        data = response.json()
        step_data = data["steps"][0]
        assert step_data["latest_handoff"] is not None
        assert step_data["latest_handoff"]["content_md"] is not None
        metadata = step_data["latest_handoff"]["metadata"]
        assert metadata is not None
        assert metadata["what_was_done"] == "Fixed the bug."
        assert metadata["next_agent_context"] == "Review the fix."

    async def test_get_pipeline_handoff_null_when_no_handoff(self, test_client):
        """GET /pipelines/{id} response has latest_handoff=null for a step with no handoffs."""
        client, session_factory = test_client

        async with session_factory() as session:
            pipeline = Pipeline(
                title="No Handoff",
                template="quick_fix",
                prompt="prompt",
                status=PipelineStatus.running,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
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
        assert data["steps"][0]["latest_handoff"] is None


# ---------------------------------------------------------------------------
# Shared helper for approval tests
# ---------------------------------------------------------------------------


async def _make_waiting_pipeline(session_factory, approval_events: dict) -> tuple[int, asyncio.Event]:
    """Create a pipeline in waiting_for_approval state with a pending Approval record.

    Registers an (unset) asyncio.Event in approval_events so the endpoint can fire it.
    Returns (pipeline_id, event).
    """
    from app.models import Approval, ApprovalStatus

    async with session_factory() as session:
        pipeline = Pipeline(
            title="Awaiting Approval",
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
        approval = Approval(step_id=step.id, status=ApprovalStatus.pending)
        session.add(approval)
        await session.commit()
        pipeline_id = pipeline.id

    event = asyncio.Event()
    approval_events[pipeline_id] = event
    return pipeline_id, event


# ---------------------------------------------------------------------------
# Milestone 3: POST /pipelines/{id}/approve and /reject
# ---------------------------------------------------------------------------


class TestApprovePipeline:
    async def test_approve_pipeline_returns_200(self, test_client):
        """POST /pipelines/{id}/approve returns 200."""
        client, session_factory = test_client
        pipeline_id, event = await _make_waiting_pipeline(session_factory, app.state.approval_events)

        response = await client.post(
            f"/pipelines/{pipeline_id}/approve",
            json={"comment": "LGTM", "decided_by": "alice"},
        )
        assert response.status_code == 200
        assert event.is_set()

    async def test_approve_pipeline_sets_approval_approved(self, test_client):
        """POST /pipelines/{id}/approve sets the Approval record to approved."""
        from app.models import Approval, ApprovalStatus

        client, session_factory = test_client
        pipeline_id, _ = await _make_waiting_pipeline(session_factory, app.state.approval_events)

        await client.post(
            f"/pipelines/{pipeline_id}/approve",
            json={"comment": "All good", "decided_by": "bob"},
        )

        async with session_factory() as session:
            from sqlalchemy import select

            result = await session.execute(select(Approval).join(Step).where(Step.pipeline_id == pipeline_id))
            approval = result.scalar_one()
            assert approval.status == ApprovalStatus.approved
            assert approval.comment == "All good"
            assert approval.decided_by == "bob"
            assert approval.decided_at is not None

    async def test_approve_pipeline_not_waiting_returns_409(self, test_client):
        """POST /pipelines/{id}/approve on a non-waiting pipeline returns 409."""
        client, session_factory = test_client

        async with session_factory() as session:
            pipeline = Pipeline(
                title="Running",
                template="quick_fix",
                prompt="prompt",
                status=PipelineStatus.running,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            session.add(pipeline)
            await session.commit()
            pipeline_id = pipeline.id

        response = await client.post(f"/pipelines/{pipeline_id}/approve", json={})
        assert response.status_code == 409

    async def test_approve_pipeline_not_found_returns_404(self, test_client):
        """POST /pipelines/99999/approve returns 404."""
        client, _ = test_client
        response = await client.post("/pipelines/99999/approve", json={})
        assert response.status_code == 404


class TestRejectPipeline:
    async def test_reject_pipeline_returns_200(self, test_client):
        """POST /pipelines/{id}/reject returns 200."""
        client, session_factory = test_client
        pipeline_id, event = await _make_waiting_pipeline(session_factory, app.state.approval_events)

        response = await client.post(
            f"/pipelines/{pipeline_id}/reject",
            json={"comment": "Not ready", "decided_by": "carol"},
        )
        assert response.status_code == 200
        assert event.is_set()

    async def test_reject_pipeline_sets_approval_rejected(self, test_client):
        """POST /pipelines/{id}/reject sets the Approval record to rejected."""
        from app.models import Approval, ApprovalStatus

        client, session_factory = test_client
        pipeline_id, _ = await _make_waiting_pipeline(session_factory, app.state.approval_events)

        await client.post(
            f"/pipelines/{pipeline_id}/reject",
            json={"comment": "Needs rework", "decided_by": "dan"},
        )

        async with session_factory() as session:
            from sqlalchemy import select

            result = await session.execute(select(Approval).join(Step).where(Step.pipeline_id == pipeline_id))
            approval = result.scalar_one()
            assert approval.status == ApprovalStatus.rejected
            assert approval.decided_by == "dan"
            assert approval.decided_at is not None

    async def test_reject_pipeline_not_waiting_returns_409(self, test_client):
        """POST /pipelines/{id}/reject on a non-waiting pipeline returns 409."""
        client, session_factory = test_client

        async with session_factory() as session:
            pipeline = Pipeline(
                title="Done",
                template="quick_fix",
                prompt="prompt",
                status=PipelineStatus.done,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            session.add(pipeline)
            await session.commit()
            pipeline_id = pipeline.id

        response = await client.post(f"/pipelines/{pipeline_id}/reject", json={})
        assert response.status_code == 409
