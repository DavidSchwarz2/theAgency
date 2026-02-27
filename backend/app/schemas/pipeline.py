"""Pydantic schemas for the Pipeline REST API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from app.models import ApprovalStatus, PipelineStatus, StepStatus


class CustomStepInput(BaseModel):
    """A single step in a custom (non-template) pipeline."""

    type: Literal["agent", "approval"] = "agent"
    agent: str | None = None
    model: str | None = None

    @model_validator(mode="after")
    def _agent_required_for_agent_steps(self) -> "CustomStepInput":
        if self.type == "agent" and not self.agent:
            raise ValueError("agent is required when type='agent'")
        return self


class PipelineCreateRequest(BaseModel):
    template: str | None = None
    custom_steps: list[CustomStepInput] | None = None
    title: str
    prompt: str
    branch: str | None = None
    step_models: dict[int, str] | None = None
    working_dir: str | None = None
    github_issue_repo: str | None = None
    github_issue_number: int | None = None

    @model_validator(mode="after")
    def _exactly_one_of_template_or_custom_steps(self) -> "PipelineCreateRequest":
        has_template = self.template is not None
        has_custom = self.custom_steps is not None
        if has_template and has_custom:
            raise ValueError("Provide either 'template' or 'custom_steps', not both")
        if not has_template and not has_custom:
            raise ValueError("One of 'template' or 'custom_steps' is required")
        return self


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
    branch: str | None = None
    working_dir: str | None = None


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
