"""
Unit tests for the sandbox command executor.
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

from dot.sandbox.executor import exec_in_sandbox


class TestSandboxExecutor(unittest.IsolatedAsyncioTestCase):
    """Test suite for sandboxed command execution."""

    @patch("dot.sandbox.executor.ensure_sandbox_ready", return_value=False)
    async def test_exec_fails_when_sandbox_not_ready(self, mock_ready):
        """Verifies clean failure message when sandbox container is unavailable."""
        code, out = await exec_in_sandbox("echo test")
        self.assertEqual(code, -1)
        self.assertIn("not available", out)

    @patch("dot.sandbox.executor.ensure_sandbox_ready", return_value=True)
    @patch("asyncio.create_subprocess_exec")
    async def test_exec_success_streaming(self, mock_exec, mock_ready):
        """Verifies successful command execution and output capture."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.stdout.readline = AsyncMock(side_effect=[b"line 1\n", b"line 2\n", b""])
        mock_proc.stderr.readline = AsyncMock(side_effect=[b""])
        mock_proc.wait = AsyncMock(return_value=0)
        mock_exec.return_value = mock_proc

        streamed_chunks = []
        code, out = await exec_in_sandbox(
            "echo multi",
            stream_callback=lambda chunk: streamed_chunks.append(chunk)
        )

        self.assertEqual(code, 0)
        self.assertIn("line 1", out)
        self.assertIn("line 2", out)
        self.assertEqual(len(streamed_chunks), 2)


if __name__ == "__main__":
    unittest.main()

