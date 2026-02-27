"""Pydantic schemas for the Pipeline REST API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import PipelineStatus, StepStatus


class PipelineCreateRequest(BaseModel):
    template: str
    title: str
    prompt: str
    branch: str | None = None


class StepStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_name: str
    order_index: int
    status: StepStatus
    started_at: datetime | None
    finished_at: datetime | None


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
