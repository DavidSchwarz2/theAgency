"""SseBroker — fan-out of OpenCode SSE events to all connected browser clients.

The broker maintains a single upstream connection to OpenCode's /global/event SSE stream
and distributes every received frame to all currently subscribed asyncio.Queue instances
(one per connected browser client).

Usage in lifespan (main.py):
    broker = SseBroker(client=opencode_client)
    app.state.sse_broker = broker
    await broker.start()

Usage in the /events router (via the typed dependency `get_sse_broker`):
    async for item in broker.event_stream():
        if item is SseBroker.STOP:
            break
        yield {"data": item}
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from app.adapters.opencode_client import OpenCodeClient

logger = logging.getLogger(__name__)

_QUEUE_MAX_SIZE = 512  # prevent memory runaway for slow clients


class SseBroker:
    """Fan-out broker: one OpenCode connection → N browser SSE clients.

    ``STOP`` is a public sentinel placed on subscriber queues when the broker
    shuts down. Consumers should break their read loop when they receive it.
    """

    STOP: object = object()

    def __init__(self, client: OpenCodeClient) -> None:
        self._client = client
        self._subscribers: set[asyncio.Queue[Any]] = set()
        self._task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background task that reads from the OpenCode SSE stream.

        This method is async for API consistency with ``stop()``. Safe to call
        multiple times — a second call while the task is still running is a no-op.
        """
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name="sse_broker")

    async def stop(self) -> None:
        """Stop the broker and notify all subscribers to exit.

        Signals the OpenCodeClient to stop streaming, cancels the background
        task, and places the STOP sentinel on every subscriber queue so that
        their SSE generators exit cleanly.
        """
        self._client.stop_streaming()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.warning("sse_broker_stop_unexpected_error", exc_info=True)
            self._task = None

        # Notify all subscribers to exit.
        for q in list(self._subscribers):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(self.STOP)

    # ------------------------------------------------------------------
    # High-level consumer API
    # ------------------------------------------------------------------

    async def event_stream(self) -> AsyncGenerator[Any, None]:
        """Async generator that yields serialised event strings until the broker stops.

        Each yielded value is either a JSON string (a serialised OpenCode event frame)
        or ``SseBroker.STOP`` to signal the consumer should exit.

        Usage::

            async for item in broker.event_stream():
                if item is SseBroker.STOP:
                    break
                yield {"data": item}

        The subscriber queue is registered on entry and unregistered on exit,
        so callers do not need to manage subscribe/unsubscribe themselves.
        """
        q = self.subscribe()
        try:
            while True:
                item = await q.get()
                yield item
                if item is self.STOP:
                    break
        finally:
            self.unsubscribe(q)

    # ------------------------------------------------------------------
    # Low-level subscription management (for tests / advanced use)
    # ------------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue[Any]:
        """Register a new subscriber and return its dedicated queue."""
        q: asyncio.Queue[Any] = asyncio.Queue(maxsize=_QUEUE_MAX_SIZE)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Any]) -> None:
        """Remove a subscriber queue. Safe to call if the queue was already removed."""
        self._subscribers.discard(q)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        """Background task: stream from OpenCode and fan out to all subscribers."""
        try:
            await self._client.stream_events(self._on_event, reconnect_delay=1.0)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("sse_broker_run_error")

    async def _on_event(self, frame: dict[str, Any]) -> None:
        """Callback called by stream_events for every received frame.

        Serialises the frame to JSON and puts it on every subscriber queue.
        Drops the frame (logs a warning) if a subscriber queue is full.
        """
        serialised = json.dumps(frame)
        for q in list(self._subscribers):
            try:
                q.put_nowait(serialised)
            except asyncio.QueueFull:  # noqa: PERF203
                logger.warning("sse_subscriber_queue_full_dropping_event")
