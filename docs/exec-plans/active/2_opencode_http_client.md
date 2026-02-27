# Core: OpenCode HTTP Client Integration

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

theAgency needs to drive OpenCode agents programmatically — creating sessions, sending
prompts to specific agents, reading their responses, and streaming live status updates.
After this milestone, the backend has a fully-tested async HTTP adapter that wraps the
OpenCode REST API, an adapter for managing OpenCode server processes (start/stop/health),
and a backend REST endpoint that exposes session creation and agent messaging to other
parts of the system.

A developer can run `nx run backend:test` and see all tests pass. They can also start a
local OpenCode server with `opencode serve --port 4096` and manually hit
`POST /opencode/session` on the theAgency backend to create a session through it.

## Progress

- [x] (2026-02-27 10:05Z) ExecPlan drafted
- [ ] Milestone 1: OpenCode HTTP adapter — session + message management (TDD, unit tests with mocked HTTP)
- [ ] Milestone 2: OpenCode server process manager (start/stop/health-check)
- [ ] Milestone 3: SSE event-stream consumer (live updates from OpenCode event bus)
- [ ] Milestone 4: Backend REST endpoints wrapping the adapter (`/opencode/session`, `/opencode/session/:id/message`)
- [ ] ExecPlan finalized: outcomes written, plan moved to completed/

## Surprises & Discoveries

_nothing yet_

## Decision Log

- Decision: Use `httpx` (already in dev deps) rather than `aiohttp` for the HTTP client.
  Rationale: httpx supports both async and sync, has a cleaner API, and is already a test
  dependency. No extra dep needed.
  Date/Author: 2026-02-27 / Josie

- Decision: Move `httpx` from dev to production dependencies.
  Rationale: The adapter runs in production code, not only in tests.
  Date/Author: 2026-02-27 / Josie

- Decision: Port management — each OpenCode server instance gets a port from a configurable
  base port (default 4096) plus an offset per instance index.
  Rationale: Matches the OpenCode default and Issue #2 spec.
  Date/Author: 2026-02-27 / Josie

- Decision: SSE consumer uses `httpx` streaming requests (iter_lines) rather than a
  websocket or a separate SSE library.
  Rationale: OpenCode SSE is plain HTTP chunked text; httpx handles it natively. No extra dep.
  Date/Author: 2026-02-27 / Josie

## Outcomes & Retrospective

_to be filled after completion_

## Context and Orientation

The repo root is `theAgency/`. The backend is a Python/FastAPI app in `backend/`. All Python
commands should be run inside `backend/` with `uv run`. The NX target `nx run backend:test`
runs `uv run pytest` from the backend directory.

**Hexagonal Architecture**: domain logic lives in `backend/app/services/`, external
integrations in `backend/app/adapters/`. Routers in `backend/app/routers/` are thin HTTP
wrappers. This milestone adds:

- `backend/app/adapters/opencode_client.py` — async HTTP adapter for the OpenCode REST API
- `backend/app/adapters/opencode_process.py` — manages OpenCode server subprocesses
- `backend/app/routers/opencode.py` — thin FastAPI router exposing `/opencode/*` endpoints
- `backend/app/tests/test_opencode_client.py` — TDD unit tests for the HTTP adapter
- `backend/app/tests/test_opencode_process.py` — TDD unit tests for process management

**OpenCode Server API** (runs at `http://127.0.0.1:<port>`):

- `GET /global/health` → `{ healthy: true, version: string }` — server liveness check
- `GET /global/event` — SSE stream of all server events
- `POST /session` → `{ parentID?, title? }` — create a new session; returns `Session` object
- `GET /session` → `Session[]` — list sessions
- `GET /session/:id` → `Session` — get a session
- `DELETE /session/:id` → `boolean` — delete a session
- `POST /session/:id/message` → `{ messageID?, model?, agent?, noReply?, parts }` — send a
  message to an agent and wait for the full response; returns `{ info: Message, parts: Part[] }`
- `POST /session/:id/prompt_async` — same body as above but returns immediately (204)
- `POST /session/:id/abort` → `boolean` — abort a running message
- `GET /session/:id/todo` → `Todo[]` — get the agent's todo list

A `Session` has at minimum `{ id: string, title: string }`. A `Message` has `{ id: string,
sessionID: string, role: string }`. A `Part` represents a chunk of the message content.

**OpenCode server process**: `opencode serve --port <n>` starts the server. The process
listens on port `n` within a second or two. A health-check loop polls `GET /global/health`
until it succeeds or a timeout is exceeded.

**`httpx`** is an async HTTP client for Python. `httpx.AsyncClient` is used with `async with`
for connection pooling. `client.stream("GET", url)` yields chunks for SSE consumption.

**SSE (Server-Sent Events)** is a plain-text HTTP protocol where the server keeps a
connection open and emits lines like `data: <json>\n\n`. The client reads these lines as
they arrive. We parse each `data:` line as JSON to get the event payload.

The `Settings` class in `backend/app/config/config.py` is a pydantic-settings object. It
reads environment variables from `.env`. We add `opencode_base_port: int = 4096` to it so
the port is configurable without code changes.

## Plan of Work

**Milestone 1 — HTTP adapter (session + message).** Create
`backend/app/adapters/opencode_client.py`. The public interface is an `OpenCodeClient`
class that accepts a `base_url: str` and an optional `httpx.AsyncClient` (for injection in
tests). Methods needed:

- `async def health_check() -> bool` — GET /global/health, returns True if healthy
- `async def create_session(title: str | None = None) -> dict` — POST /session
- `async def list_sessions() -> list[dict]` — GET /session
- `async def get_session(session_id: str) -> dict` — GET /session/:id
- `async def delete_session(session_id: str) -> bool` — DELETE /session/:id
- `async def send_message(session_id: str, prompt: str, agent: str | None = None, model: str | None = None) -> dict`
  — POST /session/:id/message with `parts: [{ type: "text", text: prompt }]`
- `async def send_message_async(session_id: str, prompt: str, agent: str | None = None) -> None`
  — POST /session/:id/prompt_async (fire and forget, returns immediately)
- `async def abort_session(session_id: str) -> bool` — POST /session/:id/abort
- `async def get_todos(session_id: str) -> list[dict]` — GET /session/:id/todo

All methods raise `OpenCodeClientError(message, status_code)` on HTTP errors. Define this
exception class in the same file.

Write unit tests in `backend/app/tests/test_opencode_client.py` using `pytest-mock` (already
available via `uv`) and `httpx.MockTransport` / `respx` to mock HTTP responses. Use
`respx` — a dedicated httpx mocking library — instead of generic mocks, as it integrates
cleanly with httpx's transport layer.

Add `respx` to dev dependencies: `uv add --dev respx`.

TDD order: write the failing test first, then implement just enough to make it pass, then
refactor.

**Milestone 2 — Process manager.** Create `backend/app/adapters/opencode_process.py`. The
`OpenCodeProcessManager` class wraps `asyncio.create_subprocess_exec` to start
`opencode serve --port <n>` in a given working directory. Methods:

- `async def start(port: int, cwd: str) -> None` — launch process, poll health until ready
  (max 15 s, 0.5 s interval), raise `OpenCodeStartupError` on timeout
- `async def stop() -> None` — send SIGTERM, wait up to 5 s, then SIGKILL
- `async def is_running() -> bool` — check process exists and health endpoint responds
- `property port: int` — the port this instance is listening on

The process manager holds a reference to the `asyncio.subprocess.Process` object and the
`OpenCodeClient` it uses for health checks. It should not import FastAPI or SQLAlchemy.

Write tests in `backend/app/tests/test_opencode_process.py` using `unittest.mock.AsyncMock`
and `pytest-mock` to patch `asyncio.create_subprocess_exec` and the `OpenCodeClient`.

**Milestone 3 — SSE consumer.** Add an `async def stream_events(callback)` method to
`OpenCodeClient`. It performs a streaming GET to `/global/event`, reads lines, and calls
`callback(event: dict)` for each `data:` line that parses as valid JSON. It loops until the
connection drops, then re-connects after a 1-second delay (retry logic). A `stop()` method
sets a flag to break the loop.

Write a test that verifies the callback is called for each data line in a mocked chunked
response.

**Milestone 4 — Backend router.** Create `backend/app/routers/opencode.py` with the prefix
`/opencode`. Register it in `backend/app/main.py`. Endpoints:

- `POST /opencode/session` — body `{ title?: string }`, creates a session via
  `OpenCodeClient`, returns the session dict
- `GET /opencode/session` — list sessions
- `GET /opencode/session/{session_id}` — get one session
- `DELETE /opencode/session/{session_id}` — delete
- `POST /opencode/session/{session_id}/message` — body `{ prompt: string, agent?: string,
  model?: string }`, calls `send_message`, returns the response dict

The router uses a shared `OpenCodeClient` instance created from `settings.opencode_base_url`
(a new setting: `opencode_base_url: str = "http://127.0.0.1:4096"`). Write integration
tests in `backend/app/tests/test_opencode_router.py` using `respx` to mock the upstream
OpenCode server.

## Concrete Steps

Run all commands from `backend/` unless stated otherwise.

    # Add respx to dev deps
    cd backend
    uv add --dev respx
    uv add httpx   # promote from dev to production dep

    # Run tests at any point (from repo root)
    nx run backend:test
    # or directly:
    cd backend && uv run pytest app/tests/ -v

    # Lint check
    nx run backend:lint

    # Type check
    nx run backend:type-check

## Validation and Acceptance

Run `nx run backend:test` and expect all tests to pass (green). Specifically:

1. `test_opencode_client.py` — health_check, session CRUD, send_message, send_message_async,
   abort, get_todos all covered with mocked HTTP responses.
2. `test_opencode_process.py` — start/stop/is_running covered with mocked subprocess.
3. SSE stream test — callback called for each mocked data line.
4. `test_opencode_router.py` — all 5 router endpoints return expected status codes and bodies
   with mocked upstream.
5. `nx run backend:lint` exits clean.
6. `nx run backend:type-check` exits clean (mypy or pyright — use ruff for now as type-check
   target uses `uv run python -m py_compile` per existing project.json).

## Idempotence and Recovery

`uv add` and `uv add --dev` are safe to run multiple times. Tests are idempotent — no
persistent state (all HTTP calls mocked). If a test leaves state, re-running `pytest` will
reset it.

## Artifacts and Notes

_to be filled during implementation_

## Interfaces and Dependencies

New Python deps (production): `httpx>=0.27`
New Python deps (dev): `respx>=0.21`

Key types exposed by `backend/app/adapters/opencode_client.py`:

    class OpenCodeClientError(Exception):
        def __init__(self, message: str, status_code: int | None = None): ...

    class OpenCodeClient:
        def __init__(self, base_url: str, http_client: httpx.AsyncClient | None = None): ...
        async def health_check(self) -> bool: ...
        async def create_session(self, title: str | None = None) -> dict: ...
        async def list_sessions(self) -> list[dict]: ...
        async def get_session(self, session_id: str) -> dict: ...
        async def delete_session(self, session_id: str) -> bool: ...
        async def send_message(
            self,
            session_id: str,
            prompt: str,
            agent: str | None = None,
            model: str | None = None,
        ) -> dict: ...
        async def send_message_async(
            self, session_id: str, prompt: str, agent: str | None = None
        ) -> None: ...
        async def abort_session(self, session_id: str) -> bool: ...
        async def get_todos(self, session_id: str) -> list[dict]: ...
        async def stream_events(self, callback: Callable[[dict], Awaitable[None]]) -> None: ...
        def stop_streaming(self) -> None: ...

Key types exposed by `backend/app/adapters/opencode_process.py`:

    class OpenCodeStartupError(Exception): ...

    class OpenCodeProcessManager:
        def __init__(self, client: OpenCodeClient): ...
        async def start(self, port: int, cwd: str) -> None: ...
        async def stop(self) -> None: ...
        async def is_running(self) -> bool: ...
        @property
        def port(self) -> int: ...
