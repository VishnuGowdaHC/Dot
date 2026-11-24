"""
Unit tests for the Docker sandbox container manager.
Complies with ASD-STE100 technical writing standards.
"""

import sys
from pathlib import Path

# Add backend directory to module search path.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import unittest
from unittest.mock import patch, AsyncMock

from dot.sandbox.manager import (
    is_docker_available,
    is_sandbox_running,
    start_sandbox,
    stop_sandbox,
    pause_sandbox,
    unpause_sandbox,
    ensure_sandbox_ready,
    invalidate_sandbox_cache,
    MAX_MEMORY,
    MAX_CPUS,
    CONTAINER_NAME,
)


class TestSandboxManager(unittest.IsolatedAsyncioTestCase):
    """Test suite for Docker sandbox container management."""

    def setUp(self):
        invalidate_sandbox_cache()

    @patch("asyncio.create_subprocess_exec")
    async def test_is_docker_available_true(self, mock_exec):
        """Verifies true return when docker info succeeds."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        result = await is_docker_available()
        self.assertTrue(result)

    @patch("asyncio.create_subprocess_exec")
    async def test_is_docker_available_false(self, mock_exec):
        """Verifies false return when docker info raises exception."""
        mock_exec.side_effect = Exception("Docker daemon unreachable")

        result = await is_docker_available()
        self.assertFalse(result)

    @patch("asyncio.create_subprocess_exec")
    async def test_is_sandbox_running(self, mock_exec):
        """Verifies container status detection via docker ps."""
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"c123456\n", b"")
        mock_exec.return_value = mock_proc

        result = await is_sandbox_running()
        self.assertTrue(result)

    @patch("dot.sandbox.manager.is_sandbox_running", return_value=False)
    @patch("dot.sandbox.manager.is_image_present", return_value=True)
    @patch("asyncio.create_subprocess_exec")
    async def test_start_sandbox_invokes_resource_limits(self, mock_exec, mock_img, mock_run):
        """Verifies that start_sandbox applies resource and security caps."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (b"", b"")
        mock_exec.return_value = mock_proc

        started = await start_sandbox()
        self.assertTrue(started)

        called_args_list = [call[0] for call in mock_exec.call_args_list]
        run_calls = [args for args in called_args_list if "run" in args]
        self.assertTrue(len(run_calls) > 0)
        run_args = run_calls[0]

        self.assertIn(f"--memory={MAX_MEMORY}", run_args)
        self.assertIn(f"--cpus={MAX_CPUS}", run_args)
        self.assertIn("--init", run_args)
        self.assertIn("--cap-drop=ALL", run_args)
        self.assertIn("--security-opt=no-new-privileges:true", run_args)
        self.assertIn(CONTAINER_NAME, run_args)

    @patch("dot.sandbox.manager.is_sandbox_running", return_value=False)
    @patch("dot.sandbox.manager.is_image_present", return_value=True)
    @patch("asyncio.create_subprocess_exec")
    async def test_ensure_sandbox_ready_uses_cache(self, mock_exec, mock_img, mock_run):
        """Verifies that ensure_sandbox_ready skips CLI probes when cached as running."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (b"", b"")
        mock_exec.return_value = mock_proc

        started = await start_sandbox()
        self.assertTrue(started)
        mock_exec.reset_mock()

        ready = await ensure_sandbox_ready()
        self.assertTrue(ready)
        mock_exec.assert_not_called()

    @patch("asyncio.create_subprocess_exec")
    async def test_pause_and_unpause_sandbox(self, mock_exec):
        """Verifies pause and unpause command dispatch using communicate."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (b"", b"")
        mock_exec.return_value = mock_proc

        paused = await pause_sandbox()
        self.assertTrue(paused)

        unpaused = await unpause_sandbox()
        self.assertTrue(unpaused)
        self.assertEqual(mock_proc.communicate.call_count, 2)

    @patch("asyncio.create_subprocess_exec")
    async def test_stop_sandbox(self, mock_exec):
        """Verifies stop_sandbox removes the container."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        stopped = await stop_sandbox()
        self.assertTrue(stopped)

    @patch("asyncio.create_subprocess_exec")
    async def test_stop_sandbox_failure_returns_false(self, mock_exec):
        """Verifies stop_sandbox returns false when docker rm fails."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_exec.return_value = mock_proc

        stopped = await stop_sandbox()
        self.assertFalse(stopped)


if __name__ == "__main__":
    unittest.main()
