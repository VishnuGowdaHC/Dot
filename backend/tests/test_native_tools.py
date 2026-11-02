"""
Unit tests for native memory retrieval tools.
Tests active session transcript search and past session vector query tools.
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

from dot.config.paths import TRANSCRIPTS_DIR
from dot.memory.search import search_active_session, search_past_sessions
from dot.memory.collections.native_tools_collection import NATIVE_TOOLS


class TestNativeTools(unittest.TestCase):
    """Test suite for native memory search tools."""

    def test_native_tools_registration(self):
        """Verifies that native tools dictionary registers core lookup functions."""
        self.assertIn("search_active_session", NATIVE_TOOLS)
        self.assertIn("search_past_sessions", NATIVE_TOOLS)
        self.assertTrue(callable(NATIVE_TOOLS["search_active_session"]))
        self.assertTrue(callable(NATIVE_TOOLS["search_past_sessions"]))

    def test_search_active_session_nonexistent(self):
        """Verifies proper error handling when transcript file does not exist."""
        dummy_id = f"nonexistent_session_{uuid.uuid4().hex[:6]}"
        res = search_active_session("keyword", dummy_id)
        self.assertIn("does not exist", res)

    def test_search_active_session_with_content(self):
        """Verifies keyword lookup in active session transcript file."""
        test_id = f"test_active_session_{uuid.uuid4().hex[:6]}"
        test_file = TRANSCRIPTS_DIR / f"{test_id}.md"

        try:
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("User: How do I configure port 9222 for browser automation?\nAssistant: Use remote-debugging-port.")

            # Test matching keyword
            res_match = search_active_session("browser automation", test_id)
            self.assertIn("Past Memory Retrieved", res_match)
            self.assertIn("remote-debugging-port", res_match)

            # Test missing keyword
            res_no_match = search_active_session("quantum physics", test_id)
            self.assertIn("No matches found", res_no_match)

        finally:
            if os.path.exists(test_file):
                os.remove(test_file)

    def test_search_past_sessions_query(self):
        """Verifies vector search across past sessions returns formatted string."""
        res = search_past_sessions("test query", k=2)
        self.assertIsInstance(res, str)
        self.assertTrue(len(res) > 0)


if __name__ == "__main__":
    unittest.main()

