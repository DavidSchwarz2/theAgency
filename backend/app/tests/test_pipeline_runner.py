"""TDD tests for PipelineRunner service (Milestone 1 & 2)."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.adapters.opencode_client import OpenCodeClient, OpenCodeClientError
from app.adapters.opencode_models import MessageInfo, MessageResponse, Part, SessionInfo
from app.models import Base, Handoff, Pipeline, PipelineStatus, Step, StepStatus
from app.schemas.registry import AgentProfile, AgentStep, ApprovalStep, PipelineTemplate

# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def make_agent_profile(
    name: str = "developer",
    opencode_agent: str = "developer",
    system_prompt_additions: str = "",
) -> AgentProfile:
    return AgentProfile(
        name=name,
        description="Test agent",
        opencode_agent=opencode_agent,
        system_prompt_additions=system_prompt_additions,
    )


def make_message_response(text: str = "output text") -> MessageResponse:
    return MessageResponse(
        info=MessageInfo(id="msg-1", sessionID="test-session", role="assistant"),
        parts=[Part(type="text", content=text)],
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()


@pytest.fixture
def mock_client() -> AsyncMock:
    client = AsyncMock(spec=OpenCodeClient)
    client.create_session.return_value = SessionInfo(id="test-session", title="test")
    client.send_message.return_value = make_message_response("output text")
    client.delete_session.return_value = True
    client.abort_session.return_value = True
    return client


@pytest.fixture
async def pipeline_and_step(db_session: AsyncSession):
    """Create a minimal Pipeline + Step in the in-memory DB, return both."""
    pipeline = Pipeline(
        title="Test Pipeline",
        template="quick_fix",
        prompt="Fix the bug",
        status=PipelineStatus.running,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(pipeline)
    await db_session.flush()

    step = Step(
        pipeline_id=pipeline.id,
        agent_name="developer",
        order_index=0,
        status=StepStatus.running,
        started_at=datetime.now(UTC),
    )
    db_session.add(step)
    await db_session.commit()
    return pipeline, step


@pytest.fixture
def mock_registry():
    """A MagicMock AgentRegistry that returns a developer agent for any name."""
    registry = MagicMock()
    registry.get_agent.return_value = make_agent_profile(name="developer")
    return registry


@pytest.fixture
async def two_step_pipeline(db_session: AsyncSession):
    """Create a Pipeline with two Steps for run_pipeline tests."""
    pipeline = Pipeline(
        title="Two Step Pipeline",
        template="quick_fix",
        prompt="Initial prompt",
        status=PipelineStatus.running,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(pipeline)
    await db_session.flush()

    step1 = Step(
        pipeline_id=pipeline.id,
        agent_name="developer",
        order_index=0,
        status=StepStatus.pending,
    )
    step2 = Step(
        pipeline_id=pipeline.id,
        agent_name="developer",
        order_index=1,
        status=StepStatus.pending,
    )
    db_session.add(step1)
    db_session.add(step2)
    await db_session.commit()
    return pipeline, step1, step2


# ---------------------------------------------------------------------------
# Test 1: run_step success
# ---------------------------------------------------------------------------


class TestRunStepSuccess:
    async def test_run_step_success(self, db_session, mock_client, pipeline_and_step):
        """run_step with a successful send_message marks step done, persists Handoff, returns text."""
        from app.services.pipeline_runner import PipelineRunner

        _, step = pipeline_and_step
        agent = make_agent_profile()
        runner = PipelineRunner(client=mock_client, db=db_session, step_timeout=30)

        output_text, handoff_schema = await runner.run_step(step, agent, "Fix the bug")

        assert output_text == "output text"
        assert handoff_schema is None  # plain "output text" has no structured headings
        assert step.status == StepStatus.done
        assert step.finished_at is not None

        # Handoff persisted in DB
        handoff = await db_session.get(Handoff, 1)
        assert handoff is not None
        assert handoff.content_md == "output text"
        assert handoff.step_id == step.id


# ---------------------------------------------------------------------------
# Test 2: run_step failure (OpenCodeClientError)
# ---------------------------------------------------------------------------


class TestRunStepFailure:
    async def test_run_step_failure_raises_error(self, db_session, mock_client, pipeline_and_step):
        """run_step raises StepExecutionError and marks step failed on OpenCodeClientError."""
        from app.services.pipeline_runner import PipelineRunner, StepExecutionError

        _, step = pipeline_and_step
        mock_client.send_message.side_effect = OpenCodeClientError("Agent crashed")
        agent = make_agent_profile()
        runner = PipelineRunner(client=mock_client, db=db_session, step_timeout=30)

        with pytest.raises(StepExecutionError, match="failed"):
            await runner.run_step(step, agent, "Fix the bug")

        assert step.status == StepStatus.failed
        assert step.finished_at is not None


# ---------------------------------------------------------------------------
# Tests 3 & 4: session cleanup in finally block
# ---------------------------------------------------------------------------


class TestRunStepSessionCleanup:
    async def test_run_step_deletes_session_on_success(self, db_session, mock_client, pipeline_and_step):
        """delete_session is called even when run_step succeeds."""
        from app.services.pipeline_runner import PipelineRunner

        _, step = pipeline_and_step
        runner = PipelineRunner(client=mock_client, db=db_session, step_timeout=30)
        await runner.run_step(step, make_agent_profile(), "prompt")

        mock_client.delete_session.assert_awaited_once_with("test-session")

    async def test_run_step_deletes_session_on_failure(self, db_session, mock_client, pipeline_and_step):
        """delete_session is called even when run_step raises StepExecutionError."""
        from app.services.pipeline_runner import PipelineRunner, StepExecutionError

        _, step = pipeline_and_step
        mock_client.send_message.side_effect = OpenCodeClientError("boom")
        runner = PipelineRunner(client=mock_client, db=db_session, step_timeout=30)

        with pytest.raises(StepExecutionError):
            await runner.run_step(step, make_agent_profile(), "prompt")

        mock_client.delete_session.assert_awaited_once_with("test-session")


# ---------------------------------------------------------------------------
# Test 5: system_prompt_additions are prepended
# ---------------------------------------------------------------------------


class TestRunStepSystemPrompt:
    async def test_run_step_includes_system_prompt_additions(self, db_session, mock_client, pipeline_and_step):
        """When agent_profile has system_prompt_additions, they are prepended to the prompt."""
        from app.services.pipeline_runner import PipelineRunner

        _, step = pipeline_and_step
        agent = make_agent_profile(system_prompt_additions="Always be concise.")
        runner = PipelineRunner(client=mock_client, db=db_session, step_timeout=30)

        await runner.run_step(step, agent, "Fix the bug")

        call_kwargs = mock_client.send_message.call_args
        sent_prompt = call_kwargs.kwargs.get("prompt") or call_kwargs.args[1]
        assert sent_prompt.startswith("Always be concise.")
        assert "Fix the bug" in sent_prompt


# ---------------------------------------------------------------------------
# Test 6: timeout aborts the OpenCode session
# ---------------------------------------------------------------------------


class TestRunStepTimeout:
    async def test_run_step_timeout_aborts_session(self, db_session, mock_client, pipeline_and_step):
        """On asyncio.TimeoutError, abort_session is called and step is marked failed."""
        from app.services.pipeline_runner import PipelineRunner, StepExecutionError

        _, step = pipeline_and_step

        async def slow_send(*_args, **_kwargs):
            await asyncio.sleep(9999)

        mock_client.send_message.side_effect = slow_send
        runner = PipelineRunner(client=mock_client, db=db_session, step_timeout=0.05)

        with pytest.raises(StepExecutionError, match="timed out"):
            await runner.run_step(step, make_agent_profile(), "prompt")

        mock_client.abort_session.assert_awaited_once_with("test-session")
        assert step.status == StepStatus.failed


# ---------------------------------------------------------------------------
# Test 7: current_session_id property lifecycle
# ---------------------------------------------------------------------------


class TestCurrentSessionId:
    async def test_current_session_id_set_during_execution(self, db_session, mock_client, pipeline_and_step):
        """current_session_id is set during step execution and reset to None after."""
        from app.services.pipeline_runner import PipelineRunner

        _, step = pipeline_and_step
        runner = PipelineRunner(client=mock_client, db=db_session, step_timeout=30)

        captured_session_id: list[str | None] = []

        async def capturing_send(session_id, prompt, agent=None):
            captured_session_id.append(runner.current_session_id)
            return make_message_response("output")

        mock_client.send_message.side_effect = capturing_send

        assert runner.current_session_id is None
        await runner.run_step(step, make_agent_profile(), "prompt")
        assert runner.current_session_id is None
        assert captured_session_id == ["test-session"]


# ---------------------------------------------------------------------------
# Milestone 2 tests: run_pipeline
# ---------------------------------------------------------------------------


class TestRunPipelineSuccess:
    async def test_run_pipeline_success(self, db_session, mock_client, mock_registry, two_step_pipeline):
        """Two-step pipeline completes: both steps done, pipeline status done."""
        from app.services.pipeline_runner import PipelineRunner

        pipeline, step1, step2 = two_step_pipeline

        call_count = 0

        async def send_message(session_id, prompt, agent=None):
            nonlocal call_count
            call_count += 1
            return make_message_response(f"output-{call_count}")

        mock_client.send_message.side_effect = send_message

        template = PipelineTemplate(
            name="quick_fix",
            description="Quick fix",
            steps=[
                AgentStep(agent="developer", description="step 1"),
                AgentStep(agent="developer", description="step 2"),
            ],
        )

        runner = PipelineRunner(client=mock_client, db=db_session, step_timeout=30, registry=mock_registry)

        await runner.run_pipeline(pipeline, template)

        assert pipeline.status == PipelineStatus.done
        assert step1.status == StepStatus.done
        assert step2.status == StepStatus.done


class TestRunPipelineFailure:
    async def test_run_pipeline_step_failure_marks_pipeline_failed(
        self, db_session, mock_client, mock_registry, two_step_pipeline
    ):
        """If first step fails, pipeline is marked failed, second step stays pending."""
        from app.services.pipeline_runner import PipelineRunner

        pipeline, step1, step2 = two_step_pipeline
        mock_client.send_message.side_effect = OpenCodeClientError("boom")

        template = PipelineTemplate(
            name="quick_fix",
            description="Quick fix",
            steps=[
                AgentStep(agent="developer", description="step 1"),
                AgentStep(agent="developer", description="step 2"),
            ],
        )
        runner = PipelineRunner(client=mock_client, db=db_session, step_timeout=30, registry=mock_registry)

        await runner.run_pipeline(pipeline, template)

        assert pipeline.status == PipelineStatus.failed
        assert step1.status == StepStatus.failed
        assert step2.status == StepStatus.pending


class TestRunPipelineHandoff:
    async def test_run_pipeline_passes_handoff_as_next_prompt(
        self, db_session, mock_client, mock_registry, two_step_pipeline
    ):
        """The second step's prompt equals the first step's output text."""
        from app.services.pipeline_runner import PipelineRunner

        pipeline, step1, step2 = two_step_pipeline
        received_prompts: list[str] = []

        async def send_message(session_id, prompt, agent=None):
            received_prompts.append(prompt)
            return make_message_response("step-one-output")

        mock_client.send_message.side_effect = send_message

        template = PipelineTemplate(
            name="quick_fix",
            description="Quick fix",
            steps=[
                AgentStep(agent="developer", description="step 1"),
                AgentStep(agent="developer", description="step 2"),
            ],
        )
        runner = PipelineRunner(client=mock_client, db=db_session, step_timeout=30, registry=mock_registry)

        await runner.run_pipeline(pipeline, template)

        # First prompt is the pipeline's initial prompt
        assert received_prompts[0] == "Initial prompt"
        # Second prompt is the first step's output
        assert received_prompts[1] == "step-one-output"


class TestRunPipelineUnknownAgent:
    async def test_run_pipeline_unknown_agent_marks_pipeline_failed(
        self, db_session, mock_client, mock_registry, two_step_pipeline
    ):
        """If step references unknown agent, pipeline is marked failed."""
        from app.services.pipeline_runner import PipelineRunner

        pipeline, step1, step2 = two_step_pipeline
        mock_registry.get_agent.return_value = None  # unknown agent

        template = PipelineTemplate(
            name="quick_fix",
            description="Quick fix",
            steps=[
                AgentStep(agent="unknown_agent", description="step 1"),
                AgentStep(agent="developer", description="step 2"),
            ],
        )
        runner = PipelineRunner(client=mock_client, db=db_session, step_timeout=30, registry=mock_registry)

        await runner.run_pipeline(pipeline, template)

        assert pipeline.status == PipelineStatus.failed
        assert step1.status == StepStatus.failed


# ---------------------------------------------------------------------------
# Milestone 3 tests: resume_pipeline
# ---------------------------------------------------------------------------


@pytest.fixture
async def partial_pipeline(db_session: AsyncSession):
    """Pipeline with step1=done (has Handoff), step2=pending."""
    pipeline = Pipeline(
        title="Partial Pipeline",
        template="quick_fix",
        prompt="Initial prompt",
        status=PipelineStatus.running,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(pipeline)
    await db_session.flush()

    step1 = Step(
        pipeline_id=pipeline.id,
        agent_name="developer",
        order_index=0,
        status=StepStatus.done,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    step2 = Step(
        pipeline_id=pipeline.id,
        agent_name="developer",
        order_index=1,
        status=StepStatus.pending,
    )
    db_session.add(step1)
    db_session.add(step2)
    await db_session.flush()

    handoff = Handoff(step_id=step1.id, content_md="prev output")
    db_session.add(handoff)
    await db_session.commit()
    return pipeline, step1, step2


class TestResumePipelineSkipsCompleted:
    async def test_resume_pipeline_skips_completed_steps(
        self, db_session, mock_client, mock_registry, partial_pipeline
    ):
        """Only step2 is executed; send_message is called once."""
        from app.services.pipeline_runner import PipelineRunner

        pipeline, step1, step2 = partial_pipeline
        runner = PipelineRunner(client=mock_client, db=db_session, step_timeout=30, registry=mock_registry)
        await runner.resume_pipeline(pipeline, template=None)

        mock_client.send_message.assert_awaited_once()
        assert step2.status == StepStatus.done


class TestResumePipelineHandoff:
    async def test_resume_pipeline_uses_last_handoff_as_prompt(
        self, db_session, mock_client, mock_registry, partial_pipeline
    ):
        """step2 receives the handoff content from step1 as its prompt."""
        from app.services.pipeline_runner import PipelineRunner

        pipeline, step1, step2 = partial_pipeline
        received_prompts: list[str] = []

        async def capturing_send(session_id, prompt, agent=None):
            received_prompts.append(prompt)
            return make_message_response("new output")

        mock_client.send_message.side_effect = capturing_send
        runner = PipelineRunner(client=mock_client, db=db_session, step_timeout=30, registry=mock_registry)
        await runner.resume_pipeline(pipeline, template=None)

        assert received_prompts == ["prev output"]


class TestResumePipelineAllDone:
    async def test_resume_pipeline_all_done_marks_done(self, db_session, mock_client, mock_registry):
        """If all steps are done, pipeline is marked done without any send_message call."""
        from app.services.pipeline_runner import PipelineRunner

        pipeline = Pipeline(
            title="Done Pipeline",
            template="quick_fix",
            prompt="prompt",
            status=PipelineStatus.running,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db_session.add(pipeline)
        await db_session.flush()

        step = Step(
            pipeline_id=pipeline.id,
            agent_name="developer",
            order_index=0,
            status=StepStatus.done,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )
        db_session.add(step)
        await db_session.commit()

        runner = PipelineRunner(client=mock_client, db=db_session, step_timeout=30, registry=mock_registry)
        await runner.resume_pipeline(pipeline, template=None)

        assert pipeline.status == PipelineStatus.done
        mock_client.send_message.assert_not_awaited()


class TestResumePipelineNoDoneSteps:
    async def test_resume_pipeline_no_done_steps_uses_pipeline_prompt(
        self, db_session, mock_client, mock_registry, two_step_pipeline
    ):
        """If no steps are done yet, first step receives pipeline.prompt."""
        from app.services.pipeline_runner import PipelineRunner

        pipeline, step1, step2 = two_step_pipeline
        received_prompts: list[str] = []

        async def capturing_send(session_id, prompt, agent=None):
            received_prompts.append(prompt)
            return make_message_response("output")

        mock_client.send_message.side_effect = capturing_send
        runner = PipelineRunner(client=mock_client, db=db_session, step_timeout=30, registry=mock_registry)
        await runner.resume_pipeline(pipeline, template=None)

        assert received_prompts[0] == "Initial prompt"


# ---------------------------------------------------------------------------
# Milestone 2 (Handoff System) — tests 14–20
# ---------------------------------------------------------------------------

STRUCTURED_OUTPUT = (
    "## What Was Done\nImplemented the login endpoint.\n\n## Next Agent Context\nContinue with rate limiting.\n"
)


class TestRunStepHandoffExtraction:
    async def test_run_step_persists_metadata_json_when_extraction_succeeds(
        self, db_session, mock_client, pipeline_and_step
    ):
        """When agent output has structured headings, metadata_json is stored on Handoff."""
        from sqlalchemy import select

        from app.models import Handoff
        from app.schemas.handoff import HandoffSchema
        from app.services.pipeline_runner import PipelineRunner

        _, step = pipeline_and_step
        mock_client.send_message.return_value = make_message_response(STRUCTURED_OUTPUT)
        runner = PipelineRunner(client=mock_client, db=db_session, step_timeout=30)

        output, schema = await runner.run_step(step, make_agent_profile(), "prompt")

        assert schema is not None
        assert isinstance(schema, HandoffSchema)
        result = await db_session.execute(select(Handoff).where(Handoff.step_id == step.id))
        handoff = result.scalar_one()
        assert handoff.metadata_json is not None
        parsed = HandoffSchema.model_validate_json(handoff.metadata_json)
        assert parsed.what_was_done == "Implemented the login endpoint."

    async def test_run_step_metadata_json_is_none_when_extraction_fails(
        self, db_session, mock_client, pipeline_and_step
    ):
        """When agent output is plain prose, metadata_json stays None."""
        from sqlalchemy import select

        from app.models import Handoff
        from app.services.pipeline_runner import PipelineRunner

        _, step = pipeline_and_step
        mock_client.send_message.return_value = make_message_response("Just plain prose, no headings here.")
        runner = PipelineRunner(client=mock_client, db=db_session, step_timeout=30)

        output, schema = await runner.run_step(step, make_agent_profile(), "prompt")

        assert schema is None
        result = await db_session.execute(select(Handoff).where(Handoff.step_id == step.id))
        handoff = result.scalar_one()
        assert handoff.metadata_json is None


class TestExecuteStepsContextHeader:
    async def test_execute_steps_uses_context_header_as_next_prompt(
        self, db_session, mock_client, mock_registry, two_step_pipeline
    ):
        """When step 1 produces structured output, step 2's prompt is a context header."""
        from app.services.pipeline_runner import PipelineRunner

        pipeline, step1, step2 = two_step_pipeline
        received_prompts: list[str] = []
        call_count = 0

        async def send_message(session_id, prompt, agent=None):
            nonlocal call_count
            received_prompts.append(prompt)
            call_count += 1
            if call_count == 1:
                return make_message_response(STRUCTURED_OUTPUT)
            return make_message_response("final output")

        mock_client.send_message.side_effect = send_message
        template = PipelineTemplate(
            name="quick_fix",
            description="Quick fix",
            steps=[
                AgentStep(agent="developer", description="step 1"),
                AgentStep(agent="developer", description="step 2"),
            ],
        )
        runner = PipelineRunner(client=mock_client, db=db_session, step_timeout=30, registry=mock_registry)
        await runner.run_pipeline(pipeline, template)

        assert received_prompts[1].startswith("## Handoff from previous step")

    async def test_execute_steps_falls_back_to_raw_output_when_extraction_fails(
        self, db_session, mock_client, mock_registry, two_step_pipeline
    ):
        """When step 1 output has no headings, step 2 receives the raw output text."""
        from app.services.pipeline_runner import PipelineRunner

        pipeline, step1, step2 = two_step_pipeline
        received_prompts: list[str] = []

        async def send_message(session_id, prompt, agent=None):
            received_prompts.append(prompt)
            return make_message_response("plain prose output")

        mock_client.send_message.side_effect = send_message
        template = PipelineTemplate(
            name="quick_fix",
            description="Quick fix",
            steps=[
                AgentStep(agent="developer", description="step 1"),
                AgentStep(agent="developer", description="step 2"),
            ],
        )
        runner = PipelineRunner(client=mock_client, db=db_session, step_timeout=30, registry=mock_registry)
        await runner.run_pipeline(pipeline, template)

        assert received_prompts[1] == "plain prose output"


class TestAuditEventsForHandoffs:
    async def test_audit_event_handoff_created_written_on_success(self, db_session, mock_client, pipeline_and_step):
        """A handoff_created AuditEvent with has_structured_data=true is written on structured output."""
        import json

        from sqlalchemy import select

        from app.models import AuditEvent
        from app.services.pipeline_runner import PipelineRunner

        _, step = pipeline_and_step
        mock_client.send_message.return_value = make_message_response(STRUCTURED_OUTPUT)
        runner = PipelineRunner(client=mock_client, db=db_session, step_timeout=30)
        await runner.run_step(step, make_agent_profile(), "prompt")

        result = await db_session.execute(select(AuditEvent).where(AuditEvent.event_type == "handoff_created"))
        event = result.scalar_one()
        payload = json.loads(event.payload_json)
        assert payload["has_structured_data"] is True

    async def test_audit_event_handoff_extraction_failed_written_on_failure(
        self, db_session, mock_client, pipeline_and_step
    ):
        """Both handoff_created (has_structured_data=false) and handoff_extraction_failed are written."""
        import json

        from sqlalchemy import select

        from app.models import AuditEvent
        from app.services.pipeline_runner import PipelineRunner

        _, step = pipeline_and_step
        mock_client.send_message.return_value = make_message_response("plain prose, no structure")
        runner = PipelineRunner(client=mock_client, db=db_session, step_timeout=30)
        await runner.run_step(step, make_agent_profile(), "prompt")

        result = await db_session.execute(select(AuditEvent))
        events = result.scalars().all()
        event_types = {e.event_type for e in events}
        assert "handoff_created" in event_types
        assert "handoff_extraction_failed" in event_types

        created = next(e for e in events if e.event_type == "handoff_created")
        payload = json.loads(created.payload_json)
        assert payload["has_structured_data"] is False


class TestResumePipelineContextHeader:
    async def test_resume_pipeline_uses_context_header_from_metadata_json(self, db_session, mock_client, mock_registry):
        """resume_pipeline uses to_context_header() when metadata_json is set on last done step."""
        from app.schemas.handoff import HandoffSchema
        from app.services.pipeline_runner import PipelineRunner

        pipeline = Pipeline(
            title="Resume Header Pipeline",
            template="quick_fix",
            prompt="original prompt",
            status=PipelineStatus.running,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db_session.add(pipeline)
        await db_session.flush()

        step1 = Step(
            pipeline_id=pipeline.id,
            agent_name="developer",
            order_index=0,
            status=StepStatus.done,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )
        step2 = Step(
            pipeline_id=pipeline.id,
            agent_name="developer",
            order_index=1,
            status=StepStatus.pending,
        )
        db_session.add(step1)
        db_session.add(step2)
        await db_session.flush()

        schema = HandoffSchema(
            what_was_done="Did the first thing.",
            next_agent_context="Continue with second thing.",
        )
        handoff = Handoff(
            step_id=step1.id,
            content_md="raw content",
            metadata_json=schema.model_dump_json(exclude_none=True),
        )
        db_session.add(handoff)
        await db_session.commit()

        received_prompts: list[str] = []

        async def capturing_send(session_id, prompt, agent=None):
            received_prompts.append(prompt)
            return make_message_response("resumed output")

        mock_client.send_message.side_effect = capturing_send
        runner = PipelineRunner(client=mock_client, db=db_session, step_timeout=30, registry=mock_registry)
        await runner.resume_pipeline(pipeline, template=None)

        assert received_prompts[0].startswith("## Handoff from previous step")


# ---------------------------------------------------------------------------
# Milestone 2 Tests: Approval step detection in _execute_steps
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_engine_for_approval():
    """Separate in-memory engine for approval tests that need two concurrent sessions."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def approval_pipeline(db_engine_for_approval):
    """A Pipeline with three steps: agent → approval → agent. Uses its own engine."""
    async with AsyncSession(db_engine_for_approval, expire_on_commit=False) as session:
        pipeline = Pipeline(
            title="Approval Pipeline",
            template="approval_flow",
            prompt="Initial prompt",
            status=PipelineStatus.running,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(pipeline)
        await session.flush()

        step_agent1 = Step(
            pipeline_id=pipeline.id,
            agent_name="developer",
            order_index=0,
            status=StepStatus.pending,
        )
        step_approval = Step(
            pipeline_id=pipeline.id,
            agent_name="__approval__",
            order_index=1,
            status=StepStatus.pending,
        )
        step_agent2 = Step(
            pipeline_id=pipeline.id,
            agent_name="reviewer",
            order_index=2,
            status=StepStatus.pending,
        )
        session.add(step_agent1)
        session.add(step_approval)
        session.add(step_agent2)
        await session.commit()
        return pipeline.id, step_agent1.id, step_approval.id, step_agent2.id


class TestApprovalStepDetection:
    async def test_runner_pauses_at_approval_step(
        self, mock_client, mock_registry, approval_pipeline, db_engine_for_approval
    ):
        """When the runner hits an approval step it sets pipeline to waiting_for_approval and pauses."""
        from sqlalchemy import select as sa_select

        from app.models import Approval, ApprovalStatus
        from app.services.pipeline_runner import PipelineRunner

        pipeline_id, step_agent1_id, step_approval_id, step_agent2_id = approval_pipeline
        approval_event: asyncio.Event = asyncio.Event()

        async def _runner_task() -> None:
            async with AsyncSession(db_engine_for_approval, expire_on_commit=False) as runner_session:
                result = await runner_session.execute(sa_select(Pipeline).where(Pipeline.id == pipeline_id))
                pipeline = result.scalar_one()
                runner = PipelineRunner(
                    client=mock_client,
                    db=runner_session,
                    step_timeout=30,
                    registry=mock_registry,
                    approval_events={pipeline_id: approval_event},
                )
                await runner.run_pipeline(
                    pipeline,
                    PipelineTemplate(
                        name="approval_flow",
                        description="d",
                        steps=[
                            AgentStep(agent="developer", description="s1"),
                            ApprovalStep(type="approval", description="gate"),
                            AgentStep(agent="reviewer", description="s3"),
                        ],
                    ),
                )

        async def _approve_task() -> None:
            async with AsyncSession(db_engine_for_approval, expire_on_commit=False) as helper_session:
                approval = None
                for _ in range(50):
                    await asyncio.sleep(0.01)
                    result = await helper_session.execute(
                        sa_select(Approval).where(Approval.step_id == step_approval_id)
                    )
                    approval = result.scalar_one_or_none()
                    if approval is not None:
                        break

                assert approval is not None
                result = await helper_session.execute(sa_select(Pipeline).where(Pipeline.id == pipeline_id))
                pipeline = result.scalar_one()
                assert pipeline.status == PipelineStatus.waiting_for_approval

                approval.status = ApprovalStatus.approved
                approval.comment = "Looks good"
                approval.decided_by = "reviewer_human"
                approval.decided_at = datetime.now(UTC)
                await helper_session.commit()
            approval_event.set()

        runner_task = asyncio.create_task(_runner_task())
        await asyncio.wait_for(_approve_task(), timeout=5.0)
        await asyncio.wait_for(runner_task, timeout=5.0)

        async with AsyncSession(db_engine_for_approval, expire_on_commit=False) as check_session:
            result = await check_session.execute(sa_select(Pipeline).where(Pipeline.id == pipeline_id))
            pipeline = result.scalar_one()
            assert pipeline.status == PipelineStatus.done

            result = await check_session.execute(sa_select(Step).where(Step.id == step_agent1_id))
            assert result.scalar_one().status == StepStatus.done

            result = await check_session.execute(sa_select(Step).where(Step.id == step_approval_id))
            assert result.scalar_one().status == StepStatus.done

            result = await check_session.execute(sa_select(Step).where(Step.id == step_agent2_id))
            assert result.scalar_one().status == StepStatus.done

    async def test_runner_fails_pipeline_on_rejection(
        self, mock_client, mock_registry, approval_pipeline, db_engine_for_approval
    ):
        """When an approval step is rejected, the pipeline is marked failed."""
        from sqlalchemy import select as sa_select

        from app.models import Approval, ApprovalStatus
        from app.services.pipeline_runner import PipelineRunner

        pipeline_id, step_agent1_id, step_approval_id, step_agent2_id = approval_pipeline
        approval_event: asyncio.Event = asyncio.Event()

        async def _runner_task() -> None:
            async with AsyncSession(db_engine_for_approval, expire_on_commit=False) as runner_session:
                result = await runner_session.execute(sa_select(Pipeline).where(Pipeline.id == pipeline_id))
                pipeline = result.scalar_one()
                runner = PipelineRunner(
                    client=mock_client,
                    db=runner_session,
                    step_timeout=30,
                    registry=mock_registry,
                    approval_events={pipeline_id: approval_event},
                )
                await runner.run_pipeline(
                    pipeline,
                    PipelineTemplate(
                        name="approval_flow",
                        description="d",
                        steps=[
                            AgentStep(agent="developer", description="s1"),
                            ApprovalStep(type="approval", description="gate"),
                            AgentStep(agent="reviewer", description="s3"),
                        ],
                    ),
                )

        async def _reject_task() -> None:
            async with AsyncSession(db_engine_for_approval, expire_on_commit=False) as helper_session:
                approval = None
                for _ in range(50):
                    await asyncio.sleep(0.01)
                    result = await helper_session.execute(
                        sa_select(Approval).where(Approval.step_id == step_approval_id)
                    )
                    approval = result.scalar_one_or_none()
                    if approval is not None:
                        break

                assert approval is not None
                approval.status = ApprovalStatus.rejected
                approval.decided_at = datetime.now(UTC)
                await helper_session.commit()
            approval_event.set()

        runner_task = asyncio.create_task(_runner_task())
        await asyncio.wait_for(_reject_task(), timeout=5.0)
        await asyncio.wait_for(runner_task, timeout=5.0)

        async with AsyncSession(db_engine_for_approval, expire_on_commit=False) as check_session:
            result = await check_session.execute(sa_select(Pipeline).where(Pipeline.id == pipeline_id))
            assert result.scalar_one().status == PipelineStatus.failed

            result = await check_session.execute(sa_select(Step).where(Step.id == step_approval_id))
            assert result.scalar_one().status == StepStatus.failed

            result = await check_session.execute(sa_select(Step).where(Step.id == step_agent2_id))
            assert result.scalar_one().status == StepStatus.pending

    async def test_approval_step_writes_audit_event(
        self, mock_client, mock_registry, approval_pipeline, db_engine_for_approval
    ):
        """An approval_requested AuditEvent is written when the pipeline pauses."""
        from sqlalchemy import select as sa_select

        from app.models import Approval, ApprovalStatus, AuditEvent
        from app.services.pipeline_runner import PipelineRunner

        pipeline_id, _, step_approval_id, _ = approval_pipeline
        approval_event: asyncio.Event = asyncio.Event()

        async def _runner_task() -> None:
            async with AsyncSession(db_engine_for_approval, expire_on_commit=False) as runner_session:
                result = await runner_session.execute(sa_select(Pipeline).where(Pipeline.id == pipeline_id))
                pipeline = result.scalar_one()
                runner = PipelineRunner(
                    client=mock_client,
                    db=runner_session,
                    step_timeout=30,
                    registry=mock_registry,
                    approval_events={pipeline_id: approval_event},
                )
                await runner.run_pipeline(
                    pipeline,
                    PipelineTemplate(
                        name="approval_flow",
                        description="d",
                        steps=[
                            AgentStep(agent="developer", description="s1"),
                            ApprovalStep(type="approval", description="gate"),
                            AgentStep(agent="reviewer", description="s3"),
                        ],
                    ),
                )

        async def _approve_task() -> None:
            async with AsyncSession(db_engine_for_approval, expire_on_commit=False) as helper_session:
                for _ in range(50):
                    await asyncio.sleep(0.01)
                    result = await helper_session.execute(
                        sa_select(Approval).where(Approval.step_id == step_approval_id)
                    )
                    if result.scalar_one_or_none() is not None:
                        break

                result = await helper_session.execute(sa_select(Approval).where(Approval.step_id == step_approval_id))
                approval = result.scalar_one()
                approval.status = ApprovalStatus.approved
                approval.decided_at = datetime.now(UTC)
                await helper_session.commit()
            approval_event.set()

        runner_task = asyncio.create_task(_runner_task())
        await asyncio.wait_for(_approve_task(), timeout=5.0)
        await asyncio.wait_for(runner_task, timeout=5.0)

        async with AsyncSession(db_engine_for_approval, expire_on_commit=False) as check_session:
            result = await check_session.execute(
                sa_select(AuditEvent).where(
                    AuditEvent.pipeline_id == pipeline_id,
                    AuditEvent.event_type == "approval_requested",
                )
            )
            audit = result.scalar_one_or_none()
            assert audit is not None
            assert audit.step_id == step_approval_id
