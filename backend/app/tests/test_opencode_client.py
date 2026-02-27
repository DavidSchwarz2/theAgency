import httpx
import pytest
import respx

from app.adapters.opencode_client import OpenCodeClient, OpenCodeClientError
from app.adapters.opencode_models import MessageResponse, SessionInfo, TodoItem

BASE_URL = "http://127.0.0.1:4096"


class TestHealthCheck:
    async def test_health_check_returns_true_when_healthy(self):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get("/global/health").respond(200, json={"healthy": True, "version": "1.0"})
            async with OpenCodeClient(base_url=BASE_URL) as client:
                result = await client.health_check()
        assert result is True

    async def test_health_check_returns_false_on_connection_error(self):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get("/global/health").mock(side_effect=httpx.ConnectError("refused"))
            async with OpenCodeClient(base_url=BASE_URL) as client:
                result = await client.health_check()
        assert result is False


class TestCreateSession:
    async def test_create_session(self):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.post("/session").respond(200, json={"id": "abc123", "title": "Test"})
            async with OpenCodeClient(base_url=BASE_URL) as client:
                result = await client.create_session()
        assert isinstance(result, SessionInfo)
        assert result.id == "abc123"
        assert result.title == "Test"

    async def test_create_session_with_title(self):
        with respx.mock(base_url=BASE_URL) as mock:
            route = mock.post("/session").respond(200, json={"id": "xyz", "title": "My Session"})
            async with OpenCodeClient(base_url=BASE_URL) as client:
                result = await client.create_session(title="My Session")
        assert result.title == "My Session"
        sent_body = route.calls.last.request.content
        assert b"My Session" in sent_body


class TestListSessions:
    async def test_list_sessions(self):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get("/session").respond(
                200,
                json=[{"id": "s1", "title": "One"}, {"id": "s2", "title": "Two"}],
            )
            async with OpenCodeClient(base_url=BASE_URL) as client:
                result = await client.list_sessions()
        assert len(result) == 2
        assert all(isinstance(s, SessionInfo) for s in result)
        assert result[0].id == "s1"
        assert result[1].id == "s2"


class TestGetSession:
    async def test_get_session(self):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get("/session/abc123").respond(200, json={"id": "abc123", "title": "Hello"})
            async with OpenCodeClient(base_url=BASE_URL) as client:
                result = await client.get_session("abc123")
        assert isinstance(result, SessionInfo)
        assert result.id == "abc123"


class TestDeleteSession:
    async def test_delete_session(self):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.delete("/session/abc123").respond(200, text="true")
            async with OpenCodeClient(base_url=BASE_URL) as client:
                result = await client.delete_session("abc123")
        assert result is True


class TestSendMessage:
    async def test_send_message(self):
        payload = {
            "info": {"id": "m1", "sessionID": "abc123", "role": "assistant"},
            "parts": [{"type": "text", "content": "Hello!"}],
        }
        with respx.mock(base_url=BASE_URL) as mock:
            mock.post("/session/abc123/message").respond(200, json=payload)
            async with OpenCodeClient(base_url=BASE_URL) as client:
                result = await client.send_message("abc123", "Hi")
        assert isinstance(result, MessageResponse)
        assert result.info.id == "m1"
        assert result.parts[0].type == "text"

    async def test_send_message_with_agent(self):
        payload = {
            "info": {"id": "m2", "sessionID": "abc123", "role": "assistant"},
            "parts": [],
        }
        with respx.mock(base_url=BASE_URL) as mock:
            route = mock.post("/session/abc123/message").respond(200, json=payload)
            async with OpenCodeClient(base_url=BASE_URL) as client:
                await client.send_message("abc123", "Do something", agent="developer")
        sent_body = route.calls.last.request.content
        assert b"developer" in sent_body


class TestSendMessageAsync:
    async def test_send_message_async(self):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.post("/session/abc123/prompt_async").respond(204)
            async with OpenCodeClient(base_url=BASE_URL) as client:
                result = await client.send_message_async("abc123", "Go")
        assert result is None


class TestAbortSession:
    async def test_abort_session(self):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.post("/session/abc123/abort").respond(200, text="true")
            async with OpenCodeClient(base_url=BASE_URL) as client:
                result = await client.abort_session("abc123")
        assert result is True


class TestGetTodos:
    async def test_get_todos(self):
        todos = [
            {"content": "Fix bug", "status": "pending", "priority": "high"},
            {"content": "Write tests", "status": "completed", "priority": "medium"},
        ]
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get("/session/abc123/todo").respond(200, json=todos)
            async with OpenCodeClient(base_url=BASE_URL) as client:
                result = await client.get_todos("abc123")
        assert len(result) == 2
        assert all(isinstance(t, TodoItem) for t in result)
        assert result[0].content == "Fix bug"
        assert result[1].status == "completed"


class TestErrorHandling:
    async def test_client_raises_on_http_error(self):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get("/session/bad").respond(500, text="Internal Server Error")
            async with OpenCodeClient(base_url=BASE_URL) as client:
                with pytest.raises(OpenCodeClientError) as exc_info:
                    await client.get_session("bad")
        assert exc_info.value.status_code == 500


class TestContextManager:
    async def test_client_context_manager(self):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get("/global/health").respond(200, json={"healthy": True, "version": "1.0"})
            async with OpenCodeClient(base_url=BASE_URL) as client:
                result = await client.health_check()
        # After exiting the context manager the http client should be closed
        assert client._http.is_closed
        assert result is True


# ---------------------------------------------------------------------------
# SSE tests (Milestone 3)
# ---------------------------------------------------------------------------

SSE_FRAME_1 = b'event: message.updated\ndata: {"id": "1", "type": "text"}\n\n'
SSE_FRAME_2 = b'event: tool.call\ndata: {"tool": "bash", "input": "ls"}\n\n'


class TestStreamEvents:
    async def test_stream_events_calls_callback(self):
        """Callback is called once per SSE frame with the parsed event and data."""
        received: list[dict] = []

        async def callback(event: dict) -> None:
            received.append(event)

        body = SSE_FRAME_1 + SSE_FRAME_2

        with respx.mock(base_url=BASE_URL) as mock:
            mock.get("/global/event").respond(200, content=body)
            async with OpenCodeClient(base_url=BASE_URL) as client:
                await client.stream_events(callback, reconnect_delay=0.0)

        assert len(received) == 2
        assert received[0]["event"] == "message.updated"
        assert received[0]["data"] == {"id": "1", "type": "text"}
        assert received[1]["event"] == "tool.call"

    async def test_stream_events_reconnects_on_disconnect(self):
        """When the stream errors, the client reconnects and the callback is still called."""
        received: list[dict] = []

        async def callback(event: dict) -> None:
            received.append(event)

        call_count = 0

        def side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ReadError("disconnected")
            return respx.MockResponse(200, content=SSE_FRAME_1)

        with respx.mock(base_url=BASE_URL) as mock:
            mock.get("/global/event").mock(side_effect=side_effect)
            async with OpenCodeClient(base_url=BASE_URL) as client:
                await client.stream_events(callback, reconnect_delay=0.0)

        assert len(received) == 1

    async def test_stream_events_stops_on_signal(self):
        """stop_streaming() causes stream_events to exit cleanly."""
        received: list[dict] = []

        async def callback(event: dict) -> None:
            received.append(event)

        # Serve an infinite stream but call stop_streaming during callback
        infinite_body = SSE_FRAME_1 * 1000

        stop_called = False

        async def stopping_callback(event: dict) -> None:
            nonlocal stop_called
            received.append(event)
            if not stop_called:
                stop_called = True
                client_ref.stop_streaming()

        with respx.mock(base_url=BASE_URL) as mock:
            mock.get("/global/event").respond(200, content=infinite_body)
            async with OpenCodeClient(base_url=BASE_URL) as client_ref:
                await client_ref.stream_events(stopping_callback, reconnect_delay=0.0)

        # At least one event received and loop exited
        assert len(received) >= 1
