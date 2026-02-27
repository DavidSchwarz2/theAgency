from fastapi import APIRouter
from pydantic import BaseModel

from app.config.config import settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=settings.app_version)
