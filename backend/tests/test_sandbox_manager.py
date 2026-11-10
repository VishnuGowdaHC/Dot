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
from unittest.mock import patch, AsyncMock, MagicMock

from dot.sandbox.manager import (
    is_docker_available,
    is_image_present,
    is_sandbox_running,
    is_sandbox_paused,
    start_sandbox,
    stop_sandbox,
    pause_sandbox,
    unpause_sandbox,
    ensure_sandbox_ready,
    MAX_MEMORY,
    MAX_CPUS,
    CONTAINER_NAME,
)


class TestSandboxManager(unittest.IsolatedAsyncioTestCase):
    """Test suite for Docker sandbox container management."""

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
        """Verifies that start_sandbox applies memory and CPU caps."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (b"", b"")
        mock_exec.return_value = mock_proc

        started = await start_sandbox()
        self.assertTrue(started)

        # Inspect commands passed to create_subprocess_exec
        called_args_list = [call[0] for call in mock_exec.call_args_list]
        run_calls = [args for args in called_args_list if "run" in args]
        self.assertTrue(len(run_calls) > 0)
        run_args = run_calls[0]

        self.assertIn(f"--memory={MAX_MEMORY}", run_args)
        self.assertIn(f"--cpus={MAX_CPUS}", run_args)
        self.assertIn("--init", run_args)
        self.assertIn(CONTAINER_NAME, run_args)

    @patch("asyncio.create_subprocess_exec")
    async def test_pause_and_unpause_sandbox(self, mock_exec):
        """Verifies pause and unpause command dispatch."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        paused = await pause_sandbox()
        self.assertTrue(paused)

        unpaused = await unpause_sandbox()
        self.assertTrue(unpaused)

    @patch("asyncio.create_subprocess_exec")
    async def test_stop_sandbox(self, mock_exec):
        """Verifies stop_sandbox removes the container."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        stopped = await stop_sandbox()
        self.assertTrue(stopped)


if __name__ == "__main__":
    unittest.main()

