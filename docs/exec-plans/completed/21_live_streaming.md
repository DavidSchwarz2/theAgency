# Stream live OpenCode events to the browser

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries,
Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

## Purpose / Big Picture

After this change, a user watching the theAgency dashboard will see a live scrolling feed
of everything the OpenCode agent is doing while a pipeline step runs — every tool call,
message, and status update — as it happens, without refreshing the page. Today the UI is
silent during a running step; handoff output only appears after the step finishes. This
feature removes that dead-air period entirely.

The user experience is: a running step in the pipeline card expands to show a "Live
output" panel. Lines stream in as OpenCode emits them. When the step finishes, the live
panel is replaced by the completed handoff output (or disappears if there's nothing to
show yet). Multiple browser tabs simultaneously connected each receive the full event
stream.

## Progress

- [x] (2026-02-27Z) ExecPlan written, GitHub issue #21 created
- [x] (2026-02-27Z) Milestone 1: `SseBroker` implemented in `backend/app/services/sse_broker.py`
- [x] (2026-02-27Z) Milestone 1: `GET /events` upgraded to fan out OpenCode frames via broker
- [x] (2026-02-27Z) Milestone 1: Broker wired into FastAPI lifespan (startup/shutdown) in `main.py`
- [x] (2026-02-27Z) Milestone 1: 6 new tests pass (219 total), 0 failures
- [x] (2026-02-27Z) Milestone 2: `useOpenCodeStream` hook created in `frontend/src/hooks/useOpenCodeStream.ts`
- [x] (2026-02-27Z) Milestone 2: `LiveOutputPanel` component added to `PipelineCard.tsx`
- [x] (2026-02-27Z) Milestone 2: `StepRow` updated to receive and display `liveLines`
- [x] (2026-02-27Z) Milestone 2: Frontend type-check clean (0 errors)
- [x] (2026-02-27Z) Post-implementation review: code-quality fixes applied — `_STOP` sentinel moved to `SseBroker.STOP` public class attr, `event_stream()` method added, `events.py` refactored with named `_heartbeat_stream`, typed `get_sse_broker` dependency, test determinism improved (sleep→queue.get, monkeypatch for interval), `useOpenCodeStream` `esRef` removed, `onerror` surfaces CLOSED state, `PipelineCard` prop type uses `Pipeline | PipelineDetail`, `StepRow` auto-expands via `useEffect`, `LiveOutputPanel` uses stable key
- [x] (2026-02-27Z) 219 backend tests pass, frontend type-check clean, no new lint errors
- [x] (2026-02-27Z) ExecPlan moved to completed/, GH issue #21 closed

## Surprises & Discoveries

- Discovery: `httpx.ASGITransport` buffers the full response body before exposing it to
  the test client, so SSE endpoint tests cannot use `aiter_lines()` to stream frames
  incrementally. Solution: test the generator logic directly at the queue level rather
  than via HTTP. The broker and router integration is covered at the unit level; the
  HTTP path is covered by the existing FastAPI + sse_starlette infrastructure which is
  already tested in other projects.
  Evidence: tests using `aiter_lines()` + `asyncio.wait_for` timed out (60s) with 0
  frames collected.

- Discovery: `contextlib.suppress` cannot be used with a log statement inside the
  suppressed block (it has no else clause). Used guard `if q.full()` instead for the
  drop-with-warning pattern in `_on_event`.

## Decision Log

- Decision: Fan-out via per-client asyncio.Queue in a shared broker object stored on
  app.state, with a single background asyncio.Task that reads from OpenCode's
  /global/event SSE stream.
  Rationale: Avoids opening one HTTP connection to OpenCode per browser client. The
  broker holds the single upstream connection and fans events to N subscriber queues.
  A sentinel value (None) is enqueued when the broker shuts down so all client generators
  exit cleanly.
  Date/Author: 2026-02-27 / agent

- Decision: Keep the /events endpoint path unchanged.
  Rationale: The frontend can simply connect to /api/events as before; the contract
  change is additive (more events, not a different endpoint).
  Date/Author: 2026-02-27 / agent

- Decision: Do NOT filter events on the backend by session_id; send all OpenCode events
  to all connected clients and let the frontend filter if needed.
  Rationale: Simplicity. The volume of events from one active OpenCode session is tiny.
  Per-session filtering would require the backend to know which pipeline is active and
  adds coupling between the events router and the pipeline runner.
  Date/Author: 2026-02-27 / agent

- Decision: The live panel renders each event's raw JSON as a single line of
  monospace text. No pretty-printing or markdown. Keeps the implementation trivial and
  the output honest.
  Rationale: The primary value is visibility, not beauty. Pretty-printing specific event
  shapes can be a follow-up.
  Date/Author: 2026-02-27 / agent

## Outcomes & Retrospective

_To be filled in after completion._

## Context and Orientation

### How OpenCode events work

OpenCode is a separate process that runs AI agent sessions. It exposes an HTTP API at
`http://localhost:4096` (configurable via `OPENCODE_BASE_URL` in `backend/.env`). One of
its endpoints is `GET /global/event`, which is a Server-Sent Events (SSE) stream. SSE is
a standard HTTP protocol where the server pushes a stream of text frames to the client.
Each frame has an optional `event:` line, a `data:` line, and a blank terminator line.
The OpenCode stream emits one frame per agent action — tool calls, text messages, step
completions, etc.

`backend/app/adapters/opencode_client.py` already has `stream_events(callback,
reconnect_delay)` which opens this stream and calls `callback({"event": str, "data":
any})` for every frame. It also auto-reconnects on network errors and exits when
`stop_streaming()` is called.

### Current /events endpoint (stub)

`backend/app/routers/events.py` has a `GET /events` endpoint that returns an
`EventSourceResponse` (from the `sse_starlette` library). Right now it only emits a
JSON heartbeat every 5 seconds:

    {"type": "heartbeat", "ts": <unix-timestamp>}

This heartbeat approach will be preserved (clients need it to detect connection drops)
but the router will also forward every frame from the OpenCode global event stream.

### Fan-out broker concept

A "broker" is a small object that maintains one upstream connection to OpenCode's
`/global/event` and fans every event out to every currently-connected browser client.
Each browser connection registers an `asyncio.Queue` with the broker; the broker's
background task puts events onto all registered queues; each client's SSE generator
reads from its own queue and yields frames.

The broker is created during FastAPI application startup (in `lifespan` in
`backend/app/main.py`) and stored on `app.state.sse_broker`. The background task is
tracked in `app.state` as well so it can be cancelled at shutdown.

### Repository layout relevant to this feature

    backend/
      app/
        main.py                  — lifespan (startup/shutdown), app.state setup
        adapters/
          opencode_client.py     — stream_events(), stop_streaming(), _parse_sse_lines()
        routers/
          events.py              — GET /events stub to be replaced
        services/
          sse_broker.py          — NEW: SseBroker class (fan-out logic)
    frontend/
      src/
        hooks/
          useOpenCodeStream.ts   — NEW: EventSource hook
        components/
          PipelineCard.tsx       — StepRow to get a live-output panel

## Plan of Work

### Milestone 1 — Backend SSE broker

**Goal**: `GET /events` forwards all OpenCode frames to every connected browser client,
plus heartbeats. Tests prove fan-out works without a real OpenCode server.

**Step 1.1 — Create `backend/app/services/sse_broker.py`**

Define class `SseBroker`. It holds a `set` of `asyncio.Queue` instances (one per
connected client) and a reference to the `OpenCodeClient`. A sentinel constant
`_STOP = object()` is used to signal queues to drain and exit.

Public interface:

    class SseBroker:
        def __init__(self, client: OpenCodeClient) -> None: ...
        async def start(self) -> None:
            """Start the background task that reads from OpenCode SSE."""
        async def stop(self) -> None:
            """Cancel the background task and drain all subscriber queues."""
        def subscribe(self) -> asyncio.Queue:
            """Register a new subscriber; returns a fresh Queue."""
        def unsubscribe(self, q: asyncio.Queue) -> None:
            """Remove the subscriber queue."""

Internally, `start()` creates `asyncio.create_task(_run())` where `_run()` calls
`self._client.stream_events(self._on_event, reconnect_delay=1.0)`. The callback
`_on_event(frame)` puts `json.dumps(frame)` onto every registered queue. If OpenCode is
unavailable, `stream_events` will retry with reconnect_delay; this is fine — the broker
just won't emit events until OpenCode comes back.

`stop()` sets the stop event on the OpenCodeClient (`self._client.stop_streaming()`),
cancels the background task (suppress `CancelledError`), then puts `_STOP` onto every
registered queue so SSE generators exit cleanly.

`subscribe()` creates a new `asyncio.Queue(maxsize=512)` — maxsize prevents runaway
memory if a slow browser client backs up — registers it, and returns it.
`unsubscribe()` discards the queue from the set and is always called from a `finally`
block in the SSE generator.

**Step 1.2 — Wire broker into `backend/app/main.py` lifespan**

After `opencode_client` is created, instantiate the broker and start it:

    broker = SseBroker(client=opencode_client)
    app.state.sse_broker = broker
    sse_task = asyncio.create_task(broker.start())
    app.state.sse_task = sse_task

During shutdown (after cancelling pipeline tasks), call:

    await broker.stop()
    sse_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await sse_task

Note: `broker.stop()` already calls `client.stop_streaming()`, which causes
`stream_events()` to exit its loop, which causes `_run()` to return naturally. The
explicit `sse_task.cancel()` is a belt-and-suspenders safety measure.

**Step 1.3 — Replace `backend/app/routers/events.py`**

The new implementation:

1. Retrieves `request.app.state.sse_broker`.
2. Calls `broker.subscribe()` to get a queue.
3. Defines an async generator `_event_generator()` that:
   - Yields heartbeats every 5 seconds (using `asyncio.wait_for` on the queue with a
     5-second timeout — a TimeoutError means no event arrived, so emit a heartbeat).
   - When an event arrives from the queue, yields it as an SSE data frame.
   - When it receives `_STOP` (the sentinel), breaks the loop and returns.
   - Calls `broker.unsubscribe(q)` in a `finally` block.
4. Returns `EventSourceResponse(_event_generator())`.

The heartbeat/event multiplexing pattern using `asyncio.wait_for`:

    HEARTBEAT_INTERVAL = 5.0
    async def _event_generator():
        q = broker.subscribe()
        try:
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=HEARTBEAT_INTERVAL)
                    if item is _STOP:
                        break
                    yield {"data": item}
                except asyncio.TimeoutError:
                    yield {"data": json.dumps({"type": "heartbeat", "ts": int(time.time())})}
        finally:
            broker.unsubscribe(q)

**Step 1.4 — Write tests**

File: `backend/app/tests/test_events_router.py`

Tests to write (TDD — write test, then implement, then verify):

Test 1 — `test_heartbeat_emitted_when_no_opencode_events`: Create a broker with a mock
client whose `stream_events` never calls the callback. Connect to `GET /events`, read
a few bytes, verify a heartbeat JSON frame arrives within 10 seconds.

Test 2 — `test_opencode_event_forwarded`: Create a broker with a mock client that calls
the callback once with a sample frame `{"event": "message", "data": {"text": "hello"}}`.
Connect to `GET /events`, read the next non-heartbeat frame, verify the JSON matches the
sample.

Test 3 — `test_multiple_subscribers_receive_same_event`: Subscribe two queues to the
same broker, put one event onto the broker manually (bypassing `stream_events`), verify
both queues receive it.

Test 4 — `test_unsubscribe_on_disconnect`: Verify that after `unsubscribe()` is called,
the set of subscribers shrinks by one and no further events are delivered to that queue.

Use `AsyncMock` for the `OpenCodeClient` mock (specifically `stream_events` which is an
async method). Use `respx` only if making real HTTP calls; these tests mock the client
directly so `respx` is not needed.

The FastAPI `TestClient` (synchronous) won't work well for SSE because SSE generators
are never-ending. Use `httpx.AsyncClient` with `app` directly via `ASGITransport` and
stream the response to collect the first few frames. Example pattern:

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with client.stream("GET", "/events") as resp:
            # read first 2 frames
            ...

For the broker-unit tests (Tests 3–4), instantiate `SseBroker` directly without
starting it — test subscribe/unsubscribe logic in isolation.

### Milestone 2 — Frontend live output panel

**Goal**: While a step's status is `running`, the pipeline card shows a live-updating
"Live output" panel below the step row. Lines stream in via `EventSource`. When the step
finishes or the pipeline is no longer running, the live panel disappears and the handoff
toggle is available as usual.

**Step 2.1 — Add `useOpenCodeStream` hook**

File: `frontend/src/hooks/useOpenCodeStream.ts`

The hook opens an `EventSource` connection to `/api/events` while the pipeline has at
least one running step, and accumulates the last N lines (cap at 200) in local state.

    export function useOpenCodeStream(active: boolean): string[] {
        // Returns an array of raw JSON strings (one per event), capped at 200 entries.
        // Opens EventSource only when active=true; closes it when active=false.
    }

Implementation sketch:

    import { useEffect, useRef, useState } from 'react'

    const MAX_LINES = 200

    export function useOpenCodeStream(active: boolean): string[] {
      const [lines, setLines] = useState<string[]>([])
      const esRef = useRef<EventSource | null>(null)

      useEffect(() => {
        if (!active) {
          esRef.current?.close()
          esRef.current = null
          setLines([])
          return
        }

        const es = new EventSource('/api/events')
        esRef.current = es

        es.onmessage = (e) => {
          // skip heartbeats
          try {
            const parsed = JSON.parse(e.data)
            if (parsed?.type === 'heartbeat') return
          } catch { /* not JSON — still show it */ }
          setLines((prev) => {
            const next = [...prev, e.data]
            return next.length > MAX_LINES ? next.slice(-MAX_LINES) : next
          })
        }

        es.onerror = () => {
          // EventSource auto-reconnects; no action needed
        }

        return () => {
          es.close()
          esRef.current = null
        }
      }, [active])

      return lines
    }

**Step 2.2 — Add `LiveOutputPanel` component and wire into `StepRow`**

Modify `frontend/src/components/PipelineCard.tsx`:

Add a `LiveOutputPanel` sub-component that receives `lines: string[]` and renders them
as a scrollable monospace box. Auto-scrolls to the bottom when new lines arrive using
a `useEffect` + `ref` on the container div.

    function LiveOutputPanel({ lines }: { lines: string[] }) {
      const bottomRef = useRef<HTMLDivElement>(null)
      useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, [lines])
      return (
        <div className="mt-1 ml-2 border-l-2 border-blue-800 pl-3 max-h-48 overflow-y-auto font-mono text-xs text-gray-400">
          {lines.map((line, i) => (
            <div key={i}>{line}</div>
          ))}
          <div ref={bottomRef} />
        </div>
      )
    }

The `StepRow` component currently takes a single `step` prop. The live stream is
pipeline-wide (not per-step), so the stream state must be lifted to the parent
`PipelineCard` and passed down. To minimise prop drilling, the cleanest approach is:

In `PipelineCard`, compute `const hasRunningStep = sortedSteps.some(s => s.status === 'running')`,
call `useOpenCodeStream(hasRunningStep)` to get `liveLines`, and pass `liveLines` to the
running `StepRow`.

Change `StepRow` signature to:

    function StepRow({ step, liveLines }: { step: Step; liveLines?: string[] })

When `step.status === 'running'` and `liveLines` is non-empty, show `<LiveOutputPanel
lines={liveLines} />` below the step row header. When a handoff is available (after
`step.status` changes to `done`), the normal handoff toggle shows instead.

**Step 2.3 — Run `tsc --noEmit` to confirm types are valid**

    npx nx run frontend:type-check

## Concrete Steps

All commands run from the repository root `/Users/vwqd2w2/code/iandi/theAgency` unless
stated otherwise.

**Milestone 1 steps:**

1. Write the failing test for `SseBroker` (subscriber fan-out unit test):
       npx nx run backend:test -- -k test_sse_broker
   Expect: test not found (file doesn't exist yet).

2. Create `backend/app/services/sse_broker.py` with `SseBroker` class.

3. Run the unit test again. Expect: pass.

4. Write the failing router test `backend/app/tests/test_events_router.py`.
       npx nx run backend:test -- -k test_events_router
   Expect: fails (router still returns only heartbeats).

5. Rewrite `backend/app/routers/events.py` to use the broker.

6. Wire broker startup/shutdown into `backend/app/main.py`.

7. Run all backend tests:
       npx nx run backend:test
   Expect: 213 + new tests passing, 0 failures.

8. Run lint:
       npx nx run backend:lint

**Milestone 2 steps:**

9. Create `frontend/src/hooks/useOpenCodeStream.ts`.

10. Modify `frontend/src/components/PipelineCard.tsx` — add `LiveOutputPanel`,
    update `StepRow` signature, wire `useOpenCodeStream` in `PipelineCard`.

11. Run type-check:
        npx nx run frontend:type-check
    Expect: clean.

## Validation and Acceptance

**Backend (automated)**

    npx nx run backend:test

Expect: all existing 213 tests still pass plus the new SSE tests. No failures.

**Frontend (type-check)**

    npx nx run frontend:type-check

Expect: clean exit (0 errors).

**Manual end-to-end**

Start the backend and frontend dev servers. Create a new pipeline. While a step is
running, the pipeline card should display a "Live output" panel below the running step
badge. Lines of JSON should stream in as OpenCode emits events. When the step finishes,
the live panel should disappear and the "view handoff" toggle should appear.

Open a second browser tab to the same page and verify both tabs show the live output.

Disconnect the network (or kill the backend) and reconnect — verify no crash on the
server and the browser auto-reconnects.

## Idempotence and Recovery

If Milestone 1 is committed but Milestone 2 is not yet started, the backend serves the
upgraded `/events` endpoint. The existing frontend stub (no `EventSource`) simply
ignores the new events. No regression.

If the OpenCode server is down when the broker starts, `stream_events` will retry with
`reconnect_delay=1.0`. The broker starts, emits nothing except heartbeats to connected
clients, and begins forwarding events as soon as OpenCode comes back. No error surface to
the user.

## Artifacts and Notes

### SseBroker public interface (final)

    class SseBroker:
        def __init__(self, client: OpenCodeClient) -> None
        async def start(self) -> None       # starts background task
        async def stop(self) -> None        # stops task + drains subscribers
        def subscribe(self) -> asyncio.Queue[str | object]
        def unsubscribe(self, q: asyncio.Queue) -> None

### SSE frame format sent to browser

Every non-heartbeat frame:

    data: {"event": "<type>", "data": <json-value>}\n\n

Heartbeat frame:

    data: {"type": "heartbeat", "ts": <unix-timestamp>}\n\n

## Interfaces and Dependencies

Backend new file: `backend/app/services/sse_broker.py`

    from asyncio import Queue
    from app.adapters.opencode_client import OpenCodeClient

    _STOP: object = object()   # sentinel

    class SseBroker:
        _client: OpenCodeClient
        _subscribers: set[Queue]
        _task: asyncio.Task | None

Frontend new file: `frontend/src/hooks/useOpenCodeStream.ts`

Existing libraries used (already installed):
- `sse_starlette` — `EventSourceResponse` (backend)
- Browser native `EventSource` API (frontend, no library needed)
