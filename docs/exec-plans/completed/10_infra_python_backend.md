# Infra: Python Backend + Next.js Frontend Setup

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

theAgency is an AI Development Pipeline Orchestrator. It lets a developer hand a feature
description to a configurable chain of specialised OpenCode agents (product-owner, architect,
developer, senior-reviewer, …) and watch them work through it autonomously, step by step,
handing off structured context between each other.

After this plan is complete, a developer can clone the repo, run `docker compose up` (or a
simple `make dev`), and have a working skeleton with:

- A FastAPI backend answering `GET /health` → `{"status": "ok"}` on port 8000
- A Server-Sent Events endpoint `GET /events` streaming heartbeats
- A Next.js frontend at port 3000 showing a minimal dashboard stub
- A SQLite database with the initial schema (pipelines, steps, handoffs, audit_events,
  approvals)
- Alembic wired up so the first migration runs automatically on backend start
- NX monorepo wiring + mise toolchain configured
- ruff linting (line-length=120), structlog, Hexagonal architecture skeleton

The goal of this milestone is purely infrastructure — no business logic yet. The plumbing must
be sound before the agents can run through it.

## Progress

- [x] (2026-02-27 08:30Z) Removed Kotlin/Gradle scaffold, rewrote .gitignore
- [x] (2026-02-27 08:35Z) ExecPlan drafted
- [x] (2026-02-27 09:00Z) ExecPlan updated for NX/mise/Next.js/Hexagonal arch after reading backend.md
- [x] (2026-02-27 09:15Z) NX monorepo + mise toolchain setup (package.json, nx.json, .mise.toml)
- [x] (2026-02-27 09:20Z) Backend: directory structure + pyproject.toml (Hexagonal: services/, adapters/)
- [x] (2026-02-27 09:20Z) Backend: config/config.py with pydantic-settings
- [x] (2026-02-27 09:25Z) Backend: FastAPI app + health + SSE endpoint + structlog
- [x] (2026-02-27 09:25Z) Backend: SQLAlchemy models + initial schema (5 tables)
- [x] (2026-02-27 09:30Z) Backend: Alembic migration generated and applied (head: 84de6aaf4acd)
- [x] (2026-02-27 09:30Z) Backend: NX project.json targets (serve, lint, type-check, test, migrate)
- [x] (2026-02-27 09:30Z) Backend: ruff config (line-length=120), all checks pass
- [x] (2026-02-27 09:35Z) Backend: TDD health test — red → green (2 tests pass)
- [x] (2026-02-27 09:40Z) Frontend: Next.js/TS scaffold + NX project.json
- [x] (2026-02-27 09:40Z) Validation: tests pass, ruff clean, tsc clean, build succeeds, migration at head
- [x] (2026-02-27 10:00Z) ExecPlan finalized: outcomes written, plan moved to completed/

## Surprises & Discoveries

_nothing yet_

## Decision Log

- Decision: Use `uv` as Python package manager instead of pip/poetry.
  Rationale: uv is significantly faster and handles virtual envs + lockfiles cleanly.
  Date/Author: 2026-02-27 / Josie

- Decision: SQLite (not PostgreSQL) for initial infra.
  Rationale: Zero-setup for local dev. Can be swapped later via SQLAlchemy URL config.
  Date/Author: 2026-02-27 / Josie

- Decision: SQLAlchemy 2.x async with aiosqlite driver.
  Rationale: Keeps all I/O non-blocking; consistent with FastAPI's async model.
  Date/Author: 2026-02-27 / Josie

- Decision: Alembic auto-runs on startup (`alembic upgrade head` before uvicorn).
  Rationale: Zero-friction dev experience — no manual migration step needed.
  Date/Author: 2026-02-27 / Josie

- Decision: Hexagonal architecture (services/ + adapters/) from the start.
  Rationale: backend.md mandates it. Keeps domain logic free of framework dependencies.
  Date/Author: 2026-02-27 / Josie

- Decision: Next.js instead of Vite/React.
  Rationale: AGENTS.md specifies Next.js. Better SSR support and file-based routing.
  Date/Author: 2026-02-27 / Josie

- Decision: NX monorepo managed via mise.
  Rationale: AGENTS.md mandates NX + mise. Enables nx affected for CI and consistent task running.
  Date/Author: 2026-02-27 / Josie

- Decision: structlog for all backend logging.
  Rationale: backend.md mandates structured JSON logging via structlog.
  Date/Author: 2026-02-27 / Josie

## Outcomes & Retrospective

All acceptance criteria met. The full monorepo skeleton is in place:
- FastAPI backend responds on port 8000, health endpoint returns `{"status":"ok","version":"0.1.0"}`, SSE heartbeat streams correctly.
- SQLite DB initialised with 5 tables via Alembic (auto-runs on startup).
- Next.js frontend builds cleanly, tsc passes, SSE dashboard stub works.
- NX targets wired for both projects, mise pins all tool versions.
- 2 TDD tests pass, ruff clean, tsc clean.
- Hexagonal skeleton (services/, adapters/) in place and ready for domain logic.

## Context and Orientation

The repository root is `theAgency/`. All Kotlin/Gradle artefacts have been removed. The
monorepo is managed by NX (task runner) and mise (toolchain version manager). The directory
structure to create is:

    theAgency/
    ├── backend/                    ← Python/FastAPI application (NX project)
    │   ├── pyproject.toml
    │   ├── project.json            ← NX targets: serve, lint, type-check, test, migrate
    │   ├── alembic.ini
    │   ├── alembic/
    │   │   └── versions/
    │   └── app/
    │       ├── main.py             ← FastAPI app entrypoint
    │       ├── config/
    │       │   └── config.py       ← pydantic-settings Config class
    │       ├── database.py         ← SQLAlchemy async engine + session factory
    │       ├── models.py           ← ORM table definitions
    │       ├── services/           ← Domain logic (Hexagonal core), no external deps
    │       ├── adapters/           ← External integrations (DB, OpenCode HTTP client, …)
    │       ├── routers/
    │       │   ├── health.py
    │       │   └── events.py
    │       └── tests/
    ├── frontend/                   ← Next.js/TypeScript application (NX project)
    │   ├── package.json
    │   ├── project.json
    │   ├── next.config.ts
    │   ├── tsconfig.json
    │   └── src/
    │       └── app/
    │           ├── layout.tsx
    │           └── page.tsx
    ├── nx.json                     ← NX workspace config
    ├── package.json                ← root package.json (NX, etc.)
    ├── .mise.toml                  ← tool versions (node, python, uv)
    ├── .env.example
    └── docs/

**NX** is a monorepo build system. `nx run backend:serve` starts the backend, `nx affected -t lint`
runs lint only on changed projects. Each project has a `project.json` that maps target names
to commands.

**mise** is a polyglot tool version manager (like asdf). `.mise.toml` pins Node, Python, and
uv versions so every developer gets the same environment.

**Hexagonal Architecture**: the `services/` directory contains pure Python domain logic with
no imports from FastAPI, SQLAlchemy, or any external library. `adapters/` contains everything
that talks to the outside world (database, OpenCode HTTP API, etc.). Routers are thin — they
parse HTTP, call a service, return the result.

FastAPI is a Python web framework with automatic OpenAPI doc generation and native async support.
uvicorn is its ASGI server. SQLAlchemy 2.x async with aiosqlite driver keeps all DB I/O
non-blocking. Alembic manages schema migrations. sse-starlette adds Server-Sent Events support.
structlog produces structured JSON log output. ruff is the linter (line-length=120).

Server-Sent Events (SSE) is a one-directional HTTP push protocol: the server keeps a GET
connection open and writes `data: <payload>\n\n` lines. The browser uses `EventSource` to
receive them. We use `sse-starlette` for the FastAPI integration.

## Plan of Work

**Step 1 — NX + mise root setup.** Create `package.json` and `nx.json` at the repo root to
initialise the NX workspace. Create `.mise.toml` pinning Node 22, Python 3.12, and uv.

**Step 2 — Backend scaffold.** Create `backend/pyproject.toml` using `uv init`, declare all
dependencies (fastapi, uvicorn, sqlalchemy, aiosqlite, alembic, sse-starlette, pydantic-settings,
structlog, ruff, pytest, pytest-asyncio, httpx, testcontainers). Configure ruff with
`line-length=120`. Create `backend/project.json` with NX targets: `serve`, `lint`, `type-check`,
`test`, `migrate`, `makemigration`.

**Step 3 — Config.** `backend/app/config/config.py` defines a `Settings` class using
pydantic-settings, reading `DATABASE_URL` (defaults to `sqlite+aiosqlite:///./data/agency.db`),
`APP_VERSION` (default `"0.1.0"`), and `CORS_ORIGINS` (default `["http://localhost:3000"]`).

**Step 4 — Database + models.** `backend/app/database.py` creates the async SQLAlchemy engine
and session factory from `Settings`. `backend/app/models.py` defines the five ORM table classes:
`Pipeline`, `Step`, `Handoff`, `AuditEvent`, `Approval` — all inheriting from a shared
`Base = DeclarativeBase()`.

**Step 5 — Alembic.** Run `uv run alembic init alembic` inside `backend/`, update
`alembic/env.py` to import the models' `Base.metadata` and read `DATABASE_URL` from Settings
(escaping `%` → `%%`). Generate the first migration with `--autogenerate`.

**Step 6 — FastAPI app.** `backend/app/main.py` creates the FastAPI instance with a lifespan
handler that runs `alembic upgrade head` on startup. Adds CORSMiddleware (origins from Settings),
registers the health and events routers. Configures structlog for JSON output.

**Step 7 — Routers.** `health.py` returns `{"status": "ok", "version": settings.app_version}`.
`events.py` uses `sse-starlette` to stream `{"type": "heartbeat", "ts": <unix-timestamp>}`
every 5 seconds.

**Step 8 — First TDD test.** Write a failing test in `backend/app/tests/test_health.py` that
calls `GET /health` via httpx AsyncClient and asserts HTTP 200 + body. Then make it pass.

**Step 9 — Frontend scaffold.** Run `npx create-next-app@latest frontend --typescript --tailwind
--app --src-dir --no-git` in the repo root. Create `frontend/project.json` with NX targets:
`dev`, `build`, `lint`, `type-check`. Minimal `page.tsx` showing "theAgency" heading and an SSE
connection logging heartbeats to console.

**Step 10 — mise + .env.example.** Write `.mise.toml` at repo root. Write `.env.example` with
all required variables commented.

## Concrete Steps

All commands are run from the repository root unless noted otherwise.

    # 1. NX workspace init
    npm init -y
    npm install --save-dev nx

    # 2. Backend init (run from repo root)
    mkdir -p backend/app/config backend/app/routers backend/app/services \
      backend/app/adapters backend/app/tests backend/alembic/versions backend/data
    cd backend && uv init --no-workspace
    uv add fastapi "uvicorn[standard]" sqlalchemy aiosqlite alembic \
      sse-starlette "pydantic-settings>=2.0" structlog
    uv add --dev ruff pytest pytest-asyncio httpx

    # 3. Alembic init (run inside backend/)
    uv run alembic init alembic

    # 4. Generate first migration (after models are written)
    uv run alembic revision --autogenerate -m "initial schema"

    # 5. Frontend scaffold (run from repo root)
    npx create-next-app@latest frontend --typescript --tailwind --app --src-dir --no-git
    cd frontend && npm install

    # 6. Smoke test backend
    cd backend && uv run uvicorn app.main:app --reload --port 8000
    curl http://localhost:8000/health
    # Expected: {"status":"ok","version":"0.1.0"}

    # 7. Run backend tests
    cd backend && uv run pytest app/tests/ -v
    # Expected: all tests pass

    # 8. Smoke test frontend
    cd frontend && npm run dev
    # Expected: Next.js dev server at http://localhost:3000

    # 9. NX tasks
    npx nx run backend:lint
    npx nx run backend:test
    npx nx run frontend:type-check

## Validation and Acceptance

The infrastructure is complete when all of the following hold simultaneously:

1. `curl http://localhost:8000/health` returns HTTP 200 with body `{"status":"ok","version":"0.1.0"}`.
2. `curl -N http://localhost:8000/events` streams `data:` lines without error.
3. `curl http://localhost:8000/docs` returns HTTP 200 (FastAPI auto-generated Swagger UI).
4. `cd frontend && npm run build` exits with code 0.
5. `cd frontend && npx tsc --noEmit` exits with code 0.
6. `cd backend && uv run alembic current` reports the initial migration as current head.
7. `backend/data/agency.db` exists and contains all five tables.
8. `cd backend && uv run pytest app/tests/ -v` — all tests pass including the TDD health test.
9. `npx nx run backend:lint` exits with code 0 (ruff, line-length=120).

## Idempotence and Recovery

Running `uv add` or `npm install` again is safe — they are idempotent. Alembic `upgrade head`
on an already-migrated database is a no-op. If the SQLite file gets corrupted, delete
`backend/data/agency.db` and restart the backend — it will recreate from scratch.

## Artifacts and Notes

_to be filled during implementation_

## Interfaces and Dependencies

Python dependencies (declared in `backend/pyproject.toml`):
- `fastapi>=0.115` — web framework
- `uvicorn[standard]>=0.30` — ASGI server
- `sqlalchemy>=2.0` — ORM (async mode)
- `aiosqlite>=0.20` — async SQLite driver
- `alembic>=1.13` — schema migrations
- `sse-starlette>=2.1` — Server-Sent Events helper
- `pydantic-settings>=2.0` — environment-variable config
- `structlog>=24.0` — structured JSON logging
- `ruff` (dev) — linter, line-length=120
- `pytest`, `pytest-asyncio`, `httpx` (dev) — testing

Frontend dependencies (via npm):
- `next`, `react`, `react-dom` — Next.js framework
- `typescript` — type safety
- `tailwindcss` — styling

SQLite tables to exist after migration:

    pipelines    (id, title, template, branch, status, created_at, updated_at)
    steps        (id, pipeline_id, agent_name, order_index, status, started_at, finished_at)
    handoffs     (id, step_id, content_md, metadata_json, created_at)
    audit_events (id, pipeline_id, step_id, event_type, payload_json, created_at)
    approvals    (id, step_id, status, comment, decided_by, decided_at)
