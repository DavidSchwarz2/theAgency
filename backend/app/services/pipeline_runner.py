"""PipelineRunner — core orchestration service for sequential agent pipelines."""

import asyncio
import json
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.adapters.opencode_client import OpenCodeClient, OpenCodeClientError
from app.adapters.opencode_models import MessageResponse
from app.models import Approval, ApprovalStatus, AuditEvent, Handoff, Pipeline, PipelineStatus, Step, StepStatus
from app.schemas.handoff import HandoffSchema
from app.schemas.registry import AgentProfile, ApprovalStep, PipelineStep, PipelineTemplate
from app.services.agent_registry import AgentRegistry
from app.services.handoff_extractor import HandoffExtractor

logger = structlog.get_logger(__name__)

APPROVAL_SENTINEL = "__approval__"


class StepExecutionError(Exception):
    """Raised when a pipeline step fails in an unrecoverable way."""


class PipelineRunner:
    """Orchestrates the execution of pipeline steps against an OpenCode instance.

    Each step creates an isolated OpenCode session, sends the accumulated prompt to
    the designated agent role, waits for a synchronous response, persists the output
    as a Handoff record, and updates the Step status in the database.

    The runner is deliberately stateless across pipeline runs — construct a fresh
    instance per pipeline execution so that session IDs don't leak between runs.
    """

    def __init__(
        self,
        client: OpenCodeClient,
        db: AsyncSession,
        step_timeout: float = 600,
        registry: "AgentRegistry | None" = None,
        extractor: "HandoffExtractor | None" = None,
        approval_events: "dict[int, asyncio.Event] | None" = None,
    ) -> None:
        self._client = client
        self._db = db
        self._step_timeout = step_timeout
        self._registry = registry
        self._extractor = extractor or HandoffExtractor()
        self._current_session_id: str | None = None
        self._approval_events: dict[int, asyncio.Event] = approval_events if approval_events is not None else {}

    @property
    def current_session_id(self) -> str | None:
        """The active OpenCode session ID, or None when no step is running."""
        return self._current_session_id

    async def run_step(
        self,
        step: Step,
        agent_profile: AgentProfile,
        prompt: str,
        model: str | None = None,
        working_dir: str | None = None,
    ) -> tuple[str, HandoffSchema | None]:
        """Execute one step synchronously.

        Creates an OpenCode session, sends the prompt to the agent, waits for the
        response, persists a Handoff record, and updates the step status.

        Returns a tuple of (output_text, handoff_schema). handoff_schema is None
        if structured extraction failed.
        Raises StepExecutionError on failure or timeout.
        """
        session_info = await self._client.create_session(title=f"{step.agent_name}-{step.id}")
        session_id = session_info.id
        self._current_session_id = session_id

        full_prompt = self._build_prompt(prompt, agent_profile, working_dir)

        try:
            response: MessageResponse = await asyncio.wait_for(
                self._client.send_message(
                    session_id,
                    prompt=full_prompt,
                    agent=agent_profile.opencode_agent,
                    model=model,
                ),
                timeout=self._step_timeout,
            )
            output_text = self._extract_output(response)
            handoff_schema = await self._persist_success(step, output_text)
            return output_text, handoff_schema

        except TimeoutError:
            logger.warning("step_timeout", step_id=step.id, timeout=self._step_timeout)
            await self._client.abort_session(session_id)
            await self._persist_failure(step, error=f"Step timed out after {self._step_timeout}s")
            raise StepExecutionError(f"Step {step.id} timed out after {self._step_timeout}s") from None

        except OpenCodeClientError as exc:
            logger.warning("step_client_error", step_id=step.id, error=str(exc))
            await self._persist_failure(step, error=str(exc))
            raise StepExecutionError(f"Step {step.id} failed: {exc}") from exc

        finally:
            self._current_session_id = None
            try:
                await self._client.delete_session(session_id)
            except Exception:
                logger.warning("delete_session_failed", session_id=session_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(prompt: str, agent_profile: AgentProfile, working_dir: str | None) -> str:
        """Assemble the full prompt sent to OpenCode.

        Prepends a working-directory preamble when ``working_dir`` is not None,
        then prepends ``agent_profile.system_prompt_additions`` if present.
        """
        parts: list[str] = []
        if working_dir is not None:
            parts.append(f"Working directory: {working_dir} — treat this as the project root for all file operations.")
        if agent_profile.system_prompt_additions:
            parts.append(agent_profile.system_prompt_additions)
        parts.append(prompt)
        return "\n\n".join(parts)

    def _extract_output(self, response: MessageResponse) -> str:
        """Extract text content from a MessageResponse.

        Concatenates all text parts in the response. Returns an empty string if no
        text content is found, and logs a warning in that case.
        """
        texts = [part.content for part in response.parts if part.type == "text" and part.content is not None]
        if not texts:
            logger.warning("no_text_content_in_response", parts=len(response.parts))
            return ""
        return "\n".join(texts)

    async def _persist_success(self, step: Step, output_text: str) -> HandoffSchema | None:
        handoff_schema = self._extractor.extract(output_text)

        handoff = Handoff(
            step_id=step.id,
            content_md=output_text,
            metadata_json=handoff_schema.model_dump_json(exclude_none=True) if handoff_schema is not None else None,
        )
        self._db.add(handoff)
        step.status = StepStatus.done
        step.finished_at = datetime.now(UTC)
        await self._db.flush()  # assigns handoff.id before we reference it in audit payload

        audit_created = AuditEvent(
            pipeline_id=step.pipeline_id,
            step_id=step.id,
            event_type="handoff_created",
            payload_json=json.dumps({"handoff_id": handoff.id, "has_structured_data": handoff_schema is not None}),
        )
        self._db.add(audit_created)

        if handoff_schema is None:
            audit_failed = AuditEvent(
                pipeline_id=step.pipeline_id,
                step_id=step.id,
                event_type="handoff_extraction_failed",
                payload_json=json.dumps({"handoff_id": handoff.id}),
            )
            self._db.add(audit_failed)

        await self._db.commit()
        return handoff_schema

    async def _persist_failure(self, step: Step, error: str | None = None) -> None:
        step.status = StepStatus.failed
        step.finished_at = datetime.now(UTC)
        step.error_message = error
        audit_failed = AuditEvent(
            pipeline_id=step.pipeline_id,
            step_id=step.id,
            event_type="step_failed",
            payload_json=json.dumps({"error_message": error}),
        )
        self._db.add(audit_failed)
        await self._db.commit()

    async def _mark_pipeline_failed(self, pipeline: Pipeline, step: Step | None = None) -> None:
        """Mark pipeline (and optionally a step) as failed and commit."""
        if step is not None:
            step.status = StepStatus.failed
            step.finished_at = datetime.now(UTC)
        pipeline.status = PipelineStatus.failed
        pipeline.updated_at = datetime.now(UTC)
        await self._db.commit()

    async def _execute_approval_step(
        self,
        step: Step,
        pipeline: Pipeline,
        current_prompt: str,
        remind_after_hours: float | None = None,
    ) -> str | None:
        """Handle an approval gate step.

        Creates an Approval record, sets the pipeline to waiting_for_approval, and
        awaits the approval_event for this pipeline. Returns the updated prompt on
        approval (with optional comment appended), or None on rejection.

        If remind_after_hours is set, a one-shot reminder fires after that many hours:
        an approval_reminder AuditEvent is written and a warning is logged, then the
        runner continues to wait indefinitely. The pipeline is never auto-rejected.

        Callers must check the return value: None means the pipeline should be aborted.
        """
        step.status = StepStatus.running
        step.started_at = datetime.now(UTC)

        approval = Approval(
            step_id=step.id,
            status=ApprovalStatus.pending,
        )
        self._db.add(approval)

        audit_requested = AuditEvent(
            pipeline_id=pipeline.id,
            step_id=step.id,
            event_type="approval_requested",
            payload_json=json.dumps({"step_id": step.id}),
        )
        self._db.add(audit_requested)

        pipeline.status = PipelineStatus.waiting_for_approval
        pipeline.updated_at = datetime.now(UTC)
        await self._db.commit()

        logger.info("approval_step_waiting", pipeline_id=pipeline.id, step_id=step.id)

        # Retrieve or create an event for this pipeline.
        event = self._approval_events.get(pipeline.id)
        if event is None:
            # No event registered — this is a programmer error (the caller should always
            # register an event before running a pipeline). Log a warning and create a
            # fallback event so the pipeline doesn't crash; it will wait indefinitely.
            logger.warning("approval_event_missing", pipeline_id=pipeline.id, step_id=step.id)
            event = asyncio.Event()
            self._approval_events[pipeline.id] = event

        if remind_after_hours is not None:
            timeout_secs = remind_after_hours * 3600
            try:
                # shield() prevents wait_for from cancelling the inner coroutine when
                # the timeout fires — the event remains valid for the second wait below.
                await asyncio.wait_for(asyncio.shield(event.wait()), timeout=timeout_secs)
            except TimeoutError:
                logger.warning(
                    "approval_reminder_fired",
                    pipeline_id=pipeline.id,
                    step_id=step.id,
                    remind_after_hours=remind_after_hours,
                )
                audit_reminder = AuditEvent(
                    pipeline_id=pipeline.id,
                    step_id=step.id,
                    event_type="approval_reminder",
                    payload_json=json.dumps({"remind_after_hours": remind_after_hours}),
                )
                self._db.add(audit_reminder)
                await self._db.commit()
                # Continue waiting indefinitely after the reminder.
                await event.wait()
        else:
            await event.wait()

        # Re-read the approval from the DB to get the decision.
        await self._db.refresh(approval)

        if approval.status == ApprovalStatus.approved:
            step.status = StepStatus.done
            step.finished_at = datetime.now(UTC)
            pipeline.status = PipelineStatus.running
            pipeline.updated_at = datetime.now(UTC)

            audit_granted = AuditEvent(
                pipeline_id=pipeline.id,
                step_id=step.id,
                event_type="approval_granted",
                payload_json=json.dumps({"decided_by": approval.decided_by, "comment": approval.comment}),
            )
            self._db.add(audit_granted)
            await self._db.commit()

            # Append comment to next prompt if provided.
            if approval.comment:
                return f"{current_prompt}\n\n[Approval note: {approval.comment}]"
            return current_prompt

        elif approval.status == ApprovalStatus.rejected:
            # Rejected
            audit_rejected = AuditEvent(
                pipeline_id=pipeline.id,
                step_id=step.id,
                event_type="approval_rejected",
                payload_json=json.dumps({"decided_by": approval.decided_by, "comment": approval.comment}),
            )
            self._db.add(audit_rejected)
            await self._mark_pipeline_failed(pipeline, step)

            logger.info("approval_step_rejected", pipeline_id=pipeline.id, step_id=step.id)
            return None

        else:
            # Unexpected status — should never happen; treat as rejection and log prominently.
            logger.error(
                "approval_unexpected_status",
                pipeline_id=pipeline.id,
                step_id=step.id,
                approval_status=approval.status,
            )
            await self._mark_pipeline_failed(pipeline, step)
            return None

    async def _execute_steps(
        self,
        steps: list[Step],
        initial_prompt: str,
        pipeline: Pipeline,
        template_steps: list[PipelineStep] | None = None,
    ) -> None:
        """Execute a list of steps sequentially, chaining output as the next prompt.

        Updates `pipeline.status` to `failed` and returns early on any error.
        Sets `pipeline.status` to `done` if all steps complete successfully.

        template_steps, if provided, is a list of PipelineStep schema objects (AgentStep
        or ApprovalStep) in the same order as `steps`. When present, the runner uses the
        template step's configuration (e.g. remind_after_hours for approval gates).
        """
        if self._registry is None:
            raise ValueError("_execute_steps requires a registry")

        current_prompt = initial_prompt

        for i, step in enumerate(steps):
            # Approval gate step — pause and wait for a human decision.
            if step.agent_name == APPROVAL_SENTINEL:
                remind_after_hours: float | None = None
                if template_steps is not None:
                    if i < len(template_steps):
                        tpl_step = template_steps[i]
                        if isinstance(tpl_step, ApprovalStep):
                            remind_after_hours = tpl_step.remind_after_hours
                    else:
                        logger.warning(
                            "approval_step_template_mismatch",
                            step_index=i,
                            template_steps_count=len(template_steps),
                            step_id=step.id,
                        )
                result_prompt = await self._execute_approval_step(
                    step, pipeline, current_prompt, remind_after_hours=remind_after_hours
                )
                if result_prompt is None:
                    # Rejected — pipeline already marked failed in _execute_approval_step.
                    return
                current_prompt = result_prompt
                continue

            step.status = StepStatus.running
            step.started_at = datetime.now(UTC)
            await self._db.commit()

            agent_profile = self._registry.get_agent(step.agent_name)
            if agent_profile is None:
                logger.error("unknown_agent", agent_name=step.agent_name, step_id=step.id)
                await self._mark_pipeline_failed(pipeline, step)
                return

            try:
                # The router resolves the model at pipeline creation time and persists it on
                # Step.model, so `step.model` is the authoritative value in normal operation.
                # The `or agent_profile.default_model` fallback handles the crash-recovery
                # (resume_pipeline) path where a step was created before this feature existed.
                output_text, handoff_schema = await self.run_step(
                    step,
                    agent_profile,
                    current_prompt,
                    model=step.model or agent_profile.default_model,
                    working_dir=pipeline.working_dir,
                )
                if handoff_schema is not None:
                    current_prompt = handoff_schema.to_context_header(agent_name=step.agent_name)
                else:
                    current_prompt = output_text
            except StepExecutionError as exc:
                logger.error("step_execution_error", pipeline_id=pipeline.id, step_id=step.id, error=str(exc))
                await self._mark_pipeline_failed(pipeline)
                return

        pipeline.status = PipelineStatus.done
        pipeline.updated_at = datetime.now(UTC)
        await self._db.commit()

    # ------------------------------------------------------------------
    # Pipeline-level execution (Milestone 2)
    # ------------------------------------------------------------------

    async def run_pipeline(
        self,
        pipeline: Pipeline,
        template: PipelineTemplate,
    ) -> None:
        """Execute all steps in a pipeline sequentially.

        Reads the initial prompt from `pipeline.prompt`. Passes each step's output
        as the next step's prompt (handoff chaining). Updates `pipeline.status` to
        `done` on full success or `failed` on any step error.
        """
        if self._registry is None:
            raise ValueError("run_pipeline requires a registry")

        # Eagerly load steps to avoid lazy-loading outside async greenlet context.
        # We use `loaded_pipeline` only to access steps; status updates go to the
        # caller-supplied `pipeline` object which remains tracked by the session.
        result = await self._db.execute(
            select(Pipeline).options(selectinload(Pipeline.steps)).where(Pipeline.id == pipeline.id)
        )
        loaded_pipeline = result.scalar_one()
        steps = sorted(loaded_pipeline.steps, key=lambda s: s.order_index)

        await self._execute_steps(steps, loaded_pipeline.prompt, pipeline, template_steps=template.steps)

    # ------------------------------------------------------------------
    # Crash recovery (Milestone 3)
    # ------------------------------------------------------------------

    async def resume_pipeline(
        self,
        pipeline: Pipeline,
        template: "PipelineTemplate | None",
    ) -> None:
        """Resume a pipeline from the first non-done step.

        Loads steps eagerly. Uses the last completed step's Handoff content as the
        prompt for the next pending step, falling back to `pipeline.prompt` if no
        steps are done yet. If all steps are already done, marks the pipeline done
        immediately without calling OpenCode.
        """
        if self._registry is None:
            raise ValueError("resume_pipeline requires a registry")

        # Eagerly load steps and their handoffs to avoid lazy-loading issues.
        result = await self._db.execute(
            select(Pipeline)
            .options(selectinload(Pipeline.steps).selectinload(Step.handoffs))
            .where(Pipeline.id == pipeline.id)
        )
        loaded_pipeline = result.scalar_one()
        steps = sorted(loaded_pipeline.steps, key=lambda s: s.order_index)

        # Find the last done step and extract its handoff content.
        current_prompt = loaded_pipeline.prompt
        for step in steps:
            if step.status == StepStatus.done and step.handoffs:
                # Use the most recently created handoff
                latest_handoff = max(step.handoffs, key=lambda h: h.id)
                if latest_handoff.metadata_json:
                    schema = HandoffSchema.model_validate_json(latest_handoff.metadata_json)
                    current_prompt = schema.to_context_header(agent_name=step.agent_name)
                else:
                    current_prompt = latest_handoff.content_md

        # Find the first non-done step.
        remaining = [s for s in steps if s.status != StepStatus.done]
        if not remaining:
            pipeline.status = PipelineStatus.done
            pipeline.updated_at = datetime.now(UTC)
            await self._db.commit()
            return

        await self._execute_steps(remaining, current_prompt, pipeline)


# ------------------------------------------------------------------
# Module-level utility: crash recovery on startup
# ------------------------------------------------------------------


async def recover_interrupted_pipelines(
    db_session_factory: "async_sessionmaker[AsyncSession]",
    client: OpenCodeClient,
    registry: "AgentRegistry",
    task_set: "dict[int, asyncio.Task]",  # type: ignore[type-arg]
    step_timeout: float = 600,
) -> None:
    """Find all pipelines stuck in 'running' status and re-queue them as background tasks.

    Called from the FastAPI lifespan after the registry and OpenCode client are
    initialized. Each interrupted pipeline gets a fresh PipelineRunner with its
    own DB session so background tasks don't share request-scoped sessions.
    """
    async with db_session_factory() as db:
        result = await db.execute(select(Pipeline).where(Pipeline.status == PipelineStatus.running))
        pipelines = result.scalars().all()

    for pipeline in pipelines:
        pipeline_id = pipeline.id

        async def _resume(pid: int = pipeline_id) -> None:
            async with db_session_factory() as sess:
                # Re-fetch the pipeline in the new session to avoid DetachedInstanceError
                # when accessing scalar attributes (e.g. working_dir) from a closed session.
                result = await sess.execute(select(Pipeline).where(Pipeline.id == pid))
                fresh_pipeline = result.scalar_one()
                try:
                    runner = PipelineRunner(client=client, db=sess, step_timeout=step_timeout, registry=registry)
                    await runner.resume_pipeline(fresh_pipeline, template=None)
                except Exception as exc:
                    logger.error(
                        "pipeline_recovery_failed",
                        pipeline_id=pid,
                        error=str(exc),
                        exc_info=True,
                    )
                    fresh_pipeline.status = PipelineStatus.failed
                    fresh_pipeline.updated_at = datetime.now(UTC)
                    await sess.commit()

        task = asyncio.create_task(_resume())
        task_set[pipeline.id] = task
        task.add_done_callback(lambda t, pid=pipeline.id: task_set.pop(pid, None))
