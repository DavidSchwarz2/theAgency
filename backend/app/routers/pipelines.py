"""REST API router for pipeline management."""

import asyncio
import collections.abc
import json
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters.github_client import GitHubClient, GitHubClientError
from app.adapters.github_models import GitHubIssue
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
from app.schemas.registry import AgentStep, ApprovalStep, PipelineTemplate
from app.services.agent_registry import AgentRegistry
from app.services.pipeline_runner import APPROVAL_SENTINEL, PipelineRunner

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


def get_opencode_client(request: Request) -> OpenCodeClient:
    """FastAPI dependency — reads from app.state.opencode_client."""
    return request.app.state.opencode_client


def _format_issue_context(issue: GitHubIssue) -> str:
    """Format a GitHubIssue into a Markdown context block for prompt prepending."""
    labels_part = ("\n\nLabels: " + ", ".join(issue.labels)) if issue.labels else ""
    return f"## GitHub Issue #{issue.number}: {issue.title}\n\n" + (issue.body or "") + labels_part


def _launch_pipeline_background_task(
    pipeline_id: int,
    app_state: object,
    client: OpenCodeClient,
    registry: "AgentRegistry",
    run_fn: "collections.abc.Callable[[PipelineRunner, Pipeline], collections.abc.Coroutine[object, object, None]]",
    log_event: str,
) -> None:
    """Create and register an asyncio background task for a pipeline run.

    Opens a fresh DB session, fetches the pipeline, wires a PipelineRunner, then calls
    `run_fn(runner, pipeline)` to dispatch the appropriate execution method
    (run_pipeline or resume_pipeline). Handles active_runners and approval_events cleanup.

    Must only be called from within a running event loop (i.e., inside a FastAPI handler).
    """
    db_session_factory = app_state.db_session_factory  # type: ignore[attr-defined]
    step_timeout: float = app_state.step_timeout  # type: ignore[attr-defined]

    async def _run() -> None:
        async with db_session_factory() as bg_db:
            result = await bg_db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))
            bg_pipeline = result.scalar_one()
            runner = PipelineRunner(
                client=client,
                db=bg_db,
                step_timeout=step_timeout,
                registry=registry,
                approval_events=app_state.approval_events,  # type: ignore[attr-defined]
            )
            app_state.active_runners[pipeline_id] = runner  # type: ignore[attr-defined]
            try:
                await run_fn(runner, bg_pipeline)
            except Exception:
                logger.error("pipeline_task_unhandled_error", pipeline_id=pipeline_id, exc_info=True)
                try:
                    # Only overwrite the status if the pipeline was not already transitioned
                    # to a terminal state by _execute_steps / _mark_pipeline_failed — e.g. when
                    # an unexpected exception fires after the runner has already marked it done.
                    if bg_pipeline.status not in (PipelineStatus.done, PipelineStatus.failed):
                        bg_pipeline.status = PipelineStatus.failed
                        bg_pipeline.updated_at = datetime.now(UTC)
                        await bg_db.commit()
                except Exception:
                    logger.error("pipeline_task_status_update_failed", pipeline_id=pipeline_id, exc_info=True)
            finally:
                app_state.active_runners.pop(pipeline_id, None)  # type: ignore[attr-defined]
                app_state.approval_events.pop(pipeline_id, None)  # type: ignore[attr-defined]
                logger.info(log_event, pipeline_id=pipeline_id)

    task = asyncio.create_task(_run())
    app_state.pipeline_tasks[pipeline_id] = task  # type: ignore[attr-defined]
    task.add_done_callback(lambda t: app_state.pipeline_tasks.pop(pipeline_id, None))  # type: ignore[attr-defined]


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
    # ---- Merge local agents from working_dir if provided (Issue #14) ----
    if body.working_dir:
        effective_registry = registry.merge_with_local(body.working_dir)
    else:
        effective_registry = registry

    # ---- Resolve template or build one from custom steps (Issue #16) ----
    if body.template is not None:
        template: PipelineTemplate | None = effective_registry.get_pipeline(body.template)
        if template is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Unknown pipeline template: {body.template!r}",
            )
        template_name = body.template
    else:
        # Custom steps — body.custom_steps is guaranteed non-None by schema validator
        if not body.custom_steps:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="custom_steps must not be empty",
            )
        steps: list[AgentStep | ApprovalStep] = []
        for cs in body.custom_steps:
            if cs.type == "agent":
                if effective_registry.get_agent(cs.agent) is None:  # type: ignore[arg-type]
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail=f"Unknown agent: {cs.agent!r}",
                    )
                steps.append(AgentStep(agent=cs.agent, model=cs.model))  # type: ignore[arg-type]
            else:
                steps.append(ApprovalStep(type="approval"))
        template = PipelineTemplate(name="__custom__", description="", steps=steps)
        template_name = "__custom__"

    # ---- Enrich prompt with GitHub issue context if requested (Issue #13) ----
    enriched_prompt = body.prompt
    if body.github_issue_repo and body.github_issue_number is not None:
        github_client: GitHubClient | None = request.app.state.github_client
        if github_client is None:
            logger.info(
                "github_issue_skipped_no_token",
                repo=body.github_issue_repo,
                number=body.github_issue_number,
            )
        else:
            try:
                issue = await github_client.get_issue(body.github_issue_repo, body.github_issue_number)
                issue_block = _format_issue_context(issue)
                enriched_prompt = issue_block + "\n\n---\n\n" + body.prompt
            except GitHubClientError:
                logger.warning(
                    "github_issue_fetch_failed",
                    repo=body.github_issue_repo,
                    number=body.github_issue_number,
                    exc_info=True,
                )

    # ---- Persist the pipeline and its steps ----
    now = datetime.now(UTC)
    pipeline = Pipeline(
        title=body.title,
        template=template_name,
        prompt=enriched_prompt,
        working_dir=body.working_dir,
        status=PipelineStatus.running,
        created_at=now,
        updated_at=now,
    )
    db.add(pipeline)
    await db.flush()

    for idx, step_def in enumerate(template.steps):
        agent_name = step_def.agent if isinstance(step_def, AgentStep) else APPROVAL_SENTINEL
        # Resolve model: explicit per-step override first, then step-level model, then agent default.
        step_model: str | None = (body.step_models or {}).get(idx)
        if step_model is None and isinstance(step_def, AgentStep):
            # Use step-level model from custom step if provided
            if step_def.model is not None:
                step_model = step_def.model
            else:
                agent_profile = effective_registry.get_agent(step_def.agent)
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

    # Create an approval event for this pipeline before launching the background task.
    app_state.approval_events[pipeline_id] = asyncio.Event()

    captured_template = template

    _launch_pipeline_background_task(
        pipeline_id=pipeline_id,
        app_state=app_state,
        client=client,
        registry=effective_registry,
        run_fn=lambda runner, p: runner.run_pipeline(p, captured_template),
        log_event="pipeline_background_task_done",
    )

    return PipelineResponse.model_validate(pipeline)


# ---------------------------------------------------------------------------
# GET /pipelines/conflicts — find active pipelines sharing a working_dir
# ---------------------------------------------------------------------------


@router.get("/conflicts", response_model=list[PipelineResponse])
async def get_pipeline_conflicts(
    db: Annotated[AsyncSession, Depends(get_db)],
    working_dir: str | None = None,
) -> list[PipelineResponse]:
    """Return active pipelines (running or waiting_for_approval) that share working_dir.

    Returns an empty list when working_dir is absent or empty.
    """
    if not working_dir:
        return []
    result = await db.execute(
        select(Pipeline)
        .where(
            Pipeline.working_dir == working_dir,
            Pipeline.status.in_([PipelineStatus.running, PipelineStatus.waiting_for_approval]),
        )
        .order_by(Pipeline.id.desc())
    )
    return result.scalars().all()  # type: ignore[return-value]


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
                error_message=step.error_message,
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
# POST /pipelines/{id}/restart — restart a failed pipeline
# ---------------------------------------------------------------------------


@router.post("/{pipeline_id}/restart", response_model=PipelineResponse)
async def restart_pipeline(
    pipeline_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    registry: Annotated[AgentRegistry, Depends(get_registry)],
    client: Annotated[OpenCodeClient, Depends(get_opencode_client)],
    request: Request,
) -> PipelineResponse:
    """Restart a failed pipeline from the first non-completed step. Returns 409 if not failed."""
    result = await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))
    pipeline = result.scalar_one_or_none()
    if pipeline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    if pipeline.status != PipelineStatus.failed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Pipeline is not failed (status={pipeline.status})",
        )

    pipeline.status = PipelineStatus.running
    pipeline.updated_at = datetime.now(UTC)
    await db.commit()

    app_state = request.app.state
    # Create an approval event for this pipeline before launching the background task.
    app_state.approval_events[pipeline_id] = asyncio.Event()

    _launch_pipeline_background_task(
        pipeline_id=pipeline_id,
        app_state=app_state,
        client=client,
        registry=registry,
        # template=None: resume_pipeline does not use the template; it reconstructs
        # the prompt from stored handoff records in the database.
        run_fn=lambda runner, p: runner.resume_pipeline(p, template=None),
        log_event="pipeline_restart_task_done",
    )

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
