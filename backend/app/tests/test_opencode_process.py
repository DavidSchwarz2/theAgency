import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.opencode_client import OpenCodeClient
from app.adapters.opencode_process import OpenCodeProcessManager, OpenCodeStartupError


class TestStartLaunchesSubprocess:
    async def test_start_launches_subprocess(self):
        mock_proc = MagicMock()
        mock_proc.returncode = None

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_proc
            manager = OpenCodeProcessManager()
            with patch.object(OpenCodeClient, "health_check", new_callable=AsyncMock, return_value=True):
                client = await manager.start(port=4096, cwd="/tmp")
                await client.close()

        mock_exec.assert_called_once()
        args = mock_exec.call_args[0]
        assert "opencode" in args
        assert "serve" in args
        assert "--port" in args
        assert "4096" in args


class TestStartPollsHealthUntilReady:
    async def test_start_polls_health_until_ready(self):
        mock_proc = MagicMock()
        mock_proc.returncode = None

        # Fail 3 times then succeed
        health_side_effects = [False, False, False, True]
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_proc
            with (
                patch.object(
                    OpenCodeClient, "health_check", new_callable=AsyncMock, side_effect=health_side_effects
                ) as mock_health,
                patch("asyncio.sleep", new_callable=AsyncMock),
            ):
                manager = OpenCodeProcessManager()
                client = await manager.start(port=4096, cwd="/tmp")
                await client.close()

        # health_check was called exactly 4 times (3 failures + 1 success)
        assert mock_health.call_count == 4


class TestStartRaisesOnTimeout:
    async def test_start_raises_on_timeout(self):
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.terminate = MagicMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec,
            patch.object(OpenCodeClient, "health_check", new_callable=AsyncMock, return_value=False),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_exec.return_value = mock_proc
            manager = OpenCodeProcessManager()
            with pytest.raises(OpenCodeStartupError):
                await manager.start(port=4096, cwd="/tmp")


class TestStartReturnsClient:
    async def test_start_returns_client(self):
        mock_proc = MagicMock()
        mock_proc.returncode = None

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_proc
            with patch.object(OpenCodeClient, "health_check", new_callable=AsyncMock, return_value=True):
                manager = OpenCodeProcessManager()
                client = await manager.start(port=4096, cwd="/tmp")

        assert isinstance(client, OpenCodeClient)
        await client.close()


class TestStopSendsSigterm:
    async def test_stop_sends_sigterm(self):
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.terminate = MagicMock()
        mock_proc.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_proc
            with patch.object(OpenCodeClient, "health_check", new_callable=AsyncMock, return_value=True):
                manager = OpenCodeProcessManager()
                client = await manager.start(port=4096, cwd="/tmp")
                await client.close()

        await manager.stop()
        mock_proc.terminate.assert_called_once()


class TestStopSendsSigkillAfterTimeout:
    async def test_stop_sends_sigkill_after_timeout(self):
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.terminate = MagicMock()
        mock_proc.kill = MagicMock()

        # Simulate process that never exits on wait → asyncio.wait_for raises TimeoutError
        async def slow_wait():
            await asyncio.sleep(999)

        mock_proc.wait = slow_wait

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_proc
            with patch.object(OpenCodeClient, "health_check", new_callable=AsyncMock, return_value=True):
                manager = OpenCodeProcessManager()
                client = await manager.start(port=4096, cwd="/tmp")
                await client.close()

        await manager.stop()
        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()


class TestIsRunning:
    async def test_is_running_true(self):
        mock_proc = MagicMock()
        mock_proc.returncode = None

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_proc
            with patch.object(OpenCodeClient, "health_check", new_callable=AsyncMock, return_value=True):
                manager = OpenCodeProcessManager()
                client = await manager.start(port=4096, cwd="/tmp")
                running = manager.is_running()
                await client.close()

        assert running is True

    async def test_is_running_false_when_process_dead(self):
        mock_proc = MagicMock()
        mock_proc.returncode = None

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = mock_proc
            with patch.object(OpenCodeClient, "health_check", new_callable=AsyncMock, return_value=True):
                manager = OpenCodeProcessManager()
                client = await manager.start(port=4096, cwd="/tmp")
                await client.close()

        # Simulate process having exited
        mock_proc.returncode = 1
        running = manager.is_running()
        assert running is False
