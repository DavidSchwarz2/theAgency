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
from app.models import AuditEvent, Handoff, Pipeline, PipelineStatus, Step, StepStatus
from app.schemas.handoff import HandoffSchema
from app.schemas.registry import AgentProfile, PipelineTemplate
from app.services.agent_registry import AgentRegistry
from app.services.handoff_extractor import HandoffExtractor

logger = structlog.get_logger(__name__)


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
    ) -> None:
        self._client = client
        self._db = db
        self._step_timeout = step_timeout
        self._registry = registry
        self._extractor = extractor or HandoffExtractor()
        self._current_session_id: str | None = None

    @property
    def current_session_id(self) -> str | None:
        """The active OpenCode session ID, or None when no step is running."""
        return self._current_session_id

    async def run_step(
        self,
        step: Step,
        agent_profile: AgentProfile,
        prompt: str,
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

        full_prompt = (
            f"{agent_profile.system_prompt_additions}\n\n{prompt}" if agent_profile.system_prompt_additions else prompt
        )

        try:
            response: MessageResponse = await asyncio.wait_for(
                self._client.send_message(
                    session_id,
                    prompt=full_prompt,
                    agent=agent_profile.opencode_agent,
                ),
                timeout=self._step_timeout,
            )
            output_text = self._extract_output(response)
            handoff_schema = await self._persist_success(step, output_text)
            return output_text, handoff_schema

        except TimeoutError:
            logger.warning("step_timeout", step_id=step.id, timeout=self._step_timeout)
            await self._client.abort_session(session_id)
            await self._persist_failure(step)
            raise StepExecutionError(f"Step {step.id} timed out after {self._step_timeout}s") from None

        except OpenCodeClientError as exc:
            logger.warning("step_client_error", step_id=step.id, error=str(exc))
            await self._persist_failure(step)
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

    async def _persist_failure(self, step: Step) -> None:
        step.status = StepStatus.failed
        step.finished_at = datetime.now(UTC)
        await self._db.commit()

    async def _execute_steps(self, steps: list[Step], initial_prompt: str, pipeline: Pipeline) -> None:
        """Execute a list of steps sequentially, chaining output as the next prompt.

        Updates `pipeline.status` to `failed` and returns early on any error.
        Sets `pipeline.status` to `done` if all steps complete successfully.
        """
        if self._registry is None:
            raise ValueError("_execute_steps requires a registry")

        current_prompt = initial_prompt

        for step in steps:
            step.status = StepStatus.running
            step.started_at = datetime.now(UTC)
            await self._db.commit()

            agent_profile = self._registry.get_agent(step.agent_name)
            if agent_profile is None:
                logger.error("unknown_agent", agent_name=step.agent_name, step_id=step.id)
                step.status = StepStatus.failed
                step.finished_at = datetime.now(UTC)
                pipeline.status = PipelineStatus.failed
                pipeline.updated_at = datetime.now(UTC)
                await self._db.commit()
                return

            try:
                output_text, handoff_schema = await self.run_step(step, agent_profile, current_prompt)
                if handoff_schema is not None:
                    current_prompt = handoff_schema.to_context_header(agent_name=step.agent_name)
                else:
                    current_prompt = output_text
            except StepExecutionError:
                pipeline.status = PipelineStatus.failed
                pipeline.updated_at = datetime.now(UTC)
                await self._db.commit()
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

        await self._execute_steps(steps, loaded_pipeline.prompt, pipeline)

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
    task_set: "set[asyncio.Task]",  # type: ignore[type-arg]
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

        async def _resume(p: Pipeline = pipeline) -> None:
            async with db_session_factory() as sess:
                runner = PipelineRunner(client=client, db=sess, step_timeout=step_timeout, registry=registry)
                await runner.resume_pipeline(p, template=None)

        task = asyncio.create_task(_resume())
        task_set.add(task)
        task.add_done_callback(task_set.discard)
