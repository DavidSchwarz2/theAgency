import asyncio
import contextlib
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.github_client import GitHubClient
from app.adapters.opencode_client import OpenCodeClient
from app.config.config import settings
from app.database import AsyncSessionLocal
from app.routers import approvals as approvals_router
from app.routers import audit as audit_router
from app.routers import events, health
from app.routers import fs as fs_router
from app.routers import pipelines as pipelines_router
from app.routers import registry as registry_router
from app.services.agent_registry import AgentRegistry, watch_and_reload
from app.services.pipeline_runner import recover_interrupted_pipelines

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
    proc = await asyncio.create_subprocess_exec(
        "uv",
        "run",
        "alembic",
        "upgrade",
        "head",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    if proc.returncode != 0:
        stderr_text = stderr_bytes.decode()
        logger.error("migration_failed", stderr=stderr_text)
        raise RuntimeError(f"Alembic migration failed: {stderr_text}")
    logger.info("migrations_complete", stdout=stdout_bytes.decode().strip())

    # Initialize Agent Registry from YAML config
    agent_registry = AgentRegistry(
        agents_path=settings.agents_config_path,
        pipelines_path=settings.pipelines_config_path,
    )
    app.state.registry = agent_registry

    # Initialize OpenCode client and pipeline task tracking
    opencode_client = OpenCodeClient(base_url=settings.opencode_base_url)
    app.state.opencode_client = opencode_client
    app.state.pipeline_tasks = {}  # dict[int, asyncio.Task]
    app.state.active_runners = {}
    app.state.approval_events = {}
    app.state.step_timeout = float(settings.step_timeout_seconds)
    app.state.db_session_factory = AsyncSessionLocal

    # Initialize GitHub client (optional — only when token is configured)
    github_client: GitHubClient | None = GitHubClient(token=settings.github_token) if settings.github_token else None
    app.state.github_client = github_client

    # Start file watcher for hot-reload
    stop_event = asyncio.Event()
    watcher_task = asyncio.create_task(
        watch_and_reload(
            agent_registry,
            [settings.agents_config_path, settings.pipelines_config_path],
            stop_event,
        )
    )

    # Check OpenCode server availability
    opencode_available = await opencode_client.health_check()
    if opencode_available:
        logger.info("opencode_server_available", url=settings.opencode_base_url)
    else:
        logger.warning("opencode_server_unavailable", url=settings.opencode_base_url)

    # Recover any pipelines that were interrupted by a previous crash
    await recover_interrupted_pipelines(
        db_session_factory=AsyncSessionLocal,
        client=opencode_client,
        registry=agent_registry,
        task_set=app.state.pipeline_tasks,
        step_timeout=app.state.step_timeout,
    )

    yield

    # Shutdown: cancel pending pipeline tasks
    for task in list(app.state.pipeline_tasks.values()):
        task.cancel()
    if app.state.pipeline_tasks:
        await asyncio.gather(*app.state.pipeline_tasks.values(), return_exceptions=True)

    # Shutdown: stop file watcher
    stop_event.set()
    watcher_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await watcher_task

    await opencode_client.close()
    if github_client is not None:
        await github_client.close()
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
app.include_router(fs_router.router)
app.include_router(registry_router.router)
app.include_router(pipelines_router.router)
app.include_router(approvals_router.router)
app.include_router(audit_router.router)
