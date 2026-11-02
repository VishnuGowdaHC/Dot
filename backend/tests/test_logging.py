"""
Unit tests for context logging and tool execution telemetry.
Tests output formats for agent_context.log and agent_debug.log.
"""

import sys
from pathlib import Path

# Add backend directory to module search path.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import unittest
import os
import uuid

from dot.config.paths import CONTEXT_LOG_FILE, DEBUG_LOG_FILE
from dot.core.utils import (
    log_agent_context,
    log_tool_execution,
    auto_format_observation,
    dump_observation,
)


class TestLogging(unittest.TestCase):
    """Test suite for context and debug logging."""

    def test_log_agent_context_writes_file(self):
        """Verifies that log_agent_context appends formatted turn context to agent_context.log."""
        unique_marker = f"marker_{uuid.uuid4().hex[:8]}"
        query = f"Test query {unique_marker}"
        system_prompt = "You are a test assistant."
        history_parts = [
            {"role": "user", "text": query, "pinned": True},
            {"role": "model", "text": "Test model step.", "pinned": False},
        ]

        log_agent_context(
            query=query,
            step=1,
            history_parts=history_parts,
            system_prompt=system_prompt,
            total_tokens=150,
            context_limit=8192,
        )

        self.assertTrue(os.path.exists(CONTEXT_LOG_FILE))
        with open(CONTEXT_LOG_FILE, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn(unique_marker, content)
        self.assertIn("--- SYSTEM PROMPT ---", content)
        self.assertIn("--- CONTEXT HISTORY ENTRIES ---", content)
        self.assertIn("Role: user", content)
        self.assertIn("TOKENS: 150/8192", content)

    def test_log_tool_execution_writes_file(self):
        """Verifies that log_tool_execution appends telemetry to agent_debug.log."""
        unique_tool = f"custom_tool_{uuid.uuid4().hex[:6]}"
        args = {"target": "test_folder", "count": 5}
        obs = {"status": "success", "items": ["file1.txt", "file2.txt"]}

        log_tool_execution(
            step=2,
            service="test_service",
            tool_name=unique_tool,
            tool_args=args,
            observation=obs,
            duration_sec=0.15,
        )

        self.assertTrue(os.path.exists(DEBUG_LOG_FILE))
        with open(DEBUG_LOG_FILE, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn(unique_tool, content)
        self.assertIn("Duration: 0.15s", content)
        self.assertIn("test_folder", content)

    def test_auto_format_observation_dict(self):
        """Verifies observation dictionary formatting into compact text."""
        data = {"status": "ok", "count": 42}
        formatted = auto_format_observation(data)
        self.assertIn("status: ok", formatted)
        self.assertIn("count: 42", formatted)

    def test_dump_observation_creates_file(self):
        """Verifies that dump_observation stores raw debug json file."""
        obs_path = dump_observation({"test_key": "test_val"}, step=1, action="test_action")
        self.assertTrue(os.path.exists(obs_path))
        if os.path.exists(obs_path):
            os.remove(obs_path)


if __name__ == "__main__":
    unittest.main()

