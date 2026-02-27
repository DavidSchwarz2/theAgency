import subprocess
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.config import settings
from app.routers import events, health

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("running_migrations", action="alembic upgrade head")
    result = subprocess.run(  # noqa: S603
        ["uv", "run", "alembic", "upgrade", "head"],  # noqa: S607
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error("migration_failed", stderr=result.stderr)
        raise RuntimeError(f"Alembic migration failed: {result.stderr}")
    logger.info("migrations_complete", stdout=result.stdout.strip())
    yield
    logger.info("shutdown")


app = FastAPI(
    title="theAgency",
    description="AI Development Pipeline Orchestrator",
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(events.router)
