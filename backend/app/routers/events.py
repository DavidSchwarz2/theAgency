import asyncio
import time

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

router = APIRouter()


async def _heartbeat_generator():
    while True:
        yield {"data": f'{{"type": "heartbeat", "ts": {int(time.time())}}}'}
        await asyncio.sleep(5)


@router.get("/events")
async def events():
    return EventSourceResponse(_heartbeat_generator())
