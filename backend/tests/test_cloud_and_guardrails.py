"""
Unit tests for cloud endpoints and destructive action guardrails.
Complies with ASD-STE100 technical writing standards.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure backend root is on sys.path.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from dot.config.settings import get_allowed_workspace, set_allowed_workspace
from dot.core.guardrails import check_destructive_action
from dot.memory.rolling_memory import get_rolling_memory


class TestCloudAndGuardrails(unittest.IsolatedAsyncioTestCase):
    """Validates destructive action guardrails and cloud endpoints."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = os.path.join(self.temp_dir.name, "safe_zone")
        os.makedirs(self.workspace, exist_ok=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_allowed_workspace_settings(self):
        """Verifies that allowed workspace updates correctly."""
        original = get_allowed_workspace()
        try:
            set_allowed_workspace(self.workspace)
            self.assertEqual(get_allowed_workspace(), self.workspace)
        finally:
            set_allowed_workspace(original)

    def test_destructive_command_blocked_outside_workspace(self):
        """Verifies that destructive actions outside allowed workspace fail."""
        outside_file = os.path.join(self.temp_dir.name, "system32", "critical.dll")

        with patch("dot.config.settings.get_allowed_workspace", return_value=self.workspace):
            err1 = check_destructive_action("delete_file", {"path": outside_file})
            self.assertIsNotNone(err1)
            self.assertIn("Guardrail Blocked", err1)

            err2 = check_destructive_action("sandbox_exec", {"cmd": f"rm -rf {outside_file}"})
            self.assertIsNotNone(err2)
            self.assertIn("Guardrail Blocked", err2)

    def test_destructive_command_blocked_on_workspace_root(self):
        """Verifies that deleting the workspace root is forbidden."""
        with patch("dot.config.settings.get_allowed_workspace", return_value=self.workspace):
            err = check_destructive_action("delete_file", {"path": self.workspace})
            self.assertIsNotNone(err)
            self.assertIn("forbidden", err.lower())

    def test_destructive_command_allowed_inside_workspace(self):
        """Verifies that deleting a file inside the allowed workspace succeeds."""
        inside_file = os.path.join(self.workspace, "temp.log")

        with patch("dot.config.settings.get_allowed_workspace", return_value=self.workspace):
            err = check_destructive_action("delete_file", {"path": inside_file})
            self.assertIsNone(err)

    def test_process_termination_requires_confirmation(self):
        """Verifies that process termination actions require confirmation."""
        err = check_destructive_action("os_manage_process", {"action": "kill", "pid": 1234})
        self.assertIsNotNone(err)
        self.assertIn("confirmation", err.lower())

    def test_rolling_memory_clear(self):
        """Verifies that clearing rolling memory resets all state."""
        rolling_mem = get_rolling_memory()
        rolling_mem.set_goal("Test task")
        rolling_mem.add_step("browser_open", "Page loaded", exit_code=0)
        rolling_mem.add_error("Network timeout")
        rolling_mem.register_file("script.py")

        self.assertEqual(rolling_mem.goal, "Test task")
        self.assertGreater(len(rolling_mem.completed_steps), 0)

        rolling_mem.clear()

        self.assertEqual(rolling_mem.goal, "")
        self.assertEqual(len(rolling_mem.completed_steps), 0)
        self.assertEqual(len(rolling_mem.known_errors), 0)
        self.assertEqual(len(rolling_mem.created_files), 0)

    async def test_cloud_test_missing_api_key(self):
        """Verifies that test connection returns an error when api key is empty."""
        from server import app
        from httpx import AsyncClient, ASGITransport

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/cloud/test", json={"api_key": ""})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertFalse(data["success"])
            self.assertIn("API key is required", data["error"])

    async def test_clear_chat_endpoint(self):
        """Verifies that POST /api/chat/clear returns a success status."""
        from server import app
        from httpx import AsyncClient, ASGITransport

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/chat/clear")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["status"], "ok")


if __name__ == "__main__":
    unittest.main()
