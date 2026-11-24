"""
Unit tests for browser page reading, outline suppression, auto-retry on heading misses,
and primary heading alignment in clean_readable_text.
"""

import unittest
from unittest.mock import AsyncMock, patch

from dot.automation.browser import clean_readable_text
from dot.mcp.client import execute_mcp_tool


class TestPageReading(unittest.IsolatedAsyncioTestCase):
    """Test suite for full-text page reading and heading alignment."""

    async def test_browser_read_suppresses_outline_during_content_read(self):
        """Verifies that outline=True is forced to False so body text is not omitted."""
        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value="Full page body")

        args = {"outline": True, "url": "https://en.wikipedia.org/wiki/Andrew_Ng"}
        await execute_mcp_tool(mock_client, "browser", "browser_read", args)

        mock_client.call_tool.assert_called_once()
        passed_args = mock_client.call_tool.call_args[0][1]
        self.assertFalse(passed_args.get("outline"), "outline must be False for content reading")

    async def test_browser_read_auto_retries_on_no_matching_headings(self):
        """Verifies automatic recovery without filter when initial read returns No matching headings."""
        mock_client = AsyncMock()
        # First call with filter returns 'No matching headings'
        # Retry call without filter returns the full article
        mock_client.call_tool.side_effect = [
            "success: True\ndetail: No matching headings",
            "# Andrew Ng\nAndrew Yan-Tak Ng is a British-American computer scientist.",
        ]

        args = {"filter": "biography", "url": "https://en.wikipedia.org/wiki/Andrew_Ng"}
        res = await execute_mcp_tool(mock_client, "browser", "browser_read", args)

        self.assertEqual(mock_client.call_tool.call_count, 2)
        # Verify second call had filter removed
        retry_passed_args = mock_client.call_tool.call_args_list[1][0][1]
        self.assertNotIn("filter", retry_passed_args)
        self.assertIn("Andrew Yan-Tak Ng", res.get("detail", ""))

    def test_clean_readable_text_aligns_to_primary_heading(self):
        """Verifies that sidebar navigation links are stripped and extraction aligns to primary heading."""
        raw_text = (
            "Jump to content\n"
            "Main menu\n"
            "Navigation\n"
            "- Donate\n"
            "- Random article\n"
            "## Contents\n"
            "- 1 Early life\n"
            "- 2 Career\n\n"
            "# Andrew Ng\n"
            "Andrew Yan-Tak Ng (born 1976) is a computer scientist and machine learning pioneer.\n"
            "He co-founded Coursera and deeplearning.ai.\n"
        )
        cleaned = clean_readable_text(raw_text)

        self.assertNotIn("Jump to content", cleaned)
        self.assertNotIn("Main menu", cleaned)
        self.assertNotIn("Donate", cleaned)
        self.assertTrue(cleaned.startswith("# Andrew Ng"))
        self.assertIn("co-founded Coursera", cleaned)

    def test_clean_readable_text_honors_increased_char_limit(self):
        """Verifies that clean_readable_text preserves up to 4000 characters."""
        long_paragraph = "Andrew Ng is a prominent computer scientist. " * 75  # ~3375 chars
        raw_text = f"# Andrew Ng\n{long_paragraph}"
        cleaned = clean_readable_text(raw_text)

        self.assertGreater(len(cleaned), 3000)
        self.assertNotIn("...[truncated]", cleaned)


if __name__ == "__main__":
    unittest.main()
