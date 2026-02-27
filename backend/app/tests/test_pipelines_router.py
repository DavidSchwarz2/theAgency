"""TDD tests for the /pipelines REST API (Milestone 4)."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import get_db
from app.main import app
from app.models import Base, Pipeline, PipelineStatus, Step, StepStatus
from app.routers.pipelines import get_opencode_client
from app.routers.registry import get_registry
from app.services.pipeline_runner import APPROVAL_SENTINEL

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
    app.state.github_client = None

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


# ---------------------------------------------------------------------------
# GET /pipelines — list all pipelines
# ---------------------------------------------------------------------------


class TestListPipelines:
    async def test_list_pipelines_returns_all(self, test_client):
        """GET /pipelines returns 200 with a list of all pipelines ordered by id desc."""
        client, session_factory = test_client

        async with session_factory() as session:
            p1 = Pipeline(
                title="Pipeline One",
                template="quick_fix",
                prompt="prompt1",
                status=PipelineStatus.done,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            p2 = Pipeline(
                title="Pipeline Two",
                template="quick_fix",
                prompt="prompt2",
                status=PipelineStatus.running,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            session.add_all([p1, p2])
            await session.commit()

        response = await client.get("/pipelines")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2
        # Endpoint orders by id descending: p2 was inserted after p1, so it should come first.
        assert data[0]["title"] == "Pipeline Two"
        assert data[1]["title"] == "Pipeline One"

    async def test_list_pipelines_empty_returns_empty_list(self, test_client):
        """GET /pipelines with no pipelines returns an empty list."""
        client, _ = test_client

        response = await client.get("/pipelines")
        assert response.status_code == 200
        assert response.json() == []

    async def test_list_pipelines_response_shape(self, test_client):
        """GET /pipelines items conform to PipelineResponse schema (id, title, template, status, timestamps)."""
        from app.schemas.pipeline import PipelineResponse

        client, session_factory = test_client

        async with session_factory() as session:
            pipeline = Pipeline(
                title="Shape Test",
                template="quick_fix",
                prompt="prompt",
                status=PipelineStatus.running,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            session.add(pipeline)
            await session.commit()

        response = await client.get("/pipelines")
        assert response.status_code == 200
        item = response.json()[0]
        # Validate against the Pydantic schema to catch field mismatches automatically.
        validated = PipelineResponse.model_validate(item)
        assert validated.title == "Shape Test"
        assert validated.status.value == "running"
        # List endpoint must NOT include steps (PipelineResponse has no steps field).
        assert "steps" not in item


# ---------------------------------------------------------------------------
# Milestone 4 — step_models in PipelineCreateRequest
# ---------------------------------------------------------------------------


class TestCreatePipelineStepModels:
    async def test_create_pipeline_stores_step_model(self, test_client):
        """POST /pipelines with step_models stores the model on the Step ORM record."""
        from sqlalchemy import select as sa_select

        client, session_factory = test_client

        with patch("app.routers.pipelines.PipelineRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.run_pipeline = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            response = await client.post(
                "/pipelines",
                json={
                    "template": "quick_fix",
                    "title": "Model Test",
                    "prompt": "Do the thing",
                    "step_models": {"0": "claude-sonnet"},
                },
            )

        assert response.status_code == 201
        pipeline_id = response.json()["id"]

        async with session_factory() as session:
            result = await session.execute(
                sa_select(Step).where(Step.pipeline_id == pipeline_id).order_by(Step.order_index)
            )
            steps = result.scalars().all()

        assert steps[0].model == "claude-sonnet"
        assert steps[1].model is None  # step 1 not in step_models

    async def test_create_pipeline_uses_agent_default_model_when_no_step_model(self, test_client):
        """POST /pipelines without step_models falls back to agent's default_model."""
        from sqlalchemy import select as sa_select

        from app.tests.conftest import VALID_AGENTS, VALID_PIPELINES, write_yaml

        client, session_factory = test_client

        # Re-wire registry with an agent that has a default_model
        agents_with_default = {
            "agents": [
                {
                    "name": "developer",
                    "description": "Implements features.",
                    "opencode_agent": "developer",
                    "default_model": "gpt-4o",
                    "system_prompt_additions": "",
                },
                *VALID_AGENTS["agents"][1:],
            ]
        }
        import tempfile
        from pathlib import Path

        from app.services.agent_registry import AgentRegistry

        with tempfile.TemporaryDirectory() as tmp:
            agents_path = Path(tmp) / "agents.yaml"
            pipelines_path = Path(tmp) / "pipelines.yaml"
            write_yaml(agents_path, agents_with_default)
            write_yaml(pipelines_path, VALID_PIPELINES)
            registry_with_default = AgentRegistry(agents_path=str(agents_path), pipelines_path=str(pipelines_path))

        from app.routers.registry import get_registry

        original_override = app.dependency_overrides.get(get_registry)
        app.dependency_overrides[get_registry] = lambda: registry_with_default
        try:
            with patch("app.routers.pipelines.PipelineRunner") as mock_runner_cls:
                mock_runner = MagicMock()
                mock_runner.run_pipeline = AsyncMock()
                mock_runner_cls.return_value = mock_runner

                response = await client.post(
                    "/pipelines",
                    json={"template": "quick_fix", "title": "Default Model Test", "prompt": "Do the thing"},
                )
        finally:
            # Restore the registry override set by the test_client fixture to avoid leaking state.
            if original_override is not None:
                app.dependency_overrides[get_registry] = original_override
            else:
                app.dependency_overrides.pop(get_registry, None)

        assert response.status_code == 201
        pipeline_id = response.json()["id"]

        async with session_factory() as session:
            result = await session.execute(
                sa_select(Step).where(Step.pipeline_id == pipeline_id).order_by(Step.order_index)
            )
            steps = result.scalars().all()

        # Both steps are for "developer" which has default_model="gpt-4o"
        assert steps[0].model == "gpt-4o"


# ---------------------------------------------------------------------------
# Issue #12 — working_dir per pipeline run
# ---------------------------------------------------------------------------


class TestCreatePipelineWorkingDir:
    async def test_create_pipeline_with_working_dir(self, test_client):
        """POST /pipelines with working_dir persists and returns the value."""
        from sqlalchemy import select as sa_select

        client, session_factory = test_client

        with patch("app.routers.pipelines.PipelineRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.run_pipeline = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            response = await client.post(
                "/pipelines",
                json={
                    "template": "quick_fix",
                    "title": "WD Test",
                    "prompt": "Do the thing",
                    "working_dir": "/tmp/my_project",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["working_dir"] == "/tmp/my_project"

        pipeline_id = data["id"]
        async with session_factory() as session:
            result = await session.execute(sa_select(Pipeline).where(Pipeline.id == pipeline_id))
            pipeline = result.scalar_one()
            assert pipeline.working_dir == "/tmp/my_project"

    async def test_create_pipeline_without_working_dir_defaults_to_none(self, test_client):
        """POST /pipelines without working_dir returns working_dir=null."""
        client, _ = test_client

        with patch("app.routers.pipelines.PipelineRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.run_pipeline = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            response = await client.post(
                "/pipelines",
                json={"template": "quick_fix", "title": "No WD", "prompt": "hello"},
            )

        assert response.status_code == 201
        assert response.json()["working_dir"] is None

    async def test_get_pipeline_returns_working_dir(self, test_client):
        """GET /pipelines/{id} includes working_dir in the response."""
        client, session_factory = test_client

        async with session_factory() as session:
            pipeline = Pipeline(
                title="WD Get Test",
                template="quick_fix",
                prompt="prompt",
                status=PipelineStatus.running,
                working_dir="/srv/repo",
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
        assert response.json()["working_dir"] == "/srv/repo"


# ---------------------------------------------------------------------------
# Issue #16 — Free Agent Composition (custom steps)
# ---------------------------------------------------------------------------


class TestCreatePipelineCustomSteps:
    async def test_custom_steps_returns_201(self, test_client):
        """POST /pipelines with custom_steps (no template) returns 201."""
        client, _ = test_client

        with patch("app.routers.pipelines.PipelineRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.run_pipeline = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            response = await client.post(
                "/pipelines",
                json={
                    "custom_steps": [{"type": "agent", "agent": "developer"}],
                    "title": "Custom Run",
                    "prompt": "Do the thing",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["template"] == "__custom__"
        assert data["title"] == "Custom Run"

    async def test_custom_steps_creates_correct_step_records(self, test_client):
        """POST /pipelines with custom_steps creates Step records in DB."""
        from sqlalchemy import select as sa_select

        client, session_factory = test_client

        with patch("app.routers.pipelines.PipelineRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.run_pipeline = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            response = await client.post(
                "/pipelines",
                json={
                    "custom_steps": [
                        {"type": "agent", "agent": "developer"},
                        {"type": "approval"},
                        {"type": "agent", "agent": "reviewer"},
                    ],
                    "title": "Multi-step",
                    "prompt": "Go",
                },
            )

        assert response.status_code == 201
        pipeline_id = response.json()["id"]

        async with session_factory() as session:
            result = await session.execute(
                sa_select(Step).where(Step.pipeline_id == pipeline_id).order_by(Step.order_index)
            )
            steps = result.scalars().all()

        assert len(steps) == 3
        assert steps[0].agent_name == "developer"
        assert steps[1].agent_name == APPROVAL_SENTINEL
        assert steps[2].agent_name == "reviewer"

    async def test_custom_steps_model_override_stored(self, test_client):
        """POST /pipelines with custom_steps and per-step model stores model on Step."""
        from sqlalchemy import select as sa_select

        client, session_factory = test_client

        with patch("app.routers.pipelines.PipelineRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.run_pipeline = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            response = await client.post(
                "/pipelines",
                json={
                    "custom_steps": [{"type": "agent", "agent": "developer", "model": "claude-opus"}],
                    "title": "Model Override",
                    "prompt": "Go",
                },
            )

        assert response.status_code == 201
        pipeline_id = response.json()["id"]

        async with session_factory() as session:
            result = await session.execute(sa_select(Step).where(Step.pipeline_id == pipeline_id))
            steps = result.scalars().all()

        assert steps[0].model == "claude-opus"

    async def test_neither_template_nor_custom_steps_returns_422(self, test_client):
        """POST /pipelines with neither template nor custom_steps returns 422."""
        client, _ = test_client

        response = await client.post(
            "/pipelines",
            json={"title": "Broken", "prompt": "fail"},
        )
        assert response.status_code == 422

    async def test_both_template_and_custom_steps_returns_422(self, test_client):
        """POST /pipelines with both template and custom_steps returns 422."""
        client, _ = test_client

        response = await client.post(
            "/pipelines",
            json={
                "template": "quick_fix",
                "custom_steps": [{"type": "agent", "agent": "developer"}],
                "title": "Conflict",
                "prompt": "fail",
            },
        )
        assert response.status_code == 422

    async def test_unknown_agent_in_custom_steps_returns_422(self, test_client):
        """POST /pipelines with unknown agent in custom_steps returns 422."""
        client, _ = test_client

        with patch("app.routers.pipelines.PipelineRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.run_pipeline = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            response = await client.post(
                "/pipelines",
                json={
                    "custom_steps": [{"type": "agent", "agent": "ghost_agent"}],
                    "title": "Bad Agent",
                    "prompt": "fail",
                },
            )

        assert response.status_code == 422

    async def test_empty_custom_steps_returns_422(self, test_client):
        """POST /pipelines with empty custom_steps list returns 422."""
        client, _ = test_client

        response = await client.post(
            "/pipelines",
            json={"custom_steps": [], "title": "Empty", "prompt": "fail"},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Issue #14 — Local agents from working directory (router integration)
# ---------------------------------------------------------------------------


class TestLocalAgentMerge:
    async def test_local_agent_default_model_used_for_step(self, test_client, tmp_path):
        """POST /pipelines with working_dir uses local agent's default_model for step model."""
        import yaml
        from sqlalchemy import select as sa_select

        client, session_factory = test_client

        # Write a local developer agent with a custom default_model
        agents_dir = tmp_path / ".opencode" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "developer.yaml").write_text(
            yaml.dump(
                {
                    "name": "developer",
                    "description": "Local developer",
                    "opencode_agent": "developer",
                    "default_model": "local-model-override",
                    "system_prompt_additions": "",
                }
            )
        )

        with patch("app.routers.pipelines.PipelineRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.run_pipeline = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            response = await client.post(
                "/pipelines",
                json={
                    "template": "quick_fix",
                    "title": "Local Agent Test",
                    "prompt": "Do the thing",
                    "working_dir": str(tmp_path),
                },
            )

        assert response.status_code == 201
        pipeline_id = response.json()["id"]

        async with session_factory() as session:
            result = await session.execute(
                sa_select(Step).where(Step.pipeline_id == pipeline_id).order_by(Step.order_index)
            )
            steps = result.scalars().all()

        # Both steps are "developer" which now has default_model="local-model-override"
        assert steps[0].model == "local-model-override"


# ---------------------------------------------------------------------------
# Issue #13 — GitHub Issue as Context (prompt enrichment)
# ---------------------------------------------------------------------------


@pytest.fixture
async def test_client_with_github(db_engine, make_registry, mock_opencode_client):
    """Test client with a real GitHubClient wired into app.state."""
    from app.adapters.github_client import GitHubClient

    registry = make_registry()
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    github_client = GitHubClient(token="test-token")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_registry] = lambda: registry
    app.dependency_overrides[get_opencode_client] = lambda: mock_opencode_client
    app.state.pipeline_tasks = {}
    app.state.active_runners = {}
    app.state.approval_events = {}
    app.state.db_session_factory = session_factory
    app.state.step_timeout = 600.0
    app.state.github_client = github_client

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, session_factory

    app.dependency_overrides.clear()
    app.state.github_client = None
    await github_client.close()


class TestCreatePipelineGitHubEnrichment:
    async def test_prompt_enriched_with_github_issue(self, test_client_with_github):
        """POST /pipelines with github_issue_repo + github_issue_number enriches the stored prompt."""
        client, session_factory = test_client_with_github

        with respx.mock, patch("app.routers.pipelines.PipelineRunner") as mock_runner_cls:
            respx.get("https://api.github.com/repos/owner/repo/issues/42").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "number": 42,
                        "title": "Fix the thing",
                        "body": "It is broken.",
                        "labels": [{"name": "bug"}],
                    },
                )
            )
            mock_runner = MagicMock()
            mock_runner.run_pipeline = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            response = await client.post(
                "/pipelines",
                json={
                    "template": "quick_fix",
                    "title": "GitHub Test",
                    "prompt": "Original prompt",
                    "github_issue_repo": "owner/repo",
                    "github_issue_number": 42,
                },
            )

        assert response.status_code == 201
        pipeline_id = response.json()["id"]

        async with session_factory() as session:
            from app.models import Pipeline as PipelineModel

            pipeline = await session.get(PipelineModel, pipeline_id)
            assert pipeline is not None
            assert "## GitHub Issue #42: Fix the thing" in pipeline.prompt
            assert "It is broken." in pipeline.prompt
            assert "Labels: bug" in pipeline.prompt
            assert "Original prompt" in pipeline.prompt

    async def test_prompt_enrichment_failed_fetch_falls_back_to_original(self, test_client_with_github):
        """If the GitHub issue fetch fails, create_pipeline still succeeds with the original prompt."""
        client, session_factory = test_client_with_github

        with respx.mock, patch("app.routers.pipelines.PipelineRunner") as mock_runner_cls:
            respx.get("https://api.github.com/repos/owner/repo/issues/99").mock(
                return_value=httpx.Response(404, json={"message": "Not Found"})
            )
            mock_runner = MagicMock()
            mock_runner.run_pipeline = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            response = await client.post(
                "/pipelines",
                json={
                    "template": "quick_fix",
                    "title": "Fallback Test",
                    "prompt": "Fallback prompt",
                    "github_issue_repo": "owner/repo",
                    "github_issue_number": 99,
                },
            )

        assert response.status_code == 201
        pipeline_id = response.json()["id"]

        async with session_factory() as session:
            from app.models import Pipeline as PipelineModel

            pipeline = await session.get(PipelineModel, pipeline_id)
            assert pipeline is not None
            assert pipeline.prompt == "Fallback prompt"

    async def test_no_github_fields_prompt_unchanged(self, test_client):
        """POST /pipelines without github fields stores the prompt unmodified."""
        client, session_factory = test_client

        with patch("app.routers.pipelines.PipelineRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.run_pipeline = AsyncMock()
            mock_runner_cls.return_value = mock_runner

            response = await client.post(
                "/pipelines",
                json={"template": "quick_fix", "title": "No GH", "prompt": "Plain prompt"},
            )

        assert response.status_code == 201
        pipeline_id = response.json()["id"]

        async with session_factory() as session:
            from app.models import Pipeline as PipelineModel

            pipeline = await session.get(PipelineModel, pipeline_id)
            assert pipeline is not None
            assert pipeline.prompt == "Plain prompt"
