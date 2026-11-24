"""
Unit tests for the sandbox command executor and browser helpers.
Complies with ASD-STE100 technical writing standards.
"""

import asyncio
import sys
from pathlib import Path

# Add backend directory to module search path.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import unittest
from unittest.mock import patch, AsyncMock, MagicMock

from dot.sandbox.executor import exec_in_sandbox
from dot.sandbox.browser import sandboxed_navigate_and_extract, sandboxed_screenshot


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
        """Verifies successful command execution, timeout wrapper, and streaming."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.stdout.readline = AsyncMock(side_effect=[b"line 1\n", b"line 2\n", b""])
        mock_proc.stderr.readline = AsyncMock(side_effect=[b""])
        mock_proc.wait = AsyncMock(return_value=0)
        mock_exec.return_value = mock_proc

        streamed_chunks = []
        code, out = await exec_in_sandbox(
            "echo multi",
            timeout=30.0,
            stream_callback=lambda chunk: streamed_chunks.append(chunk),
        )

        self.assertEqual(code, 0)
        self.assertIn("line 1", out)
        self.assertIn("line 2", out)
        self.assertEqual(len(streamed_chunks), 2)

        cmd_args = mock_exec.call_args[0]
        self.assertIn("timeout", cmd_args)
        self.assertIn("30s", cmd_args)

    @patch("dot.sandbox.executor.ensure_sandbox_ready", return_value=True)
    @patch("asyncio.create_subprocess_exec")
    async def test_exec_timeout_kills_and_waits(self, mock_exec, mock_ready):
        """Verifies host timeout kills and awaits the subprocess without pkill."""
        mock_proc = AsyncMock()
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock(return_value=-9)

        async def hang_readline():
            await asyncio.sleep(1.0)
            return b""

        mock_proc.stdout.readline = hang_readline
        mock_proc.stderr.readline = hang_readline
        mock_exec.return_value = mock_proc

        async def fake_wait_for(aw, timeout):
            aw.cancel()
            try:
                await aw
            except asyncio.CancelledError:
                pass
            raise asyncio.TimeoutError

        with patch("dot.sandbox.executor.asyncio.wait_for", side_effect=fake_wait_for):
            code, out = await exec_in_sandbox("sleep 60", timeout=1.0)

        self.assertEqual(code, -1)
        self.assertIn("timed out", out)
        mock_proc.kill.assert_called_once()
        mock_proc.wait.assert_awaited_once()
        self.assertEqual(mock_exec.call_count, 1)

    @patch("dot.sandbox.executor.pause_sandbox", new_callable=AsyncMock)
    @patch("dot.sandbox.executor.ensure_sandbox_ready", return_value=True)
    @patch("asyncio.create_subprocess_exec")
    async def test_exec_restores_intervention_pause(self, mock_exec, mock_ready, mock_pause):
        """Verifies that intervention pause state is restored after CLI execution."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.stdout.readline = AsyncMock(side_effect=[b"ok\n", b""])
        mock_proc.stderr.readline = AsyncMock(side_effect=[b""])
        mock_proc.wait = AsyncMock(return_value=0)
        mock_exec.return_value = mock_proc

        mock_mgr = MagicMock(is_paused=True)
        with patch("dot.sandbox.executor.get_intervention_manager", return_value=mock_mgr):
            code, _ = await exec_in_sandbox("ls")

        self.assertEqual(code, 0)
        mock_pause.assert_awaited_once()

    @patch("dot.sandbox.browser.exec_in_sandbox", new_callable=AsyncMock)
    async def test_browser_quotes_malicious_url(self, mock_exec):
        """Verifies that browser URLs are shell-quoted to prevent injection."""
        mock_exec.return_value = (0, "page text")
        malicious_url = 'https://example.com/"; touch /tmp/pwned #'

        result = await sandboxed_navigate_and_extract(malicious_url)

        self.assertEqual(result, "page text")
        called_cmd = mock_exec.call_args[0][0]
        self.assertIn("'https://example.com/\"; touch /tmp/pwned #'", called_cmd)

    @patch("dot.sandbox.browser.exec_in_sandbox", new_callable=AsyncMock)
    async def test_browser_screenshot_sanitizes_path(self, mock_exec):
        """Verifies that screenshot output_name strips directory traversal."""
        mock_exec.return_value = (0, "")

        result = await sandboxed_screenshot("https://example.com", "../../etc/evil.png")

        self.assertEqual(result, "Screenshot saved to /workspace/evil.png")
        called_cmd = mock_exec.call_args[0][0]
        self.assertIn("/workspace/evil.png", called_cmd)
        self.assertNotIn("..", called_cmd)


if __name__ == "__main__":
    unittest.main()
