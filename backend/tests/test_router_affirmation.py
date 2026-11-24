"""
Unit tests for Intent Router affirmation handling and goal continuation.
Verifies that confirmations like 'ok' resume active goals instead of resetting context.
Complies with ASD-STE100 technical writing rules.
"""

import unittest
import asyncio
from unittest.mock import AsyncMock, patch

from dot.core.router import is_affirmation_query, resolve_continuation_query
from dot.memory.rolling_memory import get_rolling_memory


class TestRouterAffirmation(unittest.TestCase):
    """Test suite for intent router continuation on affirmative user inputs."""

    def setUp(self):
        self.rolling_mem = get_rolling_memory()
        self.rolling_mem.clear()

    def test_detects_affirmation_queries(self):
        """Verifies detection of short user affirmations."""
        affirmations = ["ok", "okay", "yes", "sure", "proceed", "go ahead", "do it", "OK", "yes please"]
        for word in affirmations:
            self.assertTrue(is_affirmation_query(word), f"Failed to detect affirmation: {word}")

    def test_rejects_non_affirmation_queries(self):
        """Verifies rejection of non-affirmation queries."""
        non_affirmations = ["what is the weather", "open youtube", "no cancel it", "ok let me check", "search github"]
        for phrase in non_affirmations:
            self.assertFalse(is_affirmation_query(phrase), f"Incorrectly marked as affirmation: {phrase}")

    def test_resolves_continuation_when_goal_is_active(self):
        """Verifies query expansion when an uncompleted goal exists in rolling memory."""
        self.rolling_mem.set_goal("Find the top story on Hacker News and paste it into notepad")
        self.rolling_mem.add_step("browser_navigate", "Navigated to Hacker News. Top story found.")

        expanded = resolve_continuation_query("ok", self.rolling_mem)
        self.assertIn("Hacker News", expanded)
        self.assertIn("paste it into notepad", expanded)

    def test_leaves_affirmation_unchanged_when_no_active_goal(self):
        """Verifies that plain affirmation returns original text when no goal is pending."""
        expanded = resolve_continuation_query("ok", self.rolling_mem)
        self.assertEqual(expanded, "ok")


if __name__ == "__main__":
    unittest.main()
