# Audit Trail — Issue #9

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

After this change any operator can query the full history of every pipeline execution:
which steps ran, when they started and finished, what the agent produced, which approvals
were requested and by whom they were decided. A `GET /audit` endpoint lets callers filter
by pipeline, step, event type, and date. Export endpoints deliver the same data as JSON
or Markdown. A configurable retention policy deletes events older than N days.

The data layer already exists: `AuditEvent` rows are written by `pipeline_runner.py`
for every handoff and every approval state transition. This feature exposes that data
over HTTP and adds the retention job.

## Progress

- [x] (2026-02-27 12:00Z) ExecPlan written.
- [x] (2026-02-27 12:10Z) Milestone 1: `GET /audit` endpoint with filter parameters — 7 tests pass (including offset pagination).
- [x] (2026-02-27 12:20Z) Milestone 2: Export endpoints (`GET /audit/export?export_format=json` and `?export_format=markdown`) — 3 tests pass.
- [x] (2026-02-27 12:30Z) Milestone 3: Retention policy — `POST /audit/retention` — 3 tests pass.
- [x] (2026-02-27 13:00Z) Post-implementation code-quality review — all MUST FIX / SHOULD FIX resolved (see Discoveries).
- [x] (2026-02-27 13:05Z) 123/123 backend tests passing, ruff clean.
- [ ] Commit (code + ExecPlan together).
- [ ] ExecPlan moved to completed/, issue closed.

## Surprises & Discoveries

- Discovery: `format` is a Python builtin; naming the export query parameter `format` shadowed it and bypassed FastAPI's
  Pydantic validation. Renamed to `export_format` and declared as `Literal["json", "markdown"]` — FastAPI now validates
  it automatically and returns a properly structured 422 on unknown values.

- Discovery: `_query_audit_events` had 8 positional parameters, a classic Long Parameter List smell. Introduced
  `AuditFilter` dataclass to group all filter fields into a single value object passed to the helper.

- Discovery: `result.rowcount` from `db.execute(delete(...))` — the static type is `Result[Any]` (which doesn't expose
  `rowcount`), but at runtime SQLAlchemy returns a `CursorResult`. Fixed with an explicit `CursorResult` type annotation
  on the variable, suppressed with a single `# type: ignore[assignment]` at the assignment site only.

- Discovery: The original `if payload` guard in `_seed_event` was falsy for `{}`, which would have stored an empty dict
  as `NULL`. Fixed to `if payload is not None`.

- Discovery: `app.dependency_overrides.clear()` in the test fixture teardown was not guarded by `try/finally`, risking
  state leakage between tests on exception. Wrapped in `try/finally`.

- Discovery: Markdown table cells were not pipe-escaped. Added `.replace("|", "\\|")` for event_type and payload fields.

## Decision Log

- Decision: Implement audit trail as a read-only `GET /audit` endpoint plus two export endpoints; retention is a `POST /audit/retention` action endpoint (not a background daemon for simplicity).
  Rationale: keeps scope manageable, fully testable, and avoids scheduler complexity. The dashboard can display and export directly.
  Date/Author: 2026-02-27 / agent

- Decision: Export endpoints return the full `AuditEvent` list (same filtering as `GET /audit`) serialised to JSON or Markdown. No streaming — the corpus is small enough for SQLite.
  Rationale: simple and deterministic; streaming would complicate tests.
  Date/Author: 2026-02-27 / agent

- Decision: Renamed export query parameter from `format` to `export_format` and typed as `Literal["json", "markdown"]`.
  Rationale: `format` shadows a Python builtin and bypasses FastAPI's validation envelope. `Literal` gives a proper 422 for free.
  Date/Author: 2026-02-27 / agent

- Decision: Introduced `AuditFilter` dataclass to replace the 8-argument signature on `_query_audit_events`.
  Rationale: reduces call-site fragility, makes adding new filter dimensions a single-place change, improves readability.
  Date/Author: 2026-02-27 / agent

- Decision: Added `_EXPORT_DEFAULT_LIMIT = 500` separate from `_MAX_LIMIT = 500`.
  Rationale: the two constants serve different semantic roles (hard server cap vs. export batch default). Keeping them separate allows them to diverge independently.
  Date/Author: 2026-02-27 / agent

## Outcomes & Retrospective

All three milestones delivered and fully tested (14 tests for the audit router alone, 123 total backend tests passing).
The API surface is clean: `GET /audit` with filters, `GET /audit/export?export_format=json|markdown`, `POST /audit/retention`.
Code quality review caught several real issues (`format` builtin shadow, long parameter list, unguarded teardown) that were
all resolved before committing. The `AuditFilter` dataclass is a genuine improvement over the original design.

## Context and Orientation

The repository is a Python/FastAPI backend (`backend/app/`). The relevant files are:

- `backend/app/models.py` — `AuditEvent` ORM model. Columns: `id`, `pipeline_id` (FK→pipelines), `step_id` (FK→steps, nullable), `event_type` (string e.g. `"handoff_created"`, `"approval_granted"`), `payload_json` (serialised dict), `created_at` (DateTime).
- `backend/app/services/pipeline_runner.py` — already writes `AuditEvent` rows at key lifecycle points.
- `backend/app/routers/audit.py` — new file; registered in `main.py`.
- `backend/app/schemas/audit.py` — new file with `AuditEventResponse`, `RetentionRequest`, `RetentionResponse`.
- `backend/app/tests/test_audit_router.py` — new file with 14 tests.

Known event_type values written by the runner: `handoff_created`, `handoff_extraction_failed`, `approval_requested`, `approval_granted`, `approval_rejected`.

The test setup uses an in-memory SQLite database, `asyncio_mode = auto` (set globally in `pyproject.toml`), `expire_on_commit=False`. All router tests use `httpx.AsyncClient` over `ASGITransport`.

## Plan of Work

### Milestone 1 — GET /audit

Create `backend/app/schemas/audit.py` with `AuditEventResponse`:

    class AuditEventResponse(BaseModel):
        id: int
        pipeline_id: int
        step_id: int | None
        event_type: str
        payload: dict | None   # parsed from payload_json
        created_at: datetime

Note `payload` is the parsed dict, not the raw JSON string — we construct this manually (not `from_attributes`) because `AuditEvent.payload_json` is a raw string.

Create `backend/app/routers/audit.py` with an `APIRouter(prefix="/audit", tags=["audit"])`.

Add `GET /audit` with these optional query parameters: `pipeline_id`, `step_id`, `event_type`, `since`, `until`, `limit` (default 100, cap 500), `offset` (default 0). The query uses SQLAlchemy `select(AuditEvent)` with `.where()` clauses applied conditionally via an `AuditFilter` dataclass. Order by `created_at DESC`. Return `list[AuditEventResponse]`.

Register the router in `main.py`: `app.include_router(audit_router.router)`.

### Milestone 2 — Export endpoints

`GET /audit/export` with query param `export_format: Literal["json", "markdown"] = "json"`. Applies the same filter params as `GET /audit` (reuses `_query_audit_events`). JSON response includes `Content-Disposition: attachment; filename="audit.json"`; Markdown response is a table with pipe-escaped values.

### Milestone 3 — Retention policy

`POST /audit/retention` with body `RetentionRequest(older_than_days: int = Field(ge=1))`. Executes `DELETE FROM audit_events WHERE created_at < cutoff`. Returns `RetentionResponse(deleted_count: int)`.

## Concrete Steps

All commands run from `backend/`:

    uv run pytest app/tests/ -q        # baseline: 109 passed (pre-implementation)

After all milestones:

    uv run pytest app/tests/ -q        # 123 passed
    uv run ruff check app/ --fix       # All checks passed!

## Validation and Acceptance

After starting the server (`uv run uvicorn app.main:app --reload`), the following HTTP
interactions demonstrate the feature:

1. `GET /audit` → returns `[]` on a fresh database.
2. Run a pipeline (via `POST /pipelines`) → audit events are written by the runner.
3. `GET /audit?pipeline_id=1` → returns events for that pipeline.
4. `GET /audit/export?export_format=json` → downloads `audit.json`.
5. `GET /audit/export?export_format=markdown` → downloads `audit.md`.
6. `POST /audit/retention` with `{"older_than_days": 1}` → returns `{"deleted_count": 0}` on fresh data.

## Idempotence and Recovery

The retention endpoint uses a single `DELETE` statement — safe to retry.
The `GET` and export endpoints are pure reads — fully idempotent.

## Interfaces and Dependencies

In `backend/app/schemas/audit.py`:

    class AuditEventResponse(BaseModel):
        id: int
        pipeline_id: int
        step_id: int | None
        event_type: str
        payload: dict | None
        created_at: datetime

    class RetentionRequest(BaseModel):
        older_than_days: int = Field(ge=1)

    class RetentionResponse(BaseModel):
        deleted_count: int

In `backend/app/routers/audit.py`:

    router = APIRouter(prefix="/audit", tags=["audit"])

    @router.get("", response_model=list[AuditEventResponse])
    async def list_audit_events(pipeline_id, step_id, event_type, since, until, limit, offset, db): ...

    @router.get("/export")
    async def export_audit_events(export_format: Literal["json", "markdown"], pipeline_id, ..., db): ...

    @router.post("/retention", response_model=RetentionResponse)
    async def apply_retention(body: RetentionRequest, db): ...
