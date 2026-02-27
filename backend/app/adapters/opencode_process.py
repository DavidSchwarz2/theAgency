import asyncio
import logging

from app.adapters.opencode_client import OpenCodeClient

logger = logging.getLogger(__name__)


class OpenCodeStartupError(Exception):
    """Raised when the OpenCode server process fails to become healthy within the timeout."""


class OpenCodeProcessManager:
    """Manages a single OpenCode server subprocess (start / stop / health)."""

    _MAX_ATTEMPTS = 30
    _POLL_INTERVAL = 0.5
    _STOP_TIMEOUT = 5.0

    def __init__(self, opencode_binary: str = "opencode") -> None:
        self._binary = opencode_binary
        self._process: asyncio.subprocess.Process | None = None
        self._client: OpenCodeClient | None = None
        self._port: int | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def start(self, port: int, cwd: str) -> OpenCodeClient:
        """Launch ``opencode serve --port <port>`` and wait until healthy.

        Returns an OpenCodeClient that is already connected and health-checked.
        Raises RuntimeError if called while a process is already running.
        Raises OpenCodeStartupError if the server does not become healthy within
        ``_MAX_ATTEMPTS * _POLL_INTERVAL`` seconds.
        """
        if self._process is not None:
            raise RuntimeError(
                "OpenCodeProcessManager.start() called while a process is already running. Call stop() first."
            )

        logger.info("Starting OpenCode server on port %d (cwd=%s)", port, cwd)
        self._port = port
        self._process = await asyncio.create_subprocess_exec(
            self._binary,
            "serve",
            "--port",
            str(port),
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        base_url = f"http://127.0.0.1:{port}"
        client = OpenCodeClient(base_url=base_url)

        for attempt in range(self._MAX_ATTEMPTS):
            if await client.health_check():
                logger.info("OpenCode server healthy after %d poll(s)", attempt + 1)
                self._client = client
                return client
            await asyncio.sleep(self._POLL_INTERVAL)

        # Health never succeeded — kill the process and bail out
        logger.error("OpenCode server on port %d did not become healthy; killing process", port)
        self._process.terminate()
        await self._process.wait()
        await client.close()
        self._process = None
        self._port = None
        raise OpenCodeStartupError(
            f"OpenCode server on port {port} did not become healthy after "
            f"{self._MAX_ATTEMPTS * self._POLL_INTERVAL:.1f}s"
        )

    async def stop(self) -> None:
        """Gracefully stop the managed process (SIGTERM, then SIGKILL after timeout)."""
        if self._process is None:
            return
        logger.info("Stopping OpenCode server (port=%s)", self._port)
        self._process.terminate()
        try:
            await asyncio.wait_for(self._process.wait(), timeout=self._STOP_TIMEOUT)
            logger.info("OpenCode server stopped cleanly")
        except TimeoutError:
            logger.warning("OpenCode server did not exit in %.1fs; sending SIGKILL", self._STOP_TIMEOUT)
            self._process.kill()
        finally:
            if self._client is not None:
                await self._client.close()
                self._client = None
            self._process = None
            self._port = None

    def is_running(self) -> bool:
        """Return True only if the subprocess is alive (returncode is None)."""
        return not (self._process is None or self._process.returncode is not None)

    @property
    def port(self) -> int | None:
        return self._port
