"""REST API router for pipeline management."""

import asyncio
import json
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters.opencode_client import OpenCodeClient
from app.database import get_db
from app.models import Approval, ApprovalStatus, Pipeline, PipelineStatus, Step, StepStatus
from app.routers.registry import get_registry
from app.schemas.pipeline import (
    ApproveRequest,
    HandoffResponse,
    PipelineCreateRequest,
    PipelineDetailResponse,
    PipelineResponse,
    RejectRequest,
    StepStatusResponse,
)
from app.schemas.registry import AgentStep, PipelineTemplate
from app.services.agent_registry import AgentRegistry
from app.services.pipeline_runner import APPROVAL_SENTINEL, PipelineRunner

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


def get_opencode_client(request: Request) -> OpenCodeClient:
    """FastAPI dependency — reads from app.state.opencode_client."""
    return request.app.state.opencode_client


# ---------------------------------------------------------------------------
# GET /pipelines — list all pipelines
# ---------------------------------------------------------------------------


@router.get("", response_model=list[PipelineResponse])
async def list_pipelines(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PipelineResponse]:
    """Return all pipelines ordered by id descending (most recent first)."""
    result = await db.execute(select(Pipeline).order_by(Pipeline.id.desc()))
    pipelines = result.scalars().all()
    return pipelines  # type: ignore[return-value]  # FastAPI serialises via response_model


# ---------------------------------------------------------------------------
# POST /pipelines — create and launch a new pipeline
# ---------------------------------------------------------------------------


@router.post("", response_model=PipelineResponse, status_code=status.HTTP_201_CREATED)
async def create_pipeline(
    body: PipelineCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    registry: Annotated[AgentRegistry, Depends(get_registry)],
    client: Annotated[OpenCodeClient, Depends(get_opencode_client)],
    request: Request,
) -> PipelineResponse:
    """Create a pipeline and immediately launch it as a background task."""
    template: PipelineTemplate | None = registry.get_pipeline(body.template)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown pipeline template: {body.template!r}",
        )

    # Persist the pipeline and its steps.
    now = datetime.now(UTC)
    pipeline = Pipeline(
        title=body.title,
        template=body.template,
        prompt=body.prompt,
        working_dir=body.working_dir,
        status=PipelineStatus.running,
        created_at=now,
        updated_at=now,
    )
    db.add(pipeline)
    await db.flush()

    for idx, step_def in enumerate(template.steps):
        agent_name = step_def.agent if isinstance(step_def, AgentStep) else APPROVAL_SENTINEL
        # Resolve model: explicit per-step override first, then agent default.
        step_model: str | None = (body.step_models or {}).get(idx)
        if step_model is None and isinstance(step_def, AgentStep):
            agent_profile = registry.get_agent(step_def.agent)
            step_model = agent_profile.default_model if agent_profile is not None else None
        step = Step(
            pipeline_id=pipeline.id,
            agent_name=agent_name,
            order_index=idx,
            status=StepStatus.pending,
            model=step_model,
        )
        db.add(step)

    await db.commit()

    pipeline_id = pipeline.id

    # Extract long-lived references before spawning the task — the Request object
    # is ASGI-scoped and must not be accessed after the response is sent.
    app_state = request.app.state
    db_session_factory = app_state.db_session_factory
    step_timeout: float = app_state.step_timeout

    # Create an approval event for this pipeline before launching the background task.
    approval_event: asyncio.Event = asyncio.Event()
    app_state.approval_events[pipeline_id] = approval_event

    async def _run_in_background() -> None:
        async with db_session_factory() as bg_db:
            result = await bg_db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))
            bg_pipeline = result.scalar_one()
            runner = PipelineRunner(
                client=client,
                db=bg_db,
                step_timeout=step_timeout,
                registry=registry,
                approval_events=app_state.approval_events,
            )
            app_state.active_runners[pipeline_id] = runner
            try:
                await runner.run_pipeline(bg_pipeline, template)
            finally:
                app_state.active_runners.pop(pipeline_id, None)
                app_state.approval_events.pop(pipeline_id, None)
                logger.info("pipeline_background_task_done", pipeline_id=pipeline_id)

    task = asyncio.create_task(_run_in_background())
    app_state.pipeline_tasks[pipeline_id] = task
    task.add_done_callback(lambda t: app_state.pipeline_tasks.pop(pipeline_id, None))

    return PipelineResponse.model_validate(pipeline)


# ---------------------------------------------------------------------------
# GET /pipelines/{id} — fetch pipeline detail with steps
# ---------------------------------------------------------------------------


@router.get("/{pipeline_id}", response_model=PipelineDetailResponse)
async def get_pipeline(
    pipeline_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PipelineDetailResponse:
    """Return a pipeline with its steps and latest handoff per step, or 404 if not found."""
    result = await db.execute(
        select(Pipeline)
        .options(selectinload(Pipeline.steps).selectinload(Step.handoffs))
        .where(Pipeline.id == pipeline_id)
    )
    pipeline = result.scalar_one_or_none()
    if pipeline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    step_responses = []
    for step in sorted(pipeline.steps, key=lambda s: s.order_index):
        latest = max(step.handoffs, key=lambda h: h.id) if step.handoffs else None
        metadata = json.loads(latest.metadata_json) if latest and latest.metadata_json else None
        handoff_resp = (
            HandoffResponse(
                id=latest.id,
                content_md=latest.content_md,
                metadata=metadata,
                created_at=latest.created_at,
            )
            if latest
            else None
        )
        step_responses.append(
            StepStatusResponse(
                id=step.id,
                agent_name=step.agent_name,
                order_index=step.order_index,
                status=step.status,
                model=step.model,
                started_at=step.started_at,
                finished_at=step.finished_at,
                latest_handoff=handoff_resp,
            )
        )

    return PipelineDetailResponse.model_validate({**pipeline.__dict__, "steps": step_responses})


# ---------------------------------------------------------------------------
# POST /pipelines/{id}/abort — abort a running pipeline
# ---------------------------------------------------------------------------


@router.post("/{pipeline_id}/abort", response_model=PipelineResponse)
async def abort_pipeline(
    pipeline_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    client: Annotated[OpenCodeClient, Depends(get_opencode_client)],
    request: Request,
) -> PipelineResponse:
    """Abort a running pipeline. Returns 409 if the pipeline is not running."""
    result = await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))
    pipeline = result.scalar_one_or_none()
    if pipeline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    if pipeline.status != PipelineStatus.running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Pipeline is not running (status={pipeline.status})",
        )

    app_state = request.app.state

    # Abort the active OpenCode session if there is one.
    runner: PipelineRunner | None = app_state.active_runners.get(pipeline_id)
    if runner is not None:
        session_id = runner.current_session_id
        if session_id is not None:
            try:
                await client.abort_session(session_id)
            except Exception as exc:
                logger.warning("abort_session_failed", pipeline_id=pipeline_id, session_id=session_id, exc_info=exc)

    # Cancel only this pipeline's background task.
    task = app_state.pipeline_tasks.get(pipeline_id)
    if task is not None and not task.done():
        task.cancel()

    pipeline.status = PipelineStatus.failed
    pipeline.updated_at = datetime.now(UTC)
    await db.commit()

    return PipelineResponse.model_validate(pipeline)


# ---------------------------------------------------------------------------
# Private helper shared by approve and reject endpoints
# ---------------------------------------------------------------------------


async def _handle_approval_decision(
    pipeline_id: int,
    decision: ApprovalStatus,
    comment: str | None,
    decided_by: str | None,
    db: AsyncSession,
    request: Request,
) -> PipelineResponse:
    """Core logic for approve / reject: validates state, updates DB, fires event."""
    result = await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))
    pipeline = result.scalar_one_or_none()
    if pipeline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    if pipeline.status != PipelineStatus.waiting_for_approval:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Pipeline is not waiting for approval (status={pipeline.status})",
        )

    approval_result = await db.execute(
        select(Approval).join(Step).where(Step.pipeline_id == pipeline_id, Approval.status == ApprovalStatus.pending)
    )
    approval = approval_result.scalar_one_or_none()
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No pending approval found")

    approval.status = decision
    approval.comment = comment
    approval.decided_by = decided_by
    approval.decided_at = datetime.now(UTC)
    await db.commit()

    # Signal the background runner to resume.
    app_state = request.app.state
    event: asyncio.Event | None = app_state.approval_events.get(pipeline_id)
    if event is None:
        # Server restarted — create a pre-set event so the runner doesn't deadlock.
        event = asyncio.Event()
        event.set()
        app_state.approval_events[pipeline_id] = event
    else:
        event.set()

    logger.info("pipeline_approval_decision", pipeline_id=pipeline_id, decision=decision, decided_by=decided_by)
    return PipelineResponse.model_validate(pipeline)


# ---------------------------------------------------------------------------
# POST /pipelines/{id}/approve — approve a paused pipeline
# ---------------------------------------------------------------------------


@router.post("/{pipeline_id}/approve", response_model=PipelineResponse)
async def approve_pipeline(
    pipeline_id: int,
    body: ApproveRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> PipelineResponse:
    """Approve a pipeline waiting for human sign-off. Returns 409 if not waiting."""
    return await _handle_approval_decision(
        pipeline_id=pipeline_id,
        decision=ApprovalStatus.approved,
        comment=body.comment,
        decided_by=body.decided_by,
        db=db,
        request=request,
    )


# ---------------------------------------------------------------------------
# POST /pipelines/{id}/reject — reject a paused pipeline
# ---------------------------------------------------------------------------


@router.post("/{pipeline_id}/reject", response_model=PipelineResponse)
async def reject_pipeline(
    pipeline_id: int,
    body: RejectRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> PipelineResponse:
    """Reject a pipeline waiting for human sign-off. Returns 409 if not waiting."""
    return await _handle_approval_decision(
        pipeline_id=pipeline_id,
        decision=ApprovalStatus.rejected,
        comment=body.comment,
        decided_by=body.decided_by,
        db=db,
        request=request,
    )
