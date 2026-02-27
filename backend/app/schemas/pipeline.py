"""Pydantic schemas for the Pipeline REST API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import ApprovalStatus, PipelineStatus, StepStatus


class PipelineCreateRequest(BaseModel):
    template: str
    title: str
    prompt: str
    branch: str | None = None
    step_models: dict[int, str] | None = None


class HandoffResponse(BaseModel):
    """Handoff data for a single step.

    Constructed manually — not via ORM auto-mapping, because the ORM Handoff model
    stores metadata as a JSON string (metadata_json) while this schema exposes it
    as a parsed dict.
    """

    id: int
    content_md: str
    metadata: dict | None = None
    created_at: datetime


class StepStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_name: str
    order_index: int
    status: StepStatus
    model: str | None = None
    started_at: datetime | None
    finished_at: datetime | None
    latest_handoff: HandoffResponse | None = None


class PipelineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    template: str
    status: PipelineStatus
    created_at: datetime
    updated_at: datetime


class PipelineDetailResponse(PipelineResponse):
    steps: list[StepStatusResponse]


class ApprovalDecisionRequest(BaseModel):
    """Shared body for approve and reject endpoints."""

    comment: str | None = None
    decided_by: str | None = None


# Kept as distinct names so API docs and call sites remain explicit.
class ApproveRequest(ApprovalDecisionRequest):
    pass


class RejectRequest(ApprovalDecisionRequest):
    pass


class ApprovalResponse(BaseModel):
    id: int
    pipeline_id: int
    step_id: int
    status: ApprovalStatus
    comment: str | None
    decided_by: str | None
    decided_at: datetime | None
