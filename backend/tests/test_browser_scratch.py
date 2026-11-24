"""
Unit tests for browser scratch buffer, element extraction, and disambiguated probing.
Follows ASD-STE100 guidelines.
"""

import os
import tempfile
import unittest
from pathlib import Path

from dot.automation.browser import (
    _dump_to_scratch,
    _search_scratch_elements,
    _build_compact_manifest,
)


class TestBrowserScratch(unittest.TestCase):
    """Verifies scratch element storage and disambiguation logic."""

    def setUp(self):
        """Prepare sample element fixtures representing a complex multi-question quiz."""
        self.sample_elements = [
            {
                "ref": "@e1",
                "tag": "h1",
                "role": "heading",
                "text": "Python Certification Quiz",
                "section": "Header",
                "coords": {"x": 100, "y": 50, "width": 400, "height": 40},
            },
            {
                "ref": "@e2",
                "tag": "h2",
                "role": "heading",
                "text": "Question 1: Which keyword defines a function?",
                "section": "Question 1",
                "coords": {"x": 100, "y": 120, "width": 500, "height": 30},
            },
            {
                "ref": "@e3",
                "tag": "input",
                "role": "radio",
                "type": "radio",
                "text": "func",
                "section": "Question 1",
                "coords": {"x": 120, "y": 160, "width": 20, "height": 20},
            },
            {
                "ref": "@e4",
                "tag": "input",
                "role": "radio",
                "type": "radio",
                "text": "def",
                "section": "Question 1",
                "coords": {"x": 120, "y": 190, "width": 20, "height": 20},
            },
            {
                "ref": "@e5",
                "tag": "h2",
                "role": "heading",
                "text": "Question 2: Which keyword defines a class?",
                "section": "Question 2",
                "coords": {"x": 100, "y": 240, "width": 500, "height": 30},
            },
            {
                "ref": "@e6",
                "tag": "input",
                "role": "radio",
                "type": "radio",
                "text": "def",
                "section": "Question 2",
                "coords": {"x": 120, "y": 280, "width": 20, "height": 20},
            },
            {
                "ref": "@e7",
                "tag": "input",
                "role": "radio",
                "type": "radio",
                "text": "class",
                "section": "Question 2",
                "coords": {"x": 120, "y": 310, "width": 20, "height": 20},
            },
            {
                "ref": "@e8",
                "tag": "input",
                "role": "textbox",
                "type": "text",
                "text": "",
                "name": "Search quiz topics",
                "section": "Search Bar",
                "coords": {"x": 600, "y": 50, "width": 200, "height": 30},
            },
            {
                "ref": "@e9",
                "tag": "button",
                "role": "button",
                "text": "Search",
                "section": "Search Bar",
                "coords": {"x": 810, "y": 50, "width": 80, "height": 30},
            },
            {
                "ref": "@e10",
                "tag": "button",
                "role": "button",
                "text": "Next Question",
                "section": "Navigation",
                "coords": {"x": 100, "y": 380, "width": 120, "height": 35},
            },
        ]

    def test_dump_to_scratch_writes_valid_markdown(self):
        """Verify scratch buffer correctly serializes elements to file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            scratch_file = Path(tmp_dir) / "scratch_page.md"
            out_path = _dump_to_scratch(self.sample_elements, scratch_file)
            self.assertTrue(os.path.exists(out_path))

            content = scratch_file.read_text(encoding="utf-8")
            self.assertIn("# Active Webpage Element Scratchpad", content)
            self.assertIn("@e4", content)
            self.assertIn("Question 1", content)
            self.assertIn("def", content)

    def test_search_scratch_elements_disambiguates_by_section(self):
        """Verify identical text across different questions is disambiguated by section."""
        # Searching 'def' without section hint returns two matches (@e4 in Q1 and @e6 in Q2)
        all_matches = _search_scratch_elements(
            query="def",
            elements=self.sample_elements,
        )
        self.assertEqual(len(all_matches), 2)
        self.assertEqual(all_matches[0]["ref"], "@e4")
        self.assertEqual(all_matches[1]["ref"], "@e6")

        # Disambiguate for Question 2 only
        q2_matches = _search_scratch_elements(
            query="def",
            elements=self.sample_elements,
            section_hint="Question 2",
        )
        self.assertEqual(len(q2_matches), 1)
        self.assertEqual(q2_matches[0]["ref"], "@e6")
        self.assertEqual(q2_matches[0]["section"], "Question 2")

    def test_search_scratch_elements_disambiguates_by_tag_type(self):
        """Verify collisions between inputs and buttons are resolved by tag_type."""
        # In search bar: input named 'Search' vs button named 'Search'
        btn_matches = _search_scratch_elements(
            query="Search",
            elements=self.sample_elements,
            tag_type="button",
        )
        self.assertEqual(len(btn_matches), 1)
        self.assertEqual(btn_matches[0]["ref"], "@e9")
        self.assertEqual(btn_matches[0]["tag"], "button")

        input_matches = _search_scratch_elements(
            query="Search",
            elements=self.sample_elements,
            tag_type="input",
        )
        self.assertEqual(len(input_matches), 1)
        self.assertEqual(input_matches[0]["ref"], "@e8")
        self.assertEqual(input_matches[0]["tag"], "input")

    def test_build_compact_manifest_limits_tokens(self):
        """Verify compact manifest remains small and token-efficient."""
        manifest = _build_compact_manifest(
            title="Python Certification Quiz",
            url="https://quiz.example.com",
            elements=self.sample_elements,
            max_elements=15,
        )
        self.assertIn("Python Certification Quiz", manifest)
        self.assertIn("[@e4] radio 'def'", manifest)
        self.assertIn("[@e10] button 'Next Question'", manifest)
        # Manifest text should stay well under 1200 characters (~300 tokens)
        self.assertLess(len(manifest), 1200)


if __name__ == "__main__":
    unittest.main()
