# Issue #13 — GitHub Issue as Context

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

When creating a new pipeline, the user can optionally link a GitHub issue. The backend
fetches that issue's title, body, and labels from the GitHub API and prepends a formatted
summary to the pipeline's prompt before persisting it. The frontend shows an optional
"GitHub Issue" panel in the New Pipeline modal: the user enters a repo slug and issue
number, clicks "Fetch", sees a preview of the issue title, and the enriched prompt is
baked into the pipeline on creation.

After this change, a user can say "run pipeline on issue owner/repo#42" and the pipeline
runner will automatically receive the full issue context without copy-pasting.

## Progress

- [x] (2026-02-27 12:00Z) Write ExecPlan (this file)
- [x] (2026-02-27 12:10Z) Backend M1: GitHubClient adapter + GitHubIssue model
- [x] (2026-02-27 12:15Z) Backend M1: Add github_token to Settings; wire GitHubClient into app.state in lifespan
- [x] (2026-02-27 12:20Z) Backend M1: Add GET /registry/github-issue endpoint + GitHubIssueResponse schema
- [x] (2026-02-27 12:30Z) Backend M1: Tests pass (red → green) — 3 tests in TestRegistryRouterGitHubIssue
- [x] (2026-02-27 12:35Z) Backend M2: Extend PipelineCreateRequest with github_issue_repo + github_issue_number
- [x] (2026-02-28 10:00Z) Backend M2: Router enriches prompt at create time when issue fields are provided
- [x] (2026-02-28 10:10Z) Backend M2: New router tests pass (red → green) — 3 tests in TestCreatePipelineGitHubEnrichment; 164 total passing
- [x] (2026-02-28 10:20Z) Frontend M3: Add AgentProfileResponse + GitHubIssueResponse to types/api.ts
- [x] (2026-02-28 10:20Z) Frontend M3: Add fetchGitHubIssue() to api/client.ts
- [x] (2026-02-28 10:25Z) Frontend M3: Add GitHub Issue panel to NewPipelineModal (collapsible <details> section)
- [x] (2026-02-28 10:30Z) Frontend M3: tsc --noEmit passes with 0 errors
- [x] (2026-02-27 15:00Z) ExecPlan finalized: all code-quality fixes applied, 164 tests pass, type-check passes, plan moved to completed/

## Surprises & Discoveries

- Discovery: `app.state.github_client` is set to `None` when `GITHUB_TOKEN` is absent — endpoint returns 503 as designed.
  Evidence: `test_get_github_issue_no_token_returns_503` passes.

- Discovery: The prompt enrichment uses graceful degradation on fetch failure — if the GitHub API call raises any exception (including 404), the original prompt is stored unchanged and a structured warning is logged.
  Evidence: `test_prompt_enrichment_failed_fetch_falls_back_to_original` passes.

- Discovery: `respx.mock` should be used as a context manager (not a decorator) for proper isolation — ensures the mock is only active during the specific HTTP call, not for the entire async method.
  Evidence: Refactored `test_prompt_enriched_with_github_issue` and `test_prompt_enrichment_failed_fetch_falls_back_to_original` to use `with respx.mock:` context manager combined with `with patch(...)`.

- Discovery: Bare `except Exception` in the enrichment path was replaced with `except GitHubClientError` so only expected failures degrade gracefully; unexpected errors propagate. Also added `logger.info("github_issue_skipped_no_token")` when the client is None but repo/number were provided.

## Decision Log

- Decision: Backend enriches the prompt at create time (bakes content into pipeline.prompt)
  rather than storing issue_number as a foreign key and fetching at run time.
  Rationale: Simpler — no live dependency on GitHub at run time. Pipeline prompt is
  self-contained. Easy to inspect in DB what context the agents received.
  Date/Author: 2026-02-27 / Josie

- Decision: Frontend calls GET /registry/github-issue to preview the issue title before
  submit; on submit it sends github_issue_repo + github_issue_number in PipelineCreateRequest
  and the backend performs the actual enrichment. This avoids duplicating fetch logic on the
  frontend and keeps the prompt baking in one place.
  Date/Author: 2026-02-27 / Josie

- Decision: When GITHUB_TOKEN is absent, the github_client on app.state is None and the
  endpoint returns HTTP 503 with a clear message. The pipeline create endpoint skips
  enrichment gracefully (no token = no enrichment, no error).
  Date/Author: 2026-02-27 / Josie

## Outcomes & Retrospective

All three milestones are complete. The backend can now fetch a GitHub issue and prepend its title, body, and labels to the pipeline prompt at create time. The frontend shows a collapsible "GitHub Issue" panel in the New Pipeline modal where the user can enter a repo slug and issue number, click Fetch to preview the issue title, and submit — the enriched prompt is stored in the DB.

164 backend tests pass. Frontend type-check passes with 0 errors. No regressions.

## Context and Orientation

The repo is a monorepo: a Python/FastAPI backend under `backend/` and a Vite/React/TypeScript
frontend under `frontend/`. The backend uses SQLAlchemy 2.x async + SQLite, Pydantic v2 for
schemas, structlog for logging, and httpx for HTTP. Tests use pytest-asyncio with
asyncio_mode="auto" (no per-test markers needed). The package manager is `uv`; run tests with
`npx nx run backend:test` from the repo root.

Key backend files:
- `backend/app/adapters/opencode_client.py` — reference implementation of an httpx-based
  adapter. Copy its pattern for GitHubClient.
- `backend/app/adapters/opencode_models.py` — reference for Pydantic response models used
  by the adapter.
- `backend/app/config/config.py` — Settings class (pydantic-settings, reads from .env).
- `backend/app/main.py` — FastAPI lifespan: initialises adapters and attaches them to
  app.state. Everything injected via FastAPI dependency injection.
- `backend/app/routers/registry.py` — existing registry router; add the new endpoint here.
- `backend/app/schemas/registry.py` — Pydantic schemas for registry responses; add
  GitHubIssueResponse here.
- `backend/app/schemas/pipeline.py` — PipelineCreateRequest; add github_issue_* fields here.
- `backend/app/routers/pipelines.py` — create_pipeline endpoint; enrich prompt here.
- `backend/app/tests/test_registry_router.py` — registry router tests (may not exist yet;
  create if needed).
- `backend/app/tests/test_pipelines_router.py` — pipeline router tests; add enrichment tests.

Key frontend files:
- `frontend/src/types/api.ts` — TypeScript interfaces matching the API.
- `frontend/src/api/client.ts` — typed HTTP helper functions.
- `frontend/src/components/NewPipelineModal.tsx` — the modal for creating pipelines.

## Plan of Work

### Milestone 1 — GitHubClient adapter + preview endpoint

Create `backend/app/adapters/github_models.py` with a `GitHubIssue` Pydantic model:

    class GitHubIssue(BaseModel):
        number: int
        title: str
        body: str | None = None
        labels: list[str] = []

Create `backend/app/adapters/github_client.py` with a `GitHubClient` class modelled exactly
after `opencode_client.py`. It uses `httpx.AsyncClient` with base URL
`https://api.github.com`. The constructor accepts an optional `token: str | None`. If token
is provided, set the `Authorization: Bearer <token>` header on all requests. One method:

    async def get_issue(self, repo: str, number: int) -> GitHubIssue

`repo` is `owner/repo` (e.g. `DavidSchwarz2/theAgency`). The GitHub API endpoint is
`GET /repos/{repo}/issues/{number}`. Parse `labels` from `response["labels"]` — each label
object has a `"name"` key. If the response is 404, raise a `GitHubClientError` (404). Any
non-2xx raises `GitHubClientError`.

Add `github_token: str | None = None` to `Settings` in `backend/app/config/config.py`.

In `backend/app/main.py` lifespan: after the opencode_client setup, add:

    from app.adapters.github_client import GitHubClient
    github_client = GitHubClient(token=settings.github_token) if settings.github_token else None
    app.state.github_client = github_client

Add `GitHubIssueResponse` to `backend/app/schemas/registry.py`:

    class GitHubIssueResponse(BaseModel):
        number: int
        title: str
        body: str | None = None
        labels: list[str] = []

Add the endpoint to `backend/app/routers/registry.py`:

    GET /registry/github-issue?repo=owner/repo&number=42

This endpoint needs `app.state.github_client`. Add a FastAPI dependency function
`get_github_client(request: Request) -> GitHubClient | None` that reads
`request.app.state.github_client`. The endpoint handler:
- If `github_client` is None → raise HTTPException 503 "GitHub token not configured"
- Call `github_client.get_issue(repo, number)`
- On GitHubClientError with status_code 404 → raise HTTPException 404
- On other GitHubClientError → raise HTTPException 502
- Return `GitHubIssueResponse` from the adapter result

Write tests in `backend/app/tests/test_registry_router.py` (create the file). Use `respx`
to mock the GitHub API. Tests: happy path returns 200 + correct fields; 503 when no token;
404 when issue not found.

### Milestone 2 — Prompt enrichment on pipeline create

Add to `PipelineCreateRequest` in `backend/app/schemas/pipeline.py`:

    github_issue_repo: str | None = None
    github_issue_number: int | None = None

In `create_pipeline` in `backend/app/routers/pipelines.py`, after resolving the template
and before creating the Pipeline ORM record:

    enriched_prompt = body.prompt
    if body.github_issue_repo and body.github_issue_number:
        github_client: GitHubClient | None = request.app.state.github_client
        if github_client is not None:
            try:
                issue = await github_client.get_issue(body.github_issue_repo, body.github_issue_number)
                issue_block = (
                    f"## GitHub Issue #{issue.number}: {issue.title}\n\n"
                    + (issue.body or "")
                    + ("\n\nLabels: " + ", ".join(issue.labels) if issue.labels else "")
                )
                enriched_prompt = issue_block + "\n\n---\n\n" + body.prompt
            except Exception:
                logger.warning("github_issue_fetch_failed", repo=body.github_issue_repo,
                               number=body.github_issue_number, exc_info=True)

Then use `enriched_prompt` when constructing the `Pipeline` ORM object instead of
`body.prompt`.

Write tests for the enrichment path in `test_pipelines_router.py`.

### Milestone 3 — Frontend GitHub Issue panel

In `frontend/src/types/api.ts`, add:

    export interface GitHubIssueResponse {
      number: number
      title: string
      body: string | null
      labels: string[]
    }

Also update `PipelineCreateRequest` to add:

    github_issue_repo?: string
    github_issue_number?: number

In `frontend/src/api/client.ts`, add:

    export function fetchGitHubIssue(repo: string, number: number): Promise<GitHubIssueResponse> {
      return apiFetch<GitHubIssueResponse>(`/registry/github-issue?repo=${encodeURIComponent(repo)}&number=${number}`)
    }

In `NewPipelineModal.tsx`, add an optional collapsible "GitHub Issue" section below the
prompt field. It has two inputs: `repo` (placeholder `owner/repo`) and `issueNumber`
(number input). A "Fetch" button calls `fetchGitHubIssue` and shows the issue title as a
preview. The repo and issue number are included in the `createPipeline.mutate(...)` call
when set (as `github_issue_repo` and `github_issue_number`). Handle fetch errors gracefully
(show an inline error message).

## Concrete Steps

All commands run from the repo root unless stated otherwise.

1. Create `backend/app/adapters/github_models.py`
2. Create `backend/app/adapters/github_client.py`
3. Edit `backend/app/config/config.py` — add `github_token`
4. Edit `backend/app/main.py` — wire GitHubClient into app.state
5. Edit `backend/app/schemas/registry.py` — add GitHubIssueResponse
6. Edit `backend/app/routers/registry.py` — add GET /registry/github-issue
7. Create `backend/app/tests/test_registry_router.py` — write tests first (TDD)
8. Run `npx nx run backend:test` — verify new tests pass
9. Edit `backend/app/schemas/pipeline.py` — add github_issue_* fields
10. Edit `backend/app/routers/pipelines.py` — add enrichment logic
11. Add enrichment tests to `backend/app/tests/test_pipelines_router.py`
12. Run `npx nx run backend:test` — verify all pass
13. Edit `frontend/src/types/api.ts`
14. Edit `frontend/src/api/client.ts`
15. Edit `frontend/src/components/NewPipelineModal.tsx`
16. Run `npx nx run frontend:type-check`

## Validation and Acceptance

- `npx nx run backend:test` passes with no failures.
- `npx nx run frontend:type-check` passes with no errors.
- Manual: POST /pipelines with `github_issue_repo="DavidSchwarz2/theAgency"` and
  `github_issue_number=13` (once token is set in `.env`) creates a pipeline whose stored
  `prompt` begins with `## GitHub Issue #13:`.
- GET /registry/github-issue?repo=DavidSchwarz2/theAgency&number=13 returns 200 with
  `number`, `title`, `body`, `labels`.
- GET /registry/github-issue without token returns 503.

## Idempotence and Recovery

Steps 1–16 can be re-run safely. The GitHubClient is a pure HTTP wrapper — no side effects
on re-creation. If a test fails mid-run, fix the code and re-run `npx nx run backend:test`.

## Interfaces and Dependencies

In `backend/app/adapters/github_client.py`:

    class GitHubClientError(Exception):
        def __init__(self, message: str, status_code: int | None = None) -> None: ...

    class GitHubClient:
        def __init__(self, token: str | None = None) -> None: ...
        async def close(self) -> None: ...
        async def get_issue(self, repo: str, number: int) -> GitHubIssue: ...

In `backend/app/adapters/github_models.py`:

    class GitHubIssue(BaseModel):
        number: int
        title: str
        body: str | None = None
        labels: list[str] = []
