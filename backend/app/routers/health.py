import asyncio

import structlog
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.adapters.opencode_client import OpenCodeClient
from app.config.config import settings

router = APIRouter()
logger = structlog.get_logger(__name__)


class HealthResponse(BaseModel):
    status: str
    version: str


class OpenCodeStatusResponse(BaseModel):
    available: bool


class OpenCodeStartResponse(BaseModel):
    available: bool
    started: bool


def get_opencode_client(request: Request) -> OpenCodeClient:
    return request.app.state.opencode_client


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=settings.app_version)


@router.get("/health/opencode", response_model=OpenCodeStatusResponse)
async def opencode_status(client: OpenCodeClient = Depends(get_opencode_client)) -> OpenCodeStatusResponse:
    available = await client.health_check()
    return OpenCodeStatusResponse(available=available)


@router.post("/health/opencode/start")
async def opencode_start(client: OpenCodeClient = Depends(get_opencode_client)) -> JSONResponse:
    if await client.health_check():
        return JSONResponse(OpenCodeStartResponse(available=True, started=False).model_dump())

    logger.info("opencode_server_starting", url=settings.opencode_base_url)
    await asyncio.create_subprocess_exec("opencode", "serve", "--port", str(_parse_port(settings.opencode_base_url)))

    # Poll until opencode is ready (up to 10s)
    for _ in range(10):
        await asyncio.sleep(1)
        if await client.health_check():
            break
    available = await client.health_check()

    if not available:
        logger.warning("opencode_server_start_failed", url=settings.opencode_base_url)
        return JSONResponse(
            OpenCodeStartResponse(available=False, started=True).model_dump(),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    logger.info("opencode_server_started", url=settings.opencode_base_url)
    return JSONResponse(OpenCodeStartResponse(available=True, started=True).model_dump())


def _parse_port(base_url: str) -> int:
    """Extract port number from a base URL like http://localhost:3000."""
    try:
        return int(base_url.rstrip("/").rsplit(":", 1)[-1])
    except (ValueError, IndexError):
        return 3000
