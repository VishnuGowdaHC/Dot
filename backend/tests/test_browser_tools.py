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
import urllib.parse

from dot.automation.browser import (
    search_web,
    open_in_browser,
    navigate,
    extract_text,
    click,
    fill,
    snapshot,
    close_browser,
    _decode_ddg_url,
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
                self.assertIn("snippet", first)

    def test_decode_ddg_url(self):
        """Verifies DuckDuckGo redirect link unwrapping."""
        wrapped = "https://duckduckgo.com/l/?uddg=https%3A%2F%2Fen.wikipedia.org%2Fwiki%2FTest&rut=abc"
        decoded = _decode_ddg_url(wrapped)
        self.assertEqual(decoded, "https://en.wikipedia.org/wiki/Test")

        direct = "https://example.com/page"
        self.assertEqual(_decode_ddg_url(direct), direct)

    async def test_search_web_empty_query(self):
        """Verifies that empty search queries return clean failure dictionaries."""
        res = await search_web("   ")
        self.assertFalse(res.get("success"))
        self.assertEqual(res.get("results"), [])

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

    async def test_click_and_extract_by_selector(self):
        """Verifies clicking and extracting text using CSS selectors."""
        raw_html = (
            "<!DOCTYPE html><html><body>"
            "<a id='test-link' href='#target'>Click Me</a>"
            "<div id='target-content' style='display:none;'>Target Loaded</div>"
            "<script>"
            "document.getElementById('test-link').addEventListener('click', function(e) {"
            "  e.preventDefault();"
            "  document.getElementById('target-content').style.display = 'block';"
            "});"
            "</script>"
            "</body></html>"
        )
        data_url = f"data:text/html;charset=utf-8,{urllib.parse.quote(raw_html)}"
        await navigate(data_url)
        click_res = await click(selector="#test-link")
        self.assertTrue(click_res.get("success"))

        extract_res = await extract_text(selector="#target-content")
        self.assertTrue(extract_res.get("success"))
        self.assertIn("Target Loaded", extract_res.get("detail", ""))
        await close_browser()

    async def test_fill_and_click_with_roles(self):
        """Verifies form input fill and button click with ARIA roles."""
        raw_html = (
            "<!DOCTYPE html><html><body>"
            "<input type='text' placeholder='Search Query' id='query-input'>"
            "<button id='submit-btn'>Search</button>"
            "<p id='result' style='display:none;'></p>"
            "<script>"
            "document.getElementById('submit-btn').addEventListener('click', function(e) {"
            "  const val = document.getElementById('query-input').value;"
            "  const p = document.getElementById('result');"
            "  p.innerText = 'Searched: ' + val;"
            "  p.style.display = 'block';"
            "});"
            "</script>"
            "</body></html>"
        )
        data_url = f"data:text/html;charset=utf-8,{urllib.parse.quote(raw_html)}"
        await navigate(data_url)
        fill_res = await fill(text="playwright testing", role="textbox", name="Search Query")
        self.assertTrue(fill_res.get("success"))

        click_res = await click(role="button", name="Search")
        self.assertTrue(click_res.get("success"))

        extract_res = await extract_text(selector="#result")
        self.assertTrue(extract_res.get("success"))
        self.assertIn("Searched: playwright testing", extract_res.get("detail", ""))
        await close_browser()

    def test_parse_agent_browser_snapshot_and_manifest(self):
        """Verifies parsing of accessibility tree and compact manifest generation."""
        from dot.mcp.client import _parse_agent_browser_snapshot
        from dot.automation.browser import _build_compact_manifest, _search_scratch_elements, clean_readable_text

        sample_tree = (
            "- heading \"Python Quiz\" [level=1, ref=e54]\n"
            "- heading \"Question 1 of 25:\" [level=3, ref=e76]\n"
            "- paragraph \"What is a correct syntax to output Hello World in Python?\"\n"
            "- LabelText \"print(\\\"Hello World\\\")\" [@e159] clickable\n"
            "  - radio \"print(\\\"Hello World\\\")\" [checked=false, ref=e163]\n"
            "- button \"Next ❯\" [@e153]\n"
        )
        elements = _parse_agent_browser_snapshot(sample_tree)
        self.assertGreaterEqual(len(elements), 4)

        refs = [e["ref"] for e in elements if e.get("ref")]
        self.assertIn("@e54", refs)
        self.assertIn("@e76", refs)
        self.assertIn("@e163", refs)
        self.assertIn("@e153", refs)

        manifest = _build_compact_manifest("Python Quiz", "https://example.com/quiz", elements)
        self.assertIn("Python Quiz", manifest)
        self.assertIn("Question 1 of 25:", manifest)
        self.assertIn("@e163", manifest)
        self.assertIn("@e153", manifest)

        # Verify probe search
        matches = _search_scratch_elements("print", elements=elements)
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0]["ref"], "@e159")

        # Verify probe search with tag_type filter
        radio_matches = _search_scratch_elements("print", elements=elements, tag_type="radio")
        self.assertEqual(len(radio_matches), 1)
        self.assertEqual(radio_matches[0]["ref"], "@e163")

        # Verify text cleaning
        raw_markdown = (
            "Navbar Link 1\nNavbar Link 2\n"
            "# Python Quiz\n"
            "### Question 1 of 25:\n"
            "What is a correct syntax to output Hello World in Python?\n"
        )
        cleaned = clean_readable_text(raw_markdown)
        self.assertIn("Question 1 of 25:", cleaned)
        self.assertNotIn("Navbar Link 1", cleaned)

        # Verify Wikipedia boilerplate and MediaWiki template stripping
        wiki_raw = (
            "# Classroom of the Elite season 4\n"
            "1 language\n- Edit links\n- Tools\n- Download as PDF\n"
            "From Wikipedia, the free encyclopedia\n"
            "The fourth season premiered on April 1, 2026.\n"
            "{{cite web|title=Test|url=https://example.com}}\n"
        )
        wiki_cleaned = clean_readable_text(wiki_raw)
        self.assertIn("# Classroom of the Elite season 4", wiki_cleaned)
        self.assertIn("The fourth season premiered on April 1, 2026.", wiki_cleaned)
        self.assertNotIn("Download as PDF", wiki_cleaned)
        self.assertNotIn("{{cite web", wiki_cleaned)

    async def test_navigate_blocks_unsafe_schemes(self):
        """Verifies that unsafe URL schemes are rejected by navigate."""
        for bad_url in ("file:///C:/Windows/System32", "javascript:alert(1)"):
            res = await navigate(bad_url)
            self.assertFalse(res.get("success"))
            self.assertIn("Blocked unsafe URL scheme", res.get("error", ""))

    async def test_extract_text_with_at_ref_does_not_click_or_type(self):
        """Verifies that extract_text with an @eN selector reads text without clicking or typing."""
        raw_html = "<!DOCTYPE html><html><body><p>Visible Article Body</p></body></html>"
        data_url = f"data:text/html;charset=utf-8,{urllib.parse.quote(raw_html)}"
        await navigate(data_url)
        res = await extract_text(selector="@e1")
        self.assertTrue(res.get("success"))
        self.assertIn("Visible Article Body", res.get("detail", ""))
        self.assertNotIn("Filled", res.get("detail", ""))
        await close_browser()


if __name__ == "__main__":
    unittest.main()
