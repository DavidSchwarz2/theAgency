"""REST API router for the Audit Trail."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import delete, select
from sqlalchemy.engine.cursor import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AuditEvent
from app.schemas.audit import AuditEventResponse, RetentionRequest, RetentionResponse

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/audit", tags=["audit"])

_MAX_LIMIT = 500
_EXPORT_DEFAULT_LIMIT = 500


@dataclass
class AuditFilter:
    """Value object carrying all optional filters for audit event queries."""

    pipeline_id: int | None = None
    step_id: int | None = None
    event_type: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    limit: int = 100
    offset: int = 0


def _to_response(event: AuditEvent) -> AuditEventResponse:
    """Convert an ORM AuditEvent to its Pydantic response schema."""
    payload: dict | None = None
    if event.payload_json is not None:
        try:
            payload = json.loads(event.payload_json)
        except (json.JSONDecodeError, ValueError):
            logger.warning("audit_payload_corrupt", event_id=event.id)
    return AuditEventResponse(
        id=event.id,
        pipeline_id=event.pipeline_id,
        step_id=event.step_id,
        event_type=event.event_type,
        payload=payload,
        created_at=event.created_at,
    )


async def _query_audit_events(db: AsyncSession, filters: AuditFilter) -> list[AuditEvent]:
    """Build and execute a filtered audit event query. Returns ORM rows."""
    stmt = select(AuditEvent)
    if filters.pipeline_id is not None:
        stmt = stmt.where(AuditEvent.pipeline_id == filters.pipeline_id)
    if filters.step_id is not None:
        stmt = stmt.where(AuditEvent.step_id == filters.step_id)
    if filters.event_type is not None:
        stmt = stmt.where(AuditEvent.event_type == filters.event_type)
    if filters.since is not None:
        stmt = stmt.where(AuditEvent.created_at >= filters.since)
    if filters.until is not None:
        stmt = stmt.where(AuditEvent.created_at <= filters.until)
    stmt = stmt.order_by(AuditEvent.created_at.desc()).limit(min(filters.limit, _MAX_LIMIT)).offset(filters.offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# GET /audit — list audit events with filters
# ---------------------------------------------------------------------------


@router.get("", response_model=list[AuditEventResponse])
async def list_audit_events(
    db: Annotated[AsyncSession, Depends(get_db)],
    pipeline_id: int | None = None,
    step_id: int | None = None,
    event_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditEventResponse]:
    """Return audit events, newest first. Supports filtering by pipeline, step, event type, and date range."""
    filters = AuditFilter(
        pipeline_id=pipeline_id,
        step_id=step_id,
        event_type=event_type,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    events = await _query_audit_events(db, filters)
    return [_to_response(e) for e in events]


# ---------------------------------------------------------------------------
# GET /audit/export — download as JSON or Markdown
# ---------------------------------------------------------------------------


@router.get("/export")
async def export_audit_events(
    db: Annotated[AsyncSession, Depends(get_db)],
    export_format: Literal["json", "markdown"] = "json",
    pipeline_id: int | None = None,
    step_id: int | None = None,
    event_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = _EXPORT_DEFAULT_LIMIT,
    offset: int = 0,
) -> Response:
    """Export audit events as JSON or Markdown. Pass `?export_format=json` or `?export_format=markdown`."""
    filters = AuditFilter(
        pipeline_id=pipeline_id,
        step_id=step_id,
        event_type=event_type,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    events = await _query_audit_events(db, filters)
    responses = [_to_response(e) for e in events]

    if export_format == "json":
        body = json.dumps([r.model_dump(mode="json") for r in responses], indent=2)
        return Response(
            content=body,
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="audit.json"'},
        )

    # Markdown table
    lines = [
        "| id | pipeline_id | step_id | event_type | created_at | payload |",
        "|----|-------------|---------|------------|------------|---------|",
    ]
    for r in responses:
        payload_str = json.dumps(r.payload).replace("|", "\\|") if r.payload is not None else ""
        event_type_safe = r.event_type.replace("|", "\\|")
        created = r.created_at.isoformat()
        lines.append(
            f"| {r.id} | {r.pipeline_id} | {r.step_id or ''} | {event_type_safe} | {created} | {payload_str} |"
        )
    body = "\n".join(lines) + "\n"
    return Response(
        content=body,
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="audit.md"'},
    )


# ---------------------------------------------------------------------------
# POST /audit/retention — delete old events
# ---------------------------------------------------------------------------


@router.post("/retention", response_model=RetentionResponse, status_code=status.HTTP_200_OK)
async def apply_retention(
    body: RetentionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RetentionResponse:
    """Delete audit events older than `older_than_days` days. Returns the count of deleted rows."""
    cutoff = datetime.now(UTC) - timedelta(days=body.older_than_days)
    cursor: CursorResult = await db.execute(  # type: ignore[assignment]
        delete(AuditEvent).where(AuditEvent.created_at < cutoff)
    )
    await db.commit()
    deleted_count = cursor.rowcount
    logger.info("audit_retention_applied", older_than_days=body.older_than_days, deleted_count=deleted_count)
    return RetentionResponse(deleted_count=deleted_count)
