import asyncio
import contextlib
import subprocess
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.config import settings
from app.routers import events, health
from app.routers import registry as registry_router
from app.services.agent_registry import AgentRegistry, watch_and_reload

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

    # Initialize Agent Registry from YAML config
    agent_registry = AgentRegistry(
        agents_path=settings.agents_config_path,
        pipelines_path=settings.pipelines_config_path,
    )
    app.state.registry = agent_registry

    # Start file watcher for hot-reload
    stop_event = asyncio.Event()
    watcher_task = asyncio.create_task(
        watch_and_reload(
            agent_registry,
            [settings.agents_config_path, settings.pipelines_config_path],
            stop_event,
        )
    )

    yield

    # Shutdown: stop file watcher
    stop_event.set()
    watcher_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await watcher_task
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
app.include_router(registry_router.router)
