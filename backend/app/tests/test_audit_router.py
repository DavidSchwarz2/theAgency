"""TDD tests for the /audit REST API — Issue #9."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import get_db
from app.main import app
from app.models import AuditEvent, Base, Pipeline, PipelineStatus, Step, StepStatus
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
    """Test client wired to in-memory DB.

    All async test methods run without explicit markers because asyncio_mode = "auto"
    is set globally in pyproject.toml [tool.pytest.ini_options].
    """
    registry = make_registry()
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_registry] = lambda: registry
    app.state.pipeline_tasks = {}
    app.state.active_runners = {}
    app.state.approval_events = {}
    app.state.db_session_factory = session_factory
    app.state.step_timeout = 600.0

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac, session_factory
    finally:
        app.dependency_overrides.clear()


async def _seed_pipeline(session_factory) -> tuple[int, int]:
    """Create a pipeline with one step. Returns (pipeline_id, step_id)."""
    async with session_factory() as session:
        pipeline = Pipeline(
            title="Audit Test",
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
        await session.commit()
        return pipeline.id, step.id


async def _seed_event(
    session_factory,
    pipeline_id: int,
    step_id: int,
    event_type: str,
    payload: dict | None = None,
    created_at: datetime | None = None,
) -> int:
    """Insert a single AuditEvent. Returns its id."""
    async with session_factory() as session:
        event = AuditEvent(
            pipeline_id=pipeline_id,
            step_id=step_id,
            event_type=event_type,
            payload_json=json.dumps(payload) if payload is not None else None,
        )
        if created_at is not None:
            event.created_at = created_at
        session.add(event)
        await session.commit()
        return event.id


# ---------------------------------------------------------------------------
# Milestone 1: GET /audit
# ---------------------------------------------------------------------------


class TestListAuditEvents:
    async def test_get_audit_empty(self, test_client):
        """GET /audit returns empty list when no events exist."""
        client, _ = test_client
        response = await client.get("/audit")
        assert response.status_code == 200
        assert response.json() == []

    async def test_get_audit_returns_events(self, test_client):
        """GET /audit returns all events, newest first."""
        client, session_factory = test_client
        pipeline_id, step_id = await _seed_pipeline(session_factory)
        now = datetime.now(UTC)
        await _seed_event(
            session_factory,
            pipeline_id,
            step_id,
            "handoff_created",
            {"handoff_id": 1},
            created_at=now - timedelta(seconds=2),
        )
        await _seed_event(session_factory, pipeline_id, step_id, "handoff_extraction_failed", created_at=now)

        response = await client.get("/audit")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        # newest first — extraction_failed was created later
        assert data[0]["event_type"] == "handoff_extraction_failed"

    async def test_get_audit_filter_pipeline_id(self, test_client):
        """GET /audit?pipeline_id=X returns only events for that pipeline."""
        client, session_factory = test_client
        pid1, sid1 = await _seed_pipeline(session_factory)
        pid2, sid2 = await _seed_pipeline(session_factory)
        await _seed_event(session_factory, pid1, sid1, "handoff_created")
        await _seed_event(session_factory, pid2, sid2, "handoff_created")

        response = await client.get(f"/audit?pipeline_id={pid1}")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["pipeline_id"] == pid1

    async def test_get_audit_filter_event_type(self, test_client):
        """GET /audit?event_type=approval_granted returns only matching events."""
        client, session_factory = test_client
        pid, sid = await _seed_pipeline(session_factory)
        await _seed_event(session_factory, pid, sid, "handoff_created")
        await _seed_event(session_factory, pid, sid, "approval_granted")

        response = await client.get("/audit?event_type=approval_granted")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["event_type"] == "approval_granted"

    async def test_get_audit_filter_since(self, test_client):
        """GET /audit?since=<iso> returns only events at or after that time."""
        client, session_factory = test_client
        pid, sid = await _seed_pipeline(session_factory)
        old = datetime.now(UTC) - timedelta(days=2)
        recent = datetime.now(UTC)
        await _seed_event(session_factory, pid, sid, "old_event", created_at=old)
        await _seed_event(session_factory, pid, sid, "recent_event", created_at=recent)

        # Use naive UTC ISO string to avoid URL encoding issues with +00:00
        cutoff = (datetime.now(UTC) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        response = await client.get(f"/audit?since={cutoff}")
        assert response.status_code == 200
        data = response.json()
        types = [e["event_type"] for e in data]
        assert "recent_event" in types
        assert "old_event" not in types

    async def test_get_audit_limit(self, test_client):
        """GET /audit?limit=1 returns at most 1 event."""
        client, session_factory = test_client
        pid, sid = await _seed_pipeline(session_factory)
        await _seed_event(session_factory, pid, sid, "e1")
        await _seed_event(session_factory, pid, sid, "e2")

        response = await client.get("/audit?limit=1")
        assert response.status_code == 200
        assert len(response.json()) == 1

    async def test_get_audit_offset(self, test_client):
        """GET /audit?limit=1&offset=1 returns the second-newest event."""
        client, session_factory = test_client
        now = datetime.now(UTC)
        pid, sid = await _seed_pipeline(session_factory)
        await _seed_event(session_factory, pid, sid, "e_older", created_at=now - timedelta(seconds=1))
        await _seed_event(session_factory, pid, sid, "e_newer", created_at=now)

        # newest first: page 0 = e_newer, page 1 = e_older
        response = await client.get("/audit?limit=1&offset=1")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["event_type"] == "e_older"

    async def test_get_audit_returns_payload(self, test_client):
        """GET /audit returns parsed payload dict, not raw JSON string."""
        client, session_factory = test_client
        pid, sid = await _seed_pipeline(session_factory)
        await _seed_event(session_factory, pid, sid, "handoff_created", {"handoff_id": 42})

        response = await client.get("/audit")
        assert response.status_code == 200
        data = response.json()
        assert data[0]["payload"] == {"handoff_id": 42}


# ---------------------------------------------------------------------------
# Milestone 2: GET /audit/export
# ---------------------------------------------------------------------------


class TestExportAuditEvents:
    async def test_export_json(self, test_client):
        """GET /audit/export?export_format=json returns 200 with attachment header."""
        client, session_factory = test_client
        pid, sid = await _seed_pipeline(session_factory)
        await _seed_event(session_factory, pid, sid, "handoff_created", {"handoff_id": 1})

        response = await client.get("/audit/export?export_format=json")
        assert response.status_code == 200
        assert "attachment" in response.headers.get("content-disposition", "")
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1

    async def test_export_markdown(self, test_client):
        """GET /audit/export?export_format=markdown returns 200 with markdown table."""
        client, session_factory = test_client
        pid, sid = await _seed_pipeline(session_factory)
        await _seed_event(session_factory, pid, sid, "handoff_created")

        response = await client.get("/audit/export?export_format=markdown")
        assert response.status_code == 200
        assert "attachment" in response.headers.get("content-disposition", "")
        body = response.text
        assert "| id |" in body
        assert "handoff_created" in body

    async def test_export_unknown_format_returns_422(self, test_client):
        """GET /audit/export?export_format=xml returns 422."""
        client, _ = test_client
        response = await client.get("/audit/export?export_format=xml")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Milestone 3: POST /audit/retention
# ---------------------------------------------------------------------------


class TestRetention:
    async def test_retention_deletes_old_events(self, test_client):
        """POST /audit/retention deletes events older than N days."""
        client, session_factory = test_client
        pid, sid = await _seed_pipeline(session_factory)
        old = datetime.now(UTC) - timedelta(days=35)
        await _seed_event(session_factory, pid, sid, "old_event", created_at=old)
        await _seed_event(session_factory, pid, sid, "recent_event")

        response = await client.post("/audit/retention", json={"older_than_days": 30})
        assert response.status_code == 200
        data = response.json()
        assert data["deleted_count"] == 1

        # Verify old event is gone, recent event remains.
        check = await client.get("/audit")
        types = [e["event_type"] for e in check.json()]
        assert "recent_event" in types
        assert "old_event" not in types

    async def test_retention_zero_days_returns_422(self, test_client):
        """POST /audit/retention with older_than_days=0 returns 422 (validation error)."""
        client, _ = test_client
        response = await client.post("/audit/retention", json={"older_than_days": 0})
        assert response.status_code == 422

    async def test_retention_returns_zero_when_nothing_to_delete(self, test_client):
        """POST /audit/retention returns deleted_count=0 when no events are old enough."""
        client, session_factory = test_client
        pid, sid = await _seed_pipeline(session_factory)
        await _seed_event(session_factory, pid, sid, "recent_event")

        response = await client.post("/audit/retention", json={"older_than_days": 30})
        assert response.status_code == 200
        assert response.json()["deleted_count"] == 0
