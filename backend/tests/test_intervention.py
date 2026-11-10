"""
Unit tests for the human intervention coordinator.
Complies with ASD-STE100 technical writing standards.
"""

import sys
import json
from pathlib import Path

# Add backend directory to module search path.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import unittest
from unittest.mock import patch, AsyncMock

from dot.sandbox.intervention import InterventionManager


class TestInterventionManager(unittest.IsolatedAsyncioTestCase):
    """Test suite for human intervention pause and resume states."""

    @patch("dot.sandbox.intervention.pause_sandbox")
    @patch("dot.sandbox.intervention.unpause_sandbox")
    async def test_intervention_pause_and_resolve(self, mock_unpause, mock_pause):
        """Verifies container freeze, WebSocket notification, and resolution resume."""
        mgr = InterventionManager()
        mock_ws = AsyncMock()

        async def auto_resolve():
            import asyncio
            await asyncio.sleep(0.05)
            self.assertTrue(mgr.is_paused)
            self.assertEqual(mgr.pause_reason, "Test security check")
            mgr.submit_resolution("User confirmed command.")

        import asyncio
        asyncio.create_task(auto_resolve())

        feedback = await mgr.request_intervention(
            reason="Test security check",
            command="rm -rf /workspace/test",
            websocket=mock_ws
        )

        self.assertEqual(feedback, "User confirmed command.")
        self.assertFalse(mgr.is_paused)
        mock_pause.assert_called_once()
        mock_unpause.assert_called_once()
        mock_ws.send_text.assert_called_once()
        sent_data = json.loads(mock_ws.send_text.call_args[0][0])
        self.assertEqual(sent_data["type"], "intervention_required")
        self.assertEqual(sent_data["data"]["reason"], "Test security check")


if __name__ == "__main__":
    unittest.main()

