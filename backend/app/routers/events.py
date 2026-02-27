import asyncio
import json
import time

from fastapi import Depends, Request
from fastapi.routing import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.services.sse_broker import SseBroker

router = APIRouter()

_HEARTBEAT_INTERVAL = 5.0


def get_sse_broker(request: Request) -> SseBroker:
    """FastAPI dependency that retrieves the typed SseBroker from app.state."""
    broker: SseBroker = request.app.state.sse_broker
    return broker


@router.get("/events", response_class=EventSourceResponse)
async def events(broker: SseBroker = Depends(get_sse_broker)) -> EventSourceResponse:
    async def _event_generator():
        async for item in _heartbeat_stream(broker):
            yield item

    return EventSourceResponse(_event_generator())


async def _heartbeat_stream(broker: SseBroker):
    """Yield SSE frames from the broker, interspersed with periodic heartbeats.

    Emits a heartbeat JSON frame after each ``_HEARTBEAT_INTERVAL`` seconds of
    silence. Exits cleanly when the broker sends its STOP sentinel.
    """
    q = broker.subscribe()
    try:
        while True:
            try:
                item = await asyncio.wait_for(q.get(), timeout=_HEARTBEAT_INTERVAL)
                if item is SseBroker.STOP:
                    break
                yield {"data": item}
            except TimeoutError:
                yield {"data": json.dumps({"type": "heartbeat", "ts": int(time.time())})}
    finally:
        broker.unsubscribe(q)
