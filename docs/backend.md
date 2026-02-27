# Backend Guidelines

Python 3.11+
**ruff enforced, line-length=120.**

## Architecture
- Hexagonal (Ports & Adapters) architecture. Core domain logic in `services/` with no external dependencies. Adapters for LLM providers, databases, etc. in `adapters/`.
- Dependency injection via constructor parameters. No global state or singletons.

## Logging

```python
import structlog
logger = structlog.get_logger(__name__)
```

Structured JSON output via structlog. Sanitize user input with `sanitize_log_param()`.

## Error Handling

Wrap route handlers in try/except. Raise `HTTPException` with appropriate status codes. Log errors before re-raising. Catch specific exceptions before generic `Exception`.

Retry logic with tenacity:

```python
@retry(stop=stop_after_attempt(5), wait=wait_exponential(min=4, max=60))
def call_llm_api(...):
    ...
```

### Writing migrations

Follow the **Expand/Contract** strategy for zero-downtime changes:

1. **Expand** — add new columns/tables as nullable or with defaults; old code still works unmodified.
2. **Backfill** — migrate existing data in a follow-up migration or background job.
3. **Contract** — once all instances run the new code, drop old columns/tables in a subsequent deploy.

Never drop a column or rename a column in the same migration that the new code first reads from it.

### Rules

- One concern per migration file. Never combine DDL and large data backfills in the same revision.
- All new columns must be `nullable=True` or carry a server-side `DEFAULT` so the existing application can insert rows without the column.
- Migrations must be **idempotent**: use `IF NOT EXISTS` / `IF EXISTS` guards in raw SQL, or Alembic's `checkfirst=True`.
- **Never** use `alembic downgrade` in production without an explicit runbook. The CD pipeline only runs `upgrade head`.
- If a migration takes more than a few seconds (e.g. backfilling millions of rows), use a background job or a separate Alembic revision with batching instead.

### `alembic/env.py` specifics

- Escape `%` → `%%` in the `DATABASE_URL` before calling `config.set_main_option`, because `configparser` treats `%` as interpolation syntax and RDS auto-generated passwords may contain it:

```python
db_url = settings.database_url.replace("%", "%%")
config.set_main_option("sqlalchemy.url", db_url)
```

### Running migrations locally

```bash
nx run backend:migrate          # upgrade head
nx run backend:migrate-down     # downgrade -1 (dev only)
nx run backend:makemigration    # autogenerate new revision
```

## Config

All constants in `config/config.py`. Env vars via `pydantic-settings`.

## Models

Pydantic `BaseModel` for request/response. Define in the file where used.

## Testing (pytest)

- Group in classes: `class TestHelperUtils:`
- Naming: `test_<what>_<scenario>` (e.g., `test_extract_json_dict_simple`)
- Fixtures: `pytest.fixture` for setup; `unittest.mock` (`patch`, `MagicMock`) for externals
- Coverage: `--cov=src --cov-report=term-missing --cov-fail-under=55`
- `asyncio_mode = auto` — no manual `@pytest.mark.asyncio` needed
- **Never delete or skip failing tests.** Fix the implementation or the test.

### Mocking — Minimize It

**Mock only external I/O boundaries, not internal logic.**

Mock these:
- LLM API calls (`openai.ChatCompletion`, `genai.GenerativeModel`)
- External HTTP requests (`httpx`, `requests`)
- File I/O when testing non-I/O logic
- Time/date functions (`datetime.now()`)

Never mock these:
- **The subject under test** — patching a method on the SUT (e.g. `patch.object(dispatcher, "dispatch", ...)` inside a test for `redispatch_recovered`) bypasses the real code path. Inject mock collaborators via the constructor and assert on those instead.
- Utility functions (`extract_json_dict`, `sanitize_log_param`)
- Business logic (requirement analysis, validation)
- Pydantic model validation
- Internal services calling each other

Prefer real objects:
- Use testcontainers for database  etc. 
