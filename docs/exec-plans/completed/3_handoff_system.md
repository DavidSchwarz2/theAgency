# Feature: Handoff System (Structured Agent-to-Agent Context)

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

Right now, when one agent finishes a pipeline step and the next agent begins, the only context
passed forward is the raw text output of the previous agent — an unstructured blob of Markdown.
The next agent must read the entire previous output to figure out what happened, what decisions
were made, and what it should do next. This is fragile and wastes tokens.

After this feature, every agent's output is automatically parsed into a structured **Handoff** —
a validated Pydantic model with four fields: `what_was_done`, `decisions_made`,
`open_questions`, and `next_agent_context`. The handoff is stored in SQLite (augmenting the
existing `Handoff.metadata_json` field — no new table or migration needed). The next agent
receives a concise, well-formatted context header derived from the structured handoff rather
than the full raw output. Failed extractions (where the agent produced no structured output)
log a warning and fall back gracefully to the raw content.

A developer can verify this feature by running `npx nx run backend:test` (all tests pass) and
inspecting a completed pipeline's `GET /pipelines/{id}` response — each step's handoff now
includes a `metadata` field with the structured fields.

## Progress

- [x] (2026-02-27) ExecPlan drafted
- [x] (2026-02-27) ExecPlan reviewed — 6 MUST FIX, 7 SHOULD FIX, 6 CONSIDER findings
- [x] (2026-02-27) Review findings incorporated into revised plan
- [x] (2026-02-27) ExecPlan reviewed and approved by user
- [x] (2026-02-27) Milestone 1: HandoffSchema Pydantic model + HandoffExtractor service (extraction logic + tests) — 13 tests, 79 total pass
- [x] (2026-02-27) Milestone 2: Wire extractor into PipelineRunner (structured metadata, context header, audit events) — 7 new tests, 86 total pass
- [x] (2026-02-27) Milestone 3: Expose handoff metadata in GET /pipelines/{id} API response — 2 new tests, 88 total pass
- [x] (2026-02-27) Post-impl code-quality review — MUST FIX resolved (datetime.utcnow → now(UTC) in tests, sorted() in get_pipeline); pre-existing bugs noted in Surprises
- [ ] ExecPlan finalized: outcomes written, plan moved to completed/

## Surprises & Discoveries

- `structlog.get_logger()` must be used instead of `logging.getLogger()` in service files.
- SQLAlchemy `expire_on_commit=False` is required in both production and test sessions —
  `step.pipeline_id` and `handoff.id` are accessed after commits in `_persist_success`; would
  raise `MissingGreenlet` without this setting.
- `_persist_success` must call `await self._db.flush()` before accessing `handoff.id` — flush
  assigns the auto-increment ID without committing.
- `HandoffResponse` must NOT use `from_attributes=True` (column is `metadata_json: str`, not
  `metadata: dict`). Constructed manually in the router.
- `run_step` now returns `tuple[str, HandoffSchema | None]`. All existing tests that treat the
  return value as a bare string needed updating to unpack the tuple.
- The existing `GET /pipelines/{id}` handler's `model_validate(pipeline)` one-liner had to be
  replaced with manual construction because `Step` ORM has no `latest_handoff` attribute.
- `datetime.now(UTC)` not `datetime.utcnow()` (deprecated since Python 3.12).
- **Pre-existing bugs (not introduced by this feature, tracked separately)**:
  - `recover_interrupted_pipelines` passes detached ORM `Pipeline` objects across sessions.
  - `abort_pipeline` cancels all pipeline tasks, not just the target pipeline's task.
  - `resume_pipeline` prompt reconstruction is fragile for failure-then-resume scenarios.

## Decision Log

- Decision: Reuse the existing `Handoff.metadata_json` column to store structured handoff data
  rather than adding new columns or a new table.
  Rationale: The column already exists with `Text` type and nullable semantics. Storing a JSON
  string there avoids a migration and keeps the schema stable. The Pydantic model does the
  validation at the service layer; the DB just stores serialized JSON.
  Date/Author: 2026-02-27 / agent

- Decision: Use regex + Markdown heading extraction for primary parsing; LLM extraction is
  deferred to a future issue.
  Rationale: Most OpenCode agents already produce structured Markdown output with headings. A
  deterministic regex approach is fast, free, and testable. LLM extraction is expensive and
  adds a network dependency — it should be a last resort. The `HandoffExtractor` class is
  designed to be extended (e.g. with a subclass or strategy pattern) without changing call sites.
  Date/Author: 2026-02-27 / agent

- Decision: The context header passed to the next agent is a compact Markdown snippet generated
  from the structured handoff, not the full raw output.
  Rationale: The issue asks for "Bereitstellung als Kontext für den nächsten Agenten" (provision
  as context for the next agent). A compact header reduces token usage and focuses the next
  agent on what it actually needs: what was done, what decisions were made, and what it should do.
  The full raw content remains in `content_md` for audit purposes.
  Date/Author: 2026-02-27 / agent

- Decision: Audit events are written using the existing `AuditEvent` ORM model.
  Rationale: The model already exists. Writing `handoff_created` and `handoff_extraction_failed`
  events satisfies the "Handoffs sind im Audit Trail nachvollziehbar" acceptance criterion without
  any schema changes.
  Date/Author: 2026-02-27 / agent

- Decision: `_persist_success` returns `HandoffSchema | None` rather than requiring a DB
  query-back in `_execute_steps`.
  Rationale: `_persist_success` already has all the information — it calls the extractor and
  stores the result. Having it return the schema avoids an unnecessary DB round-trip and a
  fragile coupling between `_execute_steps` and the internal storage details of `_persist_success`.
  Date/Author: 2026-02-27 / agent (review finding #2)

- Decision: `resume_pipeline` also uses context headers from `metadata_json` when available,
  so behavior is consistent between initial execution and crash recovery.
  Rationale: Without this, `resume_pipeline` would use raw `content_md` for the first remaining
  step's prompt while `_execute_steps` uses context headers for subsequent steps — an
  inconsistency that would confuse debugging and make test coverage awkward.
  Date/Author: 2026-02-27 / agent (review finding #3)

- Decision: Consolidate all audit event logic (both `handoff_created` and
  `handoff_extraction_failed`) into Milestone 2 rather than splitting across milestones.
  Rationale: Both events are written in the same method (`_persist_success`). Splitting them
  across milestones would mean modifying the same method twice and writing tests that don't
  verify the full behavior. A single milestone keeps TDD clean.
  Date/Author: 2026-02-27 / agent (review finding #10)

- Decision: When a heading appears multiple times in the agent output (e.g. two
  `## What Was Done` sections), the first occurrence wins.
  Rationale: Simple, predictable, testable. The agent is expected to produce well-formed output;
  duplicates are an edge case where "first wins" is the least surprising behavior.
  Date/Author: 2026-02-27 / agent (review finding #8)

## Outcomes & Retrospective

All 88 backend tests pass (was 75 before this feature). Three milestones delivered:

- **Milestone 1**: `HandoffSchema` + `HandoffExtractor` — deterministic Markdown heading extraction
  into a typed Pydantic model.
- **Milestone 2**: `PipelineRunner` wired to extract structured handoffs, persist `metadata_json`,
  generate compact context headers for the next agent, and write `handoff_created` /
  `handoff_extraction_failed` audit events.
- **Milestone 3**: `GET /pipelines/{id}` now exposes `steps[*].latest_handoff` with a `metadata`
  dict containing the parsed structured fields.

TDD discipline held throughout: every failing test was written before the implementation. The
post-implementation code-quality review caught 5 MUST FIX issues — 2 pre-existing
(`datetime.utcnow()` in test fixtures) were fixed; 3 pre-existing bugs in the runner/router
(`recover_interrupted_pipelines`, `abort_pipeline` task cancellation, `resume_pipeline` fragility)
were noted for follow-up issues.

## Context and Orientation

The repo root is `theAgency/`. The backend is Python 3.11 / FastAPI in `backend/`. All Python
commands run inside `backend/` with `uv run`. NX targets run from the repo root.

**Architecture**: Hexagonal — domain logic in `backend/app/services/`, external integrations
in `backend/app/adapters/`, HTTP wrappers in `backend/app/routers/`, shared Pydantic schemas
in `backend/app/schemas/`.

**Relevant ORM models** (all in `backend/app/models.py`):

- `Handoff`: `id`, `step_id` (FK -> steps.id), `content_md` (Text, the raw agent output),
  `metadata_json` (Text, nullable — this is where we will store the structured handoff JSON),
  `created_at`.
- `AuditEvent`: `id`, `pipeline_id` (FK -> pipelines.id), `step_id` (FK -> steps.id, nullable),
  `event_type` (String(100)), `payload_json` (Text, nullable), `created_at`.
- `Step`: `id`, `pipeline_id`, `agent_name`, `order_index`, `status`, `started_at`,
  `finished_at`, `handoffs` (relationship), `approvals`, `audit_events`.
- `Pipeline`: `id`, `title`, `template`, `prompt`, `branch`, `status`, `created_at`,
  `updated_at`, `steps` (relationship), `audit_events`.

**PipelineRunner** (in `backend/app/services/pipeline_runner.py`): the core orchestration
service. Key methods involved in this feature:

- `_persist_success(self, step, output_text)` (line 122) — creates a `Handoff` ORM record with
  `content_md=output_text` and currently sets no `metadata_json`. Returns `None`. This method
  will be changed to also call the `HandoffExtractor`, populate `metadata_json`, write audit
  events, and return `HandoffSchema | None`.
- `_execute_steps(self, steps, initial_prompt, pipeline)` (line 137) — iterates over steps,
  calls `run_step` for each, and chains output as the next prompt. Currently uses raw output.
  Will be changed to use `to_context_header()` when extraction succeeds.
- `resume_pipeline(self, pipeline, template)` (line 209) — resumes from the first non-done step.
  Currently reads `latest_handoff.content_md` to build the initial prompt. Will be changed to
  prefer `metadata_json` (parsed as `HandoffSchema.to_context_header()`) when available.

**Important**: Both production and test DB sessions use `expire_on_commit=False`. This means
ORM attributes like `step.pipeline_id` remain accessible after a `db.commit()` without triggering
lazy-loading. The implementation relies on this — specifically when `_persist_success` accesses
`step.pipeline_id` to write `AuditEvent` records after committing the `Handoff`.

**Database session**: `AsyncSession` from `sqlalchemy.ext.asyncio`, with `expire_on_commit=False`
in both production and tests. The `get_db` FastAPI dependency is in `backend/app/database.py`.

**Settings** (`backend/app/config/config.py`): a pydantic-settings `Settings` class. Currently
has `opencode_base_url`, `step_timeout_seconds`, and `database_url`. No new settings are
needed for this feature.

**Existing test infrastructure** (`backend/app/tests/`): `conftest.py` has shared fixtures.
`asyncio_mode = auto` in `pyproject.toml`. All tests use in-memory SQLite. `PipelineRunner`
tests mock `OpenCodeClient` via `AsyncMock(spec=OpenCodeClient)`. No `respx` for PipelineRunner
tests. Currently ~81 tests across all test files.

**API response** (`backend/app/schemas/pipeline.py`): `PipelineDetailResponse` contains
`steps: list[StepStatusResponse]`. `StepStatusResponse` does not currently expose handoff data.
The GET handler at `backend/app/routers/pipelines.py:125` currently uses a one-liner
`PipelineDetailResponse.model_validate(pipeline)` to auto-map from the ORM object. This must
be replaced with manual response construction when we add `latest_handoff`, because the
`Step` ORM object has no `latest_handoff` attribute — it has a `handoffs` list relationship.

**Structured fields**: The four fields that form a HandoffSchema are:
- `what_was_done`: a brief summary of what the agent accomplished (1-3 sentences).
- `decisions_made`: a list of key choices the agent made with brief rationale.
- `open_questions`: unresolved questions or concerns the next agent should be aware of.
- `next_agent_context`: specific instructions or context the next agent needs to proceed.

**Extraction strategy**: Most OpenCode agents produce Markdown output. A heading-based parser
looks for sections whose text matches (case-insensitive) the field names. For example:

    ## What Was Done
    Implemented the login endpoint and wrote 5 tests.

    ## Decisions Made
    - Used JWT over session cookies for statelessness.

    ## Open Questions
    - Should we rate-limit the endpoint?

    ## Next Agent Context
    The endpoint is at POST /auth/login. Tests pass. Next: add refresh token support.

Content before the first recognized heading (e.g. a preamble paragraph) is ignored. If a heading
appears multiple times, the first occurrence wins. If none of the four sections are found, the
extraction is considered failed, a warning is logged, and an `AuditEvent` with
`event_type="handoff_extraction_failed"` is written. The raw `content_md` is preserved and used
as-is for the next step's prompt (existing behavior).

If extraction succeeds (at least one non-empty field), the `HandoffSchema` is serialized to
JSON (using `model_dump_json(exclude_none=True)` for compact storage) and stored in
`Handoff.metadata_json`. A compact context header is generated and used as the next step's
prompt instead of the full raw output.

**Context header format** (injected as the prompt for the next step):

    ## Handoff from previous step (<agent_name>)

    **What was done**: <what_was_done>

    **Decisions made**:
    <decisions_made>

    **Open questions**:
    <open_questions>

    **Your task**: <next_agent_context>

Fields that are None or empty are omitted from the header. The `agent_name` parameter is passed
to `to_context_header(agent_name: str | None = None)` so the next agent knows who produced
the handoff.

## Plan of Work

### Milestone 1 — HandoffSchema + HandoffExtractor

Create `backend/app/schemas/handoff.py` with the Pydantic model. The `is_empty` and
`to_context_header` methods are part of `HandoffSchema`:

    class HandoffSchema(BaseModel):
        what_was_done: str | None = None
        decisions_made: str | None = None
        open_questions: str | None = None
        next_agent_context: str | None = None

        def is_empty(self) -> bool:
            """Return True if all fields are None or empty strings."""
            ...

        def to_context_header(self, agent_name: str | None = None) -> str:
            """Render a compact Markdown context header for the next agent.
            Includes agent_name in the heading if provided.
            Omits fields that are None or empty."""
            ...

Create `backend/app/services/handoff_extractor.py` with the extraction service. The extractor
does NOT log — it returns `None` on failure and the caller is responsible for logging and
audit events:

    class HandoffExtractor:
        """Extracts a structured HandoffSchema from raw Markdown agent output.

        Uses heading-based parsing. Does not log — returns None on failure,
        and the caller handles logging and audit events."""

        def extract(self, content_md: str) -> HandoffSchema | None:
            """Parse Markdown headings to populate HandoffSchema fields.
            Returns None if extraction fails (no recognized sections found,
            or input is empty/whitespace-only)."""

The extraction algorithm: if `content_md` is empty or whitespace-only, return `None` immediately.
Otherwise, split `content_md` on lines. Iterate looking for Markdown headings (lines starting
with one or more `#` characters). When a heading matches one of the four field names
(case-insensitive, ignoring leading `#` characters and surrounding whitespace), collect all
text until the next heading as the field's value. Strip leading/trailing whitespace from the
collected text. If the resulting `HandoffSchema` has all fields None or empty (`.is_empty()`),
return `None`.

The matching logic is lenient: `"what was done"`, `"what_was_done"`, `"whatwasdone"`, and
`"what-was-done"` all match the `what_was_done` field. Normalize by lower-casing and stripping
all non-alphanumeric characters before comparing.

Content before the first recognized heading is ignored. If a heading matches a field that has
already been set (duplicate heading), the first occurrence wins — subsequent matches for the
same field are ignored.

TDD tests in `backend/app/tests/test_handoff_extractor.py`. One test at a time,
red-green-refactor.

Test order:

1. `test_extract_all_four_sections` — Markdown with all four headings in order. Use `##` level.
   Assert all four fields are populated with the expected content.

2. `test_extract_partial_sections` — Markdown with only `what_was_done` and `next_agent_context`.
   Assert those two fields are set, `decisions_made` and `open_questions` are None.

3. `test_extract_returns_none_when_no_sections` — plain prose with no recognizable headings.
   Assert returns None.

4. `test_extract_returns_none_for_empty_input` — empty string and whitespace-only string.
   Assert returns None for both.

5. `test_extract_case_insensitive_headings` — headings in ALL CAPS and MiXeD cAsE.
   Assert all fields matched correctly.

6. `test_extract_strips_whitespace` — extra blank lines between heading and content, leading
   spaces in content lines. Assert fields are stripped.

7. `test_extract_ignores_preamble` — content before the first recognized heading.
   Assert preamble text is not included in any field.

8. `test_extract_duplicate_heading_first_wins` — two `## What Was Done` sections with different
   content. Assert the first occurrence's content is used.

9. `test_to_context_header_all_fields` — populated HandoffSchema renders correct Markdown header
   including agent name.

10. `test_to_context_header_omits_empty_fields` — HandoffSchema with some None fields. Assert
    omitted fields do not appear in header output.

11. `test_to_context_header_without_agent_name` — call `to_context_header()` without agent_name.
    Assert heading is `## Handoff from previous step` (no parenthetical).

12. `test_is_empty_true_when_all_none` — HandoffSchema with all None. Assert `is_empty()`
    returns True.

13. `test_is_empty_false_when_any_field_set` — one field set. Assert `is_empty()` returns False.

### Milestone 2 — Wire Extractor into PipelineRunner + Audit Events

This milestone modifies `PipelineRunner` to use the `HandoffExtractor`, pass structured context
headers to the next agent, and write audit events for all handoff operations. All audit event
logic is consolidated here (not split across milestones) to keep TDD clean.

Modify `backend/app/services/pipeline_runner.py`:

1. Import `HandoffExtractor` from `app.services.handoff_extractor`, `HandoffSchema` from
   `app.schemas.handoff`, `AuditEvent` from `app.models`, and `json` from stdlib.

2. Add a `HandoffExtractor` instance as a constructor parameter (with a default):

       def __init__(
           self,
           client: OpenCodeClient,
           db: AsyncSession,
           step_timeout: float = 600,
           registry: AgentRegistry | None = None,
           extractor: HandoffExtractor | None = None,
       ) -> None:
           ...
           self._extractor = extractor or HandoffExtractor()

3. Change `_persist_success` to return `HandoffSchema | None` (instead of `None`):

       async def _persist_success(self, step: Step, output_text: str) -> HandoffSchema | None:

   The method now does:
   a. Create the `Handoff` ORM record as before.
   b. Call `handoff_schema = self._extractor.extract(output_text)`.
   c. If `handoff_schema` is not None (extraction succeeded):
      - Set `handoff.metadata_json = handoff_schema.model_dump_json(exclude_none=True)`.
      - Log `"handoff_extracted"` at INFO level with `step_id=step.id`.
      - After flush/commit, write `AuditEvent(pipeline_id=step.pipeline_id, step_id=step.id,
        event_type="handoff_created",
        payload_json=json.dumps({"handoff_id": handoff.id, "has_structured_data": True}))`.
   d. If `handoff_schema` is None (extraction failed):
      - Log `"handoff_extraction_failed"` at WARNING level with `step_id=step.id`.
      - After flush/commit, write `AuditEvent(pipeline_id=step.pipeline_id, step_id=step.id,
        event_type="handoff_created",
        payload_json=json.dumps({"handoff_id": handoff.id, "has_structured_data": False}))`.
      - Also write `AuditEvent(pipeline_id=step.pipeline_id, step_id=step.id,
        event_type="handoff_extraction_failed", payload_json=None)`.
   e. Set `step.status = StepStatus.done`, `step.finished_at = datetime.now(UTC)`. Commit.
   f. Return `handoff_schema`.

   Note: `step.pipeline_id` is safe to access after the previous commit because the session
   uses `expire_on_commit=False`. To get `handoff.id` for the audit event payload, call
   `await self._db.flush()` after adding the handoff record (before the final commit), so
   that SQLAlchemy assigns the auto-incremented ID.

4. Update `run_step` to capture the return value of `_persist_success`:

       handoff_schema = await self._persist_success(step, output_text)
       return output_text, handoff_schema

   Change the return type of `run_step` to `tuple[str, HandoffSchema | None]`.

5. Update `_execute_steps` to use the structured context header as the next prompt when
   extraction succeeded. After `output, handoff_schema = await self.run_step(...)`:

       if handoff_schema is not None:
           current_prompt = handoff_schema.to_context_header(agent_name=step.agent_name)
       else:
           current_prompt = output

   This avoids the anti-pattern of querying back the handoff we just wrote.

6. Update `resume_pipeline` for consistency. In the loop that builds `current_prompt` from the
   last done step's handoff (lines 234-239), check `metadata_json` first:

       for step in steps:
           if step.status == StepStatus.done and step.handoffs:
               latest_handoff = max(step.handoffs, key=lambda h: h.id)
               if latest_handoff.metadata_json:
                   schema = HandoffSchema.model_validate_json(latest_handoff.metadata_json)
                   current_prompt = schema.to_context_header(agent_name=step.agent_name)
               else:
                   current_prompt = latest_handoff.content_md

   This ensures crash recovery uses the same context format as initial execution.

TDD additions in `backend/app/tests/test_pipeline_runner.py`:

14. `test_run_step_persists_metadata_json_when_extraction_succeeds` — mock `send_message` to
    return a `MessageResponse` whose text content includes a `## What Was Done` section. Assert
    the resulting `Handoff` row in the DB has a non-None `metadata_json` and that the returned
    tuple includes a `HandoffSchema`.

15. `test_run_step_metadata_json_is_none_when_extraction_fails` — mock `send_message` to return
    plain prose with no recognizable headings. Assert `metadata_json` is None and the returned
    tuple has `None` for the schema.

16. `test_execute_steps_uses_context_header_as_next_prompt` — two-step pipeline where step 1
    returns structured Markdown. Assert step 2's `send_message` is called with a prompt that
    starts with `"## Handoff from previous step"`.

17. `test_execute_steps_falls_back_to_raw_output_when_extraction_fails` — step 1 returns plain
    prose. Assert step 2's prompt equals the raw output text (not a context header).

18. `test_audit_event_handoff_created_written_on_success` — assert an `AuditEvent` row with
    `event_type="handoff_created"` and `has_structured_data: true` in payload exists after a
    step with structured output.

19. `test_audit_event_handoff_extraction_failed_written_on_failure` — assert both a
    `handoff_created` event (with `has_structured_data: false`) and a `handoff_extraction_failed`
    event exist when agent output has no structured sections.

20. `test_resume_pipeline_uses_context_header_from_metadata_json` — step 1 is done with a
    handoff that has `metadata_json` set. Assert step 2's prompt starts with
    `"## Handoff from previous step"` (not raw `content_md`).

### Milestone 3 — Expose Handoff Metadata in API Response

The `GET /pipelines/{id}` endpoint currently returns step statuses but no handoff data. After
this milestone it returns each step's latest handoff with structured metadata.

Add to `backend/app/schemas/pipeline.py`:

    class HandoffResponse(BaseModel):
        """Handoff data for a single step. Constructed manually — not via ORM auto-mapping,
        because the ORM Handoff model stores metadata as a JSON string (metadata_json)
        while this schema exposes it as a parsed dict."""

        id: int
        content_md: str
        metadata: dict | None = None
        created_at: datetime

Note: `HandoffResponse` does NOT use `ConfigDict(from_attributes=True)` because it is always
constructed manually. The ORM `Handoff` model has `metadata_json` (a JSON string), not
`metadata` (a dict). Automatic ORM mapping would fail to find a `metadata` attribute.

Modify `StepStatusResponse` to include an optional handoff field:

    class StepStatusResponse(BaseModel):
        model_config = ConfigDict(from_attributes=True)
        id: int
        agent_name: str
        order_index: int
        status: StepStatus
        started_at: datetime | None
        finished_at: datetime | None
        latest_handoff: HandoffResponse | None = None

In `backend/app/routers/pipelines.py`, the `GET /pipelines/{pipeline_id}` handler must be
refactored. The current one-liner `PipelineDetailResponse.model_validate(pipeline)` (line 125)
will NOT work with the new `latest_handoff` field because the `Step` ORM object has no
`latest_handoff` attribute — it has a `handoffs` list. The handler must:

1. Extend the eager load to include handoffs:
   `selectinload(Pipeline.steps).selectinload(Step.handoffs)`

2. Replace the `model_validate` one-liner with manual response construction:

       step_responses = []
       for step in pipeline.steps:
           latest = max(step.handoffs, key=lambda h: h.id) if step.handoffs else None
           metadata = json.loads(latest.metadata_json) if latest and latest.metadata_json else None
           handoff_resp = HandoffResponse(
               id=latest.id,
               content_md=latest.content_md,
               metadata=metadata,
               created_at=latest.created_at,
           ) if latest else None
           step_resp = StepStatusResponse(
               id=step.id,
               agent_name=step.agent_name,
               order_index=step.order_index,
               status=step.status,
               started_at=step.started_at,
               finished_at=step.finished_at,
               latest_handoff=handoff_resp,
           )
           step_responses.append(step_resp)

       return PipelineDetailResponse(
           id=pipeline.id,
           title=pipeline.title,
           template=pipeline.template,
           status=pipeline.status,
           created_at=pipeline.created_at,
           updated_at=pipeline.updated_at,
           steps=step_responses,
       )

TDD additions in `backend/app/tests/test_pipelines_router.py`:

21. `test_get_pipeline_includes_latest_handoff` — create a pipeline with one done step and a
    persisted handoff with `metadata_json` set. Assert the GET response's
    `steps[0].latest_handoff` is non-null, `metadata` contains the expected keys
    (`what_was_done`, etc.), and `content_md` is present.

22. `test_get_pipeline_handoff_null_when_no_handoff` — step with no handoff rows. Assert
    `latest_handoff` is None in the response.

## Concrete Steps

All NX commands from the repo root. Manual `uv` commands from `backend/`.

    # No new dependencies required — pydantic, sqlalchemy, json stdlib all already present.

    # Run tests after each milestone
    npx nx run backend:test

    # Lint
    npx nx run backend:lint

    # Type-check frontend (must stay clean)
    npx nx run frontend:type-check

    # Start server for manual verification (OpenCode must be running separately)
    npx nx run backend:serve

    # Create a pipeline and inspect the handoff metadata
    curl -X POST http://localhost:8000/pipelines \
      -H "Content-Type: application/json" \
      -d '{"template": "quick_fix", "title": "Test handoff", "prompt": "Fix the login button."}'

    # Poll status and check handoff metadata
    curl http://localhost:8000/pipelines/1 | python3 -m json.tool

## Validation and Acceptance

After all milestones:

1. `npx nx run backend:test` passes — ~81 existing + ~22 new = ~103 tests total.
2. `npx nx run backend:lint` exits clean.
3. `npx nx run frontend:type-check` exits clean.
4. `GET /pipelines/{id}` response contains `steps[*].latest_handoff` with a `metadata` field
   that includes `what_was_done`, `decisions_made`, `open_questions`, `next_agent_context`
   for steps whose agent produced structured output.
5. For a step where the agent produced no structured Markdown, `metadata` is null and two
   `AuditEvent` rows exist: one `handoff_created` (has_structured_data: false) and one
   `handoff_extraction_failed`.
6. Crash recovery uses context headers from `metadata_json` when available, consistent with
   initial execution.

## Idempotence and Recovery

No Alembic migrations are needed. The `metadata_json` column already exists. All new code is
additive. Tests use in-memory SQLite created fresh per test — safe to re-run indefinitely.
The `HandoffExtractor` is stateless and produces the same output for the same input.

## Artifacts and Notes

**No LLM extraction in MVP**: The issue mentions "ggf. LLM-Extraktion falls Agent keinen
strukturierten Output liefert" (possibly LLM extraction if agent output is unstructured). We
implement deterministic Markdown-heading extraction only. LLM extraction is deferred — the
`HandoffExtractor` class is designed to be extended (e.g. with a subclass or strategy pattern)
without changing any call sites.

**Existing `Handoff` model is sufficient**: The `metadata_json` Text column already exists in
the ORM model and the DB schema. No migration needed.

**Import of `json`**: The stdlib `json` module is used to serialize/deserialize `metadata_json`
in the router. `HandoffSchema.model_dump_json()` handles serialization in the service layer.
No new package dependencies are added.

**`expire_on_commit=False` dependency**: The `_persist_success` method accesses `step.pipeline_id`
and `handoff.id` after `flush()`/`commit()` calls. This works because both production and test
sessions use `expire_on_commit=False`, which prevents SQLAlchemy from expiring attribute state
after a commit. If this session setting were ever changed, these accesses would raise
`MissingGreenlet` errors. This is an existing pattern in the codebase (PipelineRunner already
relies on it) and not a new concern introduced by this feature.

## Interfaces and Dependencies

No new Python packages. All existing: `pydantic`, `sqlalchemy[asyncio]`, `aiosqlite`,
`fastapi`, `structlog`, `json` (stdlib).

New files:

    backend/app/schemas/handoff.py            — HandoffSchema Pydantic model + to_context_header + is_empty
    backend/app/services/handoff_extractor.py  — HandoffExtractor.extract()
    backend/app/tests/test_handoff_extractor.py — 13 tests for extraction and schema logic

Modified files:

    backend/app/services/pipeline_runner.py    — wire extractor, return schema, context headers, audit events
    backend/app/schemas/pipeline.py            — add HandoffResponse, extend StepStatusResponse
    backend/app/routers/pipelines.py           — eager-load handoffs, manual response construction in GET
    backend/app/tests/test_pipeline_runner.py  — 7 new tests (Milestone 2)
    backend/app/tests/test_pipelines_router.py — 2 new tests (Milestone 3)

Key signatures at end of implementation:

In `backend/app/schemas/handoff.py`:

    class HandoffSchema(BaseModel):
        what_was_done: str | None = None
        decisions_made: str | None = None
        open_questions: str | None = None
        next_agent_context: str | None = None

        def is_empty(self) -> bool: ...
        def to_context_header(self, agent_name: str | None = None) -> str: ...

In `backend/app/services/handoff_extractor.py`:

    class HandoffExtractor:
        def extract(self, content_md: str) -> HandoffSchema | None: ...

In `backend/app/schemas/pipeline.py` (additions):

    class HandoffResponse(BaseModel):
        id: int
        content_md: str
        metadata: dict | None = None
        created_at: datetime

    class StepStatusResponse(BaseModel):
        ...
        latest_handoff: HandoffResponse | None = None

In `backend/app/services/pipeline_runner.py` (changes):

    class PipelineRunner:
        def __init__(self, ..., extractor: HandoffExtractor | None = None) -> None: ...
        async def run_step(self, step, agent_profile, prompt) -> tuple[str, HandoffSchema | None]: ...
        async def _persist_success(self, step, output_text) -> HandoffSchema | None: ...
