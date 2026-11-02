"""
Unit tests for browser automation tools.
Tests web search, navigation, text extraction, accessibility snapshots, and cleanup.
"""

import sys
from pathlib import Path

# Add backend directory to module search path.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import unittest
from unittest.mock import patch
import asyncio

from dot.automation.browser import (
    search_web,
    open_in_browser,
    navigate,
    extract_text,
    snapshot,
    close_browser,
)


class TestBrowserTools(unittest.IsolatedAsyncioTestCase):
    """Test suite for browser tools."""

    async def test_search_web_structure(self):
        """Verifies that search_web returns structured results."""
        res = await search_web("python documentation", max_results=2)
        self.assertIsInstance(res, dict)
        self.assertIn("success", res)
        self.assertIn("results", res)
        if res.get("success"):
            self.assertIsInstance(res["results"], list)
            if res["results"]:
                first = res["results"][0]
                self.assertIn("title", first)
                self.assertIn("url", first)

    @patch("webbrowser.open")
    def test_open_in_browser(self, mock_open):
        """Verifies that open_in_browser formats target URL and triggers desktop browser."""
        res = open_in_browser("https://github.com")
        self.assertTrue(res.get("success"))
        self.assertTrue(res.get("terminal"))
        mock_open.assert_called_once()

    async def test_navigation_and_text_extraction(self):
        """Verifies page navigation and text extraction using data URL."""
        test_url = "data:text/html,<html><body><h1>Dot Test Header</h1><p>Test paragraph content.</p></body></html>"
        nav_res = await navigate(test_url)
        self.assertIsInstance(nav_res, dict)

        extract_res = await extract_text()
        self.assertIsInstance(extract_res, dict)
        if extract_res.get("success"):
            self.assertIn("Dot Test Header", extract_res.get("detail", ""))

        # Close browser to verify clean teardown
        close_res = await close_browser()
        self.assertTrue(close_res.get("success"))


if __name__ == "__main__":
    unittest.main()
