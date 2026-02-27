# Core: OpenCode HTTP Client Integration

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

theAgency needs to drive OpenCode agents programmatically — creating sessions, sending
prompts to specific agents, reading their responses, and streaming live status updates.
After this milestone, the backend has a fully-tested async HTTP adapter that wraps the
OpenCode REST API, and an adapter for managing OpenCode server processes (start/stop/health).

A developer can run `nx run backend:test` and see all tests pass. The adapters are pure
infrastructure components — they do not expose their own REST endpoints. The Pipeline Engine
(Issue #1) will consume them directly when it orchestrates agent steps.

## Progress

- [x] (2026-02-27 10:05Z) ExecPlan drafted
- [x] (2026-02-27 11:00Z) ExecPlan revised after review (dropped router milestone, added Pydantic models, fixed ProcessManager design, improved SSE handling)
- [x] (2026-02-27 12:00Z) Milestone 1: Pydantic response models + OpenCode HTTP adapter (TDD) — 16 tests, all green
- [x] (2026-02-27 12:30Z) Milestone 2: OpenCode server process manager (start/stop/health-check) — 8 tests, all green
- [x] (2026-02-27 13:00Z) Milestone 3: SSE event-stream consumer with reconnect logic — 3 tests, all green
- [x] (2026-02-27 13:30Z) Post-impl code-quality review: resolved all MUST FIX and SHOULD FIX findings
- [x] (2026-02-27 13:45Z) ExecPlan finalized: outcomes written, plan moved to completed/

## Surprises & Discoveries

- `respx.respond(json=True)` raises a type error — `respx` requires JSON to be a dict, list, or
  string. Bare boolean responses must use `text="true"` and are parsed correctly by `resp.json()`.
  Evidence: LSP error at test line 76 when first writing the delete/abort tests.

- `asyncio.create_subprocess_exec` requires all positional arguments to be `str`. Passing an `int`
  port compiles but raises `TypeError` at runtime on some platforms. The type checker (pyright)
  flags it; fixed by converting to `str(port)`. Evidence: LSP error in `opencode_process.py:39`.

- `asyncio.Event` is not safe to create at module import time or in `__init__` if the event loop
  hasn't started yet in some test configurations. In practice with `asyncio_mode = auto` (pytest-asyncio)
  it works fine because a loop is running by the time any async constructor is invoked.

- `is_running` doesn't need to be `async` — it only checks `process.returncode`, which is a
  synchronous attribute. Changed to a plain `def`, removing spurious `await` at all call sites.

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

- Decision: Drop Milestone 4 (Backend REST router that proxies OpenCode sessions).
  Rationale: A 1:1 passthrough router adds no value. The Pipeline Engine (Issue #1) will
  consume the adapter directly. REST endpoints come with the Pipeline Engine and expose
  pipeline operations, not raw OpenCode sessions.
  Date/Author: 2026-02-27 / Josie

- Decision: Return Pydantic models instead of raw dicts from adapter methods.
  Rationale: `docs/backend.md` mandates Pydantic models for request/response. Typed models
  catch typos at parse-time instead of runtime KeyErrors deep in business logic.
  Date/Author: 2026-02-27 / Josie

- Decision: Only `opencode_base_port` in Settings, not `opencode_base_url`.
  Rationale: The URL is always `http://127.0.0.1:<port>`. Having both a URL and a port
  setting creates ambiguity. The client constructs the URL from the port.
  Date/Author: 2026-02-27 / Josie

- Decision: `OpenCodeProcessManager.start()` returns an `OpenCodeClient`.
  Rationale: The client's `base_url` depends on the port, which is only known at start time.
  Passing a pre-built client in the constructor creates a chicken-and-egg problem.
  Date/Author: 2026-02-27 / Josie

- Decision: Use `respx` exclusively for HTTP mocking in tests. No `pytest-mock` for HTTP.
  Rationale: `respx` integrates directly with httpx's transport layer, produces cleaner
  assertions, and avoids mixing mock libraries for the same concern.
  Date/Author: 2026-02-27 / Josie

## Outcomes & Retrospective

All three milestones delivered as planned. The backend now has a fully-tested async HTTP adapter
for the OpenCode REST API (17 tests), an async process manager for OpenCode server subprocesses
(8 tests), and an SSE event-stream consumer with automatic reconnect logic (3 tests). All 27
tests pass; ruff lint is clean.

Notable improvements made during the post-implementation code-quality review:

- `_stop_event` replaced with `asyncio.Event` (proper async primitive, thread-safer)
- SSE frame parsing extracted to `_parse_sse_lines` async generator (single-responsibility)
- `port` argument to `create_subprocess_exec` converted to `str` (was a silent type bug)
- `is_running` made synchronous `def` (no I/O, was misleadingly `async`)
- `opencode_models.py` refactored with shared `_Base` class and `Literal` types for enums
- `body: dict` annotations tightened to `dict[str, Any]`
- Logging added to `OpenCodeProcessManager` start/stop state transitions
- Guard added to `start()` to prevent double-start resource leaks

The adapters are ready to be consumed by the Pipeline Engine (Issue #1).

## Context and Orientation

The repo root is `theAgency/`. The backend is a Python/FastAPI app in `backend/`. All Python
commands should be run inside `backend/` with `uv run`. The NX target `nx run backend:test`
runs `uv run pytest app/tests/ -v` from the backend directory.

**Hexagonal Architecture**: domain logic lives in `backend/app/services/`, external
integrations in `backend/app/adapters/`. Routers in `backend/app/routers/` are thin HTTP
wrappers. This milestone adds only adapter-layer code — no routers, no services. The
adapters are consumed later by the Pipeline Engine service.

Files created by this milestone:

- `backend/app/adapters/opencode_client.py` — async HTTP adapter for the OpenCode REST API
- `backend/app/adapters/opencode_process.py` — manages OpenCode server subprocesses
- `backend/app/adapters/opencode_models.py` — Pydantic response models for OpenCode API types
- `backend/app/tests/test_opencode_client.py` — TDD unit tests for the HTTP adapter
- `backend/app/tests/test_opencode_process.py` — TDD unit tests for process management

**OpenCode Server API** (runs at `http://127.0.0.1:<port>`):

The OpenCode server is started with `opencode serve --port <n>`. It exposes a REST API that
theAgency uses to create sessions, send prompts to agents, and stream events. The key
endpoints we consume are:

- `GET /global/health` → `{ healthy: true, version: "<string>" }` — server liveness check.
  Returns HTTP 200 when healthy. Any other response or connection error means unhealthy.
- `GET /global/event` — SSE (Server-Sent Events) stream. The first event has type
  `server.connected`. Subsequent events carry tool calls, message updates, status changes.
  The stream stays open indefinitely; the client reads lines as they arrive.
- `POST /session` — body: `{ parentID?: string, title?: string }`. Creates a new session.
  Returns a `Session` JSON object with at minimum `{ id: string, title: string }`.
- `GET /session` — returns an array of `Session` objects.
- `GET /session/:id` — returns a single `Session` object.
- `DELETE /session/:id` — returns `true` on success.
- `POST /session/:id/message` — body: `{ parts: [{ type: "text", text: "<prompt>" }],
  agent?: string, model?: string }`. Sends a prompt and **blocks** until the agent finishes.
  Returns `{ info: Message, parts: Part[] }` where `Message` has `{ id, sessionID, role }`
  and each `Part` represents a chunk of the response (text, tool call, etc.).
- `POST /session/:id/prompt_async` — same body as above but returns `204 No Content`
  immediately. The agent works in the background; monitor progress via SSE.
- `POST /session/:id/abort` — aborts a running agent. Returns `true`.
- `GET /session/:id/todo` — returns the agent's current todo list as `Todo[]`. Each todo has
  `{ content: string, status: string, priority: string }`.

**SSE protocol details**: SSE is a plain-text HTTP protocol. The server keeps a connection
open and writes lines in this format:

    event: <event-type>
    data: <json-payload>

    event: <event-type>
    data: <json-payload>

Events are separated by a blank line. The `data:` line contains JSON. The `event:` line is
optional — if omitted, the event type defaults to "message". OpenCode sends `event:` lines,
so we should parse both `event:` and `data:` fields. When the connection drops, the client
should reconnect after a configurable delay (default 1 second).

Important httpx detail for SSE: the default read timeout (5 seconds) will kill a long-lived
SSE connection. We must set `timeout=httpx.Timeout(connect=5.0, read=None, write=5.0,
pool=5.0)` on the streaming request so it stays open indefinitely.

**`httpx`** is an async HTTP client for Python. `httpx.AsyncClient` is used with `async with`
for connection pooling. The client must be explicitly closed when no longer needed — either
via `async with` or by calling `await client.aclose()`.

**`respx`** is a mocking library specifically for httpx. It intercepts requests at the
transport layer, so the full httpx request pipeline (headers, serialization, status codes)
still runs. Usage pattern:

    async with respx.MockRouter() as respx_mock:
        respx_mock.get("/global/health").respond(200, json={"healthy": True, "version": "1.0"})
        client = OpenCodeClient(base_url="http://test")
        result = await client.health_check()
        assert result is True

The `Settings` class in `backend/app/config/config.py` is a pydantic-settings object. It
reads environment variables from `.env`. We add `opencode_base_port: int = 4096` to it. The
`OpenCodeClient` builds its base URL as `http://127.0.0.1:{port}`.

## Plan of Work

**Milestone 1 — Pydantic models + HTTP adapter.** First create the response models in
`backend/app/adapters/opencode_models.py`, then build the `OpenCodeClient` adapter in
`backend/app/adapters/opencode_client.py` using TDD.

The response models define the shape of data returned by the OpenCode API. They use
`model_config = ConfigDict(extra="ignore")` so that extra fields from the API don't cause
validation errors — the OpenCode API may return fields we don't need yet.

Then create `OpenCodeClient`. The class accepts a `base_url: str` in its constructor and
creates an internal `httpx.AsyncClient`. It implements `__aenter__` and `__aexit__` so it
can be used as `async with OpenCodeClient(...) as client:`. When used without `async with`,
call `await client.close()` to release the connection pool.

All methods that talk to the OpenCode API parse the JSON response into the appropriate
Pydantic model before returning. If the HTTP response has a non-2xx status code, the method
raises `OpenCodeClientError` with the status code and a descriptive message.

Write unit tests in `backend/app/tests/test_opencode_client.py` using `respx` to mock HTTP
responses. TDD cycle: write one failing test, implement just enough to pass, refactor, repeat.

Test order (one at a time):
1. `test_health_check_returns_true_when_healthy` — mock 200, assert True
2. `test_health_check_returns_false_on_error` — mock connection error, assert False
3. `test_create_session` — mock 200 with session JSON, assert returns `SessionInfo`
4. `test_create_session_with_title` — verify title is sent in request body
5. `test_list_sessions` — mock 200 with array, assert returns `list[SessionInfo]`
6. `test_get_session` — mock 200, assert returns `SessionInfo`
7. `test_delete_session` — mock 200, assert returns True
8. `test_send_message` — mock 200, assert returns `MessageResponse`
9. `test_send_message_with_agent` — verify agent is sent in request body
10. `test_send_message_async` — mock 204, assert returns None (no error)
11. `test_abort_session` — mock 200, assert returns True
12. `test_get_todos` — mock 200, assert returns `list[TodoItem]`
13. `test_client_raises_on_http_error` — mock 500, assert `OpenCodeClientError` raised
14. `test_client_context_manager` — verify client closes cleanly

**Milestone 2 — Process manager.** Create `backend/app/adapters/opencode_process.py`. The
`OpenCodeProcessManager` class wraps `asyncio.create_subprocess_exec` to start
`opencode serve --port <n>` in a given working directory.

The constructor takes an optional `opencode_binary: str` parameter (defaults to `"opencode"`)
so the binary path is configurable. The `start(port, cwd)` method launches the subprocess,
then polls `GET /global/health` via a temporary `OpenCodeClient` until it responds (max 15 s,
0.5 s interval). If the health check never succeeds, it kills the process and raises
`OpenCodeStartupError`. On success, `start()` returns the `OpenCodeClient` instance — ready
to use, already connected and health-checked. The caller owns this client and is responsible
for closing it.

The `stop()` method sends SIGTERM to the subprocess, waits up to 5 seconds, then sends
SIGKILL if the process hasn't exited. The `is_running()` method checks both that the
subprocess is alive (`returncode is None`) and that the health endpoint responds.

Write tests in `backend/app/tests/test_opencode_process.py` using `unittest.mock.AsyncMock`
to patch `asyncio.create_subprocess_exec`. Mock the `OpenCodeClient.health_check` method to
simulate startup sequences (first N calls fail, then succeed).

Test order:
1. `test_start_launches_subprocess` — verify create_subprocess_exec called with correct args
2. `test_start_polls_health_until_ready` — mock health_check to fail 3x then succeed
3. `test_start_raises_on_timeout` — mock health_check to always fail, assert error
4. `test_start_returns_client` — verify returned object is an OpenCodeClient
5. `test_stop_sends_sigterm` — verify terminate() called on process
6. `test_stop_sends_sigkill_after_timeout` — mock process that doesn't exit, verify kill()
7. `test_is_running_true` — mock alive process + healthy endpoint
8. `test_is_running_false_when_process_dead` — mock process with returncode set

**Milestone 3 — SSE event-stream consumer.** Add `stream_events` to `OpenCodeClient`. This
method performs a streaming GET to `/global/event` using `httpx`'s `client.stream()` context
manager with `timeout=httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0)` so the
long-lived connection is not killed by read timeouts.

The method reads lines from the response stream. It maintains a small state machine to parse
SSE frames: when it sees a line starting with `event:`, it stores the event type. When it
sees a line starting with `data:`, it parses the JSON payload. On a blank line (frame
boundary), it calls `await callback(event)` with a dict containing `{"event": <type>,
"data": <parsed-json>}`, then resets state for the next frame.

The method runs in a loop. If the connection drops (httpx raises `ReadError`, `RemoteProtocolError`,
or any `httpx.HTTPError`), it waits `reconnect_delay` seconds (default 1.0) and reconnects.
The loop continues until `stop_streaming()` is called, which sets an internal `asyncio.Event`
that the loop checks between reconnect attempts.

Lines that don't start with `event:` or `data:` (like comments starting with `:`) are
silently ignored per the SSE spec.

Write tests in the same `test_opencode_client.py` file:
1. `test_stream_events_calls_callback` — mock a streamed response with two SSE frames,
   verify callback called twice with correct payloads
2. `test_stream_events_reconnects_on_disconnect` — mock a response that errors, then a
   second response that works. Verify callback eventually called.
3. `test_stream_events_stops_on_signal` — call `stop_streaming()` and verify the method exits

## Concrete Steps

Run all commands from `backend/` unless stated otherwise.

    # Dependencies (already done, listed for completeness)
    uv add httpx
    uv add --dev respx

    # Run tests at any point
    uv run pytest app/tests/ -v

    # Or via NX (from repo root)
    npx nx run backend:test

    # Lint check
    uv run ruff check app/

    # Or via NX
    npx nx run backend:lint

## Validation and Acceptance

Run `npx nx run backend:test` from the repo root and expect all tests to pass. Specifically:

1. `test_opencode_client.py` — 14 tests for the HTTP adapter (health, session CRUD, message,
   async message, abort, todos, error handling, context manager) plus 3 SSE tests = 17 total.
2. `test_opencode_process.py` — 8 tests for the process manager (start, health polling,
   timeout, stop, sigkill, is_running).
3. `test_health.py` — 2 pre-existing tests still pass.
4. `npx nx run backend:lint` exits clean (ruff, line-length=120).

Total expected: 27 tests, all green.

## Idempotence and Recovery

`uv add` and `uv add --dev` are safe to run multiple times. Tests are idempotent — no
persistent state (all HTTP calls mocked, no subprocess actually launched). If a test leaves
state, re-running `pytest` will reset it.

## Artifacts and Notes

_to be filled during implementation_

## Interfaces and Dependencies

New Python deps (production): `httpx>=0.27` (already added)
New Python deps (dev): `respx>=0.21` (already added)

New setting in `backend/app/config/config.py`:

    opencode_base_port: int = 4096

Pydantic models in `backend/app/adapters/opencode_models.py`:

    from pydantic import BaseModel, ConfigDict

    class SessionInfo(BaseModel):
        model_config = ConfigDict(extra="ignore")
        id: str
        title: str | None = None

    class MessageInfo(BaseModel):
        model_config = ConfigDict(extra="ignore")
        id: str
        sessionID: str
        role: str

    class Part(BaseModel):
        model_config = ConfigDict(extra="ignore")
        type: str
        content: str = ""

    class MessageResponse(BaseModel):
        model_config = ConfigDict(extra="ignore")
        info: MessageInfo
        parts: list[Part]

    class TodoItem(BaseModel):
        model_config = ConfigDict(extra="ignore")
        content: str
        status: str
        priority: str = ""

Key types in `backend/app/adapters/opencode_client.py`:

    class OpenCodeClientError(Exception):
        def __init__(self, message: str, status_code: int | None = None): ...

    class OpenCodeClient:
        def __init__(self, base_url: str): ...
        async def __aenter__(self) -> "OpenCodeClient": ...
        async def __aexit__(self, *exc) -> None: ...
        async def close(self) -> None: ...
        async def health_check(self) -> bool: ...
        async def create_session(self, title: str | None = None) -> SessionInfo: ...
        async def list_sessions(self) -> list[SessionInfo]: ...
        async def get_session(self, session_id: str) -> SessionInfo: ...
        async def delete_session(self, session_id: str) -> bool: ...
        async def send_message(
            self,
            session_id: str,
            prompt: str,
            agent: str | None = None,
            model: str | None = None,
        ) -> MessageResponse: ...
        async def send_message_async(
            self, session_id: str, prompt: str, agent: str | None = None
        ) -> None: ...
        async def abort_session(self, session_id: str) -> bool: ...
        async def get_todos(self, session_id: str) -> list[TodoItem]: ...
        async def stream_events(
            self,
            callback: Callable[[dict], Awaitable[None]],
            reconnect_delay: float = 1.0,
        ) -> None: ...
        def stop_streaming(self) -> None: ...

Key types in `backend/app/adapters/opencode_process.py`:

    class OpenCodeStartupError(Exception): ...

    class OpenCodeProcessManager:
        def __init__(self, opencode_binary: str = "opencode"): ...
        async def start(self, port: int, cwd: str) -> OpenCodeClient: ...
        async def stop(self) -> None: ...
        async def is_running(self) -> bool: ...
        @property
        def port(self) -> int | None: ...
