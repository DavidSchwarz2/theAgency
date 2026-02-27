import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx

from app.adapters.opencode_models import MessageResponse, SessionInfo, TodoItem

logger = logging.getLogger(__name__)


class OpenCodeClientError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class OpenCodeClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(base_url=self._base_url)
        self._stop_event = asyncio.Event()

    async def __aenter__(self) -> "OpenCodeClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        # Guard against double-close when both explicit close() and context-manager are used.
        if not self._http.is_closed:
            await self.close()

    async def close(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        try:
            resp = await self._http.get("/global/health")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    async def create_session(self, title: str | None = None) -> SessionInfo:
        body: dict[str, Any] = {}
        if title is not None:
            body["title"] = title
        resp = await self._http.post("/session", json=body)
        self._raise_for_status(resp)
        return SessionInfo.model_validate(resp.json())

    async def list_sessions(self) -> list[SessionInfo]:
        resp = await self._http.get("/session")
        self._raise_for_status(resp)
        return [SessionInfo.model_validate(item) for item in resp.json()]

    async def get_session(self, session_id: str) -> SessionInfo:
        resp = await self._http.get(f"/session/{session_id}")
        self._raise_for_status(resp)
        return SessionInfo.model_validate(resp.json())

    async def delete_session(self, session_id: str) -> bool:
        resp = await self._http.delete(f"/session/{session_id}")
        self._raise_for_status(resp)
        return bool(resp.json())

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    async def send_message(
        self,
        session_id: str,
        prompt: str,
        agent: str | None = None,
        model: str | None = None,
    ) -> MessageResponse:
        body: dict[str, Any] = {"parts": [{"type": "text", "text": prompt}]}
        if agent is not None:
            body["agent"] = agent
        if model is not None:
            body["model"] = model
        resp = await self._http.post(f"/session/{session_id}/message", json=body)
        self._raise_for_status(resp)
        return MessageResponse.model_validate(resp.json())

    async def send_message_async(
        self,
        session_id: str,
        prompt: str,
        agent: str | None = None,
    ) -> None:
        body: dict[str, Any] = {"parts": [{"type": "text", "text": prompt}]}
        if agent is not None:
            body["agent"] = agent
        resp = await self._http.post(f"/session/{session_id}/prompt_async", json=body)
        self._raise_for_status(resp)

    async def abort_session(self, session_id: str) -> bool:
        resp = await self._http.post(f"/session/{session_id}/abort")
        self._raise_for_status(resp)
        return bool(resp.json())

    # ------------------------------------------------------------------
    # Todos
    # ------------------------------------------------------------------

    async def get_todos(self, session_id: str) -> list[TodoItem]:
        resp = await self._http.get(f"/session/{session_id}/todo")
        self._raise_for_status(resp)
        return [TodoItem.model_validate(item) for item in resp.json()]

    # ------------------------------------------------------------------
    # SSE (Milestone 3)
    # ------------------------------------------------------------------

    async def stream_events(
        self,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
        reconnect_delay: float = 1.0,
    ) -> None:
        """Stream SSE events from /global/event, calling callback on each frame.

        Reconnects automatically if the connection drops. Exits when stop_streaming() is called.
        The stop event is cleared at entry so this method is safe to call multiple times.
        """
        self._stop_event.clear()
        timeout = httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0)

        while not self._stop_event.is_set():
            try:
                async with self._http.stream("GET", "/global/event", timeout=timeout) as response:
                    async for frame in self._parse_sse_lines(response.aiter_lines()):
                        if self._stop_event.is_set():
                            return
                        await callback(frame)
                return  # Stream ended cleanly — no reconnect needed after EOF
            except httpx.HTTPError as exc:
                if self._stop_event.is_set():
                    return
                logger.warning("SSE stream error, reconnecting in %.1fs: %s", reconnect_delay, exc)
                if reconnect_delay > 0:
                    await asyncio.sleep(reconnect_delay)

    def stop_streaming(self) -> None:
        """Signal the stream_events loop to exit after the current frame."""
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _parse_sse_lines(lines: AsyncIterator[str]) -> AsyncIterator[dict[str, Any]]:
        """Parse SSE frames from an async line iterator.

        Yields one dict per frame: ``{"event": "<type>", "data": <parsed-json-or-str>}``.
        Lines starting with ":" are SSE comments and are silently ignored.
        """
        event_type: str | None = None
        data_raw: str | None = None

        async for raw_line in lines:
            line = raw_line.strip()
            if line.startswith("event:"):
                event_type = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_raw = line[len("data:") :].strip()
            elif line == "":
                # Blank line = frame boundary
                if data_raw is not None:
                    try:
                        parsed: Any = json.loads(data_raw)
                    except json.JSONDecodeError:
                        parsed = data_raw
                    yield {"event": event_type or "message", "data": parsed}
                event_type = None
                data_raw = None
            # Lines starting with ":" are SSE comments — silently ignored

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.is_error:
            raise OpenCodeClientError(
                f"OpenCode API error {resp.status_code}: {resp.text}",
                status_code=resp.status_code,
            )
