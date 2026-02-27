"""Pydantic schemas for the Audit Trail REST API."""

from datetime import datetime

from pydantic import BaseModel, Field


class AuditEventResponse(BaseModel):
    """Single audit event, with payload parsed from JSON string."""

    id: int
    pipeline_id: int
    step_id: int | None
    event_type: str
    payload: dict | None
    created_at: datetime


class RetentionRequest(BaseModel):
    """Request body for the retention cleanup endpoint."""

    older_than_days: int = Field(ge=1, description="Delete events older than this many days (minimum 1).")


class RetentionResponse(BaseModel):
    """Result of a retention cleanup operation."""

    deleted_count: int
