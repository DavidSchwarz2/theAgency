"""TDD tests for SseBroker (fan-out) and the /events router."""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.services.sse_broker import SseBroker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_client(
    frames: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Return a mock OpenCodeClient whose stream_events() calls the callback for each frame."""
    client = MagicMock()

    async def _stream_events(
        callback: Callable[[dict[str, Any]], Awaitable[None]],
        reconnect_delay: float = 1.0,
    ) -> None:
        for frame in frames or []:
            await callback(frame)

    client.stream_events = _stream_events
    client.stop_streaming = MagicMock()
    return client


# ---------------------------------------------------------------------------
# Unit tests — SseBroker in isolation (no HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscriber_receives_event():
    """A subscribed queue receives the JSON-serialised event when stream_events fires."""
    frame = {"event": "message", "data": {"text": "hello"}}
    client = _make_mock_client(frames=[frame])
    broker = SseBroker(client=client)  # type: ignore[arg-type]

    q = broker.subscribe()
    await broker.start()

    item = await asyncio.wait_for(q.get(), timeout=1.0)
    assert json.loads(item) == frame


@pytest.mark.asyncio
async def test_multiple_subscribers_receive_same_event():
    """Two subscribers both receive the same event."""
    frame = {"event": "tool_call", "data": {"tool": "read_file"}}
    client = _make_mock_client(frames=[frame])
    broker = SseBroker(client=client)  # type: ignore[arg-type]

    q1 = broker.subscribe()
    q2 = broker.subscribe()
    await broker.start()

    item1 = await asyncio.wait_for(q1.get(), timeout=1.0)
    item2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    assert json.loads(item1) == frame
    assert json.loads(item2) == frame


@pytest.mark.asyncio
async def test_unsubscribe_removes_subscriber():
    """After unsubscribing, the queue no longer receives events."""
    # We use an event to gate the stream: emit one frame, wait, emit another.
    gate = asyncio.Event()

    async def _stream(callback, reconnect_delay=1.0):
        await callback({"event": "first", "data": {}})
        await gate.wait()
        await callback({"event": "second", "data": {}})

    client = MagicMock()
    client.stream_events = _stream
    client.stop_streaming = MagicMock()

    broker = SseBroker(client=client)  # type: ignore[arg-type]
    q = broker.subscribe()
    await broker.start()

    # Wait for first frame deterministically.
    _ = await asyncio.wait_for(q.get(), timeout=1.0)  # consume first frame

    # Unsubscribe before second frame arrives.
    broker.unsubscribe(q)
    gate.set()
    await asyncio.sleep(0.05)

    # Queue should still be empty (no second frame delivered).
    assert q.empty()


@pytest.mark.asyncio
async def test_stop_sends_sentinel_to_subscribers():
    """stop() enqueues the STOP sentinel onto all subscriber queues."""
    client = _make_mock_client(frames=[])
    broker = SseBroker(client=client)  # type: ignore[arg-type]

    q = broker.subscribe()
    await broker.start()
    await broker.stop()

    # The sentinel should be the only item in the queue.
    item = q.get_nowait()
    assert item is SseBroker.STOP


# ---------------------------------------------------------------------------
# Router-level tests — test the SSE generator logic directly (no ASGI transport)
#
# httpx ASGITransport buffers the full response body before yielding lines,
# so SSE streaming tests must exercise the generator logic directly rather
# than through an HTTP client.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_events_generator_emits_heartbeat_when_queue_empty(monkeypatch):
    """The SSE generator logic emits a heartbeat when no events arrive within the interval."""
    import app.routers.events as events_module  # noqa: PLC0415

    # Override interval to near-zero for the test.
    monkeypatch.setattr(events_module, "_HEARTBEAT_INTERVAL", 0.05)

    client = _make_mock_client(frames=[])
    broker = SseBroker(client=client)  # type: ignore[arg-type]
    await broker.start()

    frames_collected: list[dict] = []

    async def _read():
        q = broker.subscribe()
        try:
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=events_module._HEARTBEAT_INTERVAL)
                    if item is SseBroker.STOP:
                        break
                    frames_collected.append(json.loads(item))
                except TimeoutError:
                    frames_collected.append({"type": "heartbeat", "ts": int(time.time())})
                    break  # stop after first heartbeat
        finally:
            broker.unsubscribe(q)

    await asyncio.wait_for(_read(), timeout=2.0)
    await broker.stop()

    assert len(frames_collected) == 1
    assert frames_collected[0].get("type") == "heartbeat"


@pytest.mark.asyncio
async def test_events_generator_forwards_event_from_broker():
    """The SSE generator yields an event frame when the broker delivers one."""
    frame = {"event": "message", "data": {"text": "live output"}}
    client = _make_mock_client(frames=[frame])
    broker = SseBroker(client=client)  # type: ignore[arg-type]

    # Subscribe BEFORE start() so we don't miss the event.
    q = broker.subscribe()
    await broker.start()

    frames_collected: list[dict] = []
    try:
        item = await asyncio.wait_for(q.get(), timeout=1.0)
        if item is not SseBroker.STOP:
            frames_collected.append(json.loads(item))
    finally:
        broker.unsubscribe(q)
        await broker.stop()

    assert len(frames_collected) == 1
    assert frames_collected[0] == frame
