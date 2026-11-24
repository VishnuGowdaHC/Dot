"""
Integration tests for agent-browser resolution and parameter normalization.
Verifies selector resolution, key mappings, and tool alias definitions.
"""

import sys
from pathlib import Path

# Add backend directory to module search path.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import unittest
from dot.mcp.client import (
    TOOL_ALIASES,
    KEY_MAP,
    resolve_browser_selector,
)
from dot.mcp.registry import ALLOWED_BROWSER_TOOLS, BROWSER_TOOL_DESCRIPTIONS
from dot.core.parser import heal_truncated_json, extract_json, parse_agent_step


class TestAgentBrowserIntegration(unittest.TestCase):
    """Verifies selector resolution and tool compatibility."""

    def setUp(self):
        self.mock_refs = {
            "e1": {"name": "Submit order", "role": "button"},
            "e2": {"name": "Customer name:", "role": "textbox"},
            "e3": {"name": "Telephone:", "role": "textbox"},
            "e4": {"name": "Learn more", "role": "link"},
            "e5": {"name": "Documentation", "role": "link"},
        }

    def test_ref_direct_and_numeric_resolution(self):
        """Verifies direct ref and numeric string normalization."""
        self.assertEqual(resolve_browser_selector({"selector": "@e2"}, refs=self.mock_refs), "@e2")
        self.assertEqual(resolve_browser_selector({"selector": "e2"}, refs=self.mock_refs), "@e2")
        self.assertEqual(resolve_browser_selector({"ref": "2"}, refs=self.mock_refs), "@e2")
        self.assertEqual(resolve_browser_selector({"selector": "3"}, refs=self.mock_refs), "@e3")

    def test_name_and_substring_resolution(self):
        """Verifies matching element by text or name."""
        self.assertEqual(resolve_browser_selector({"selector": "Submit order"}, refs=self.mock_refs), "@e1")
        self.assertEqual(resolve_browser_selector({"name": "Customer name"}, action_type="fill", refs=self.mock_refs), "@e2")
        self.assertEqual(resolve_browser_selector({"text": "Learn more"}, action_type="click", refs=self.mock_refs), "@e4")

    def test_ordinal_selector_resolution(self):
        """Verifies ordinal phrases like first link or first button."""
        self.assertEqual(resolve_browser_selector({"selector": "first link"}, action_type="click", refs=self.mock_refs), "@e4")
        self.assertEqual(resolve_browser_selector({"selector": "second link"}, action_type="click", refs=self.mock_refs), "@e5")
        self.assertEqual(resolve_browser_selector({"selector": "first button"}, action_type="click", refs=self.mock_refs), "@e1")
        self.assertEqual(resolve_browser_selector({"selector": "first textbox"}, action_type="fill", refs=self.mock_refs), "@e2")

    def test_css_selector_preservation(self):
        """Verifies standard CSS selectors pass without alteration."""
        self.assertEqual(resolve_browser_selector({"selector": "#submit-btn"}, refs=self.mock_refs), "#submit-btn")
        self.assertEqual(resolve_browser_selector({"selector": ".btn-primary"}, refs=self.mock_refs), ".btn-primary")
        self.assertEqual(resolve_browser_selector({"selector": "input[type='text']"}, refs=self.mock_refs), "input[type='text']")

    def test_tool_aliases_and_registry_whitelisting(self):
        """Verifies that press, fill, click, and tab close tools exist."""
        self.assertIn("browser_press", ALLOWED_BROWSER_TOOLS)
        self.assertIn("browser_tab_close", ALLOWED_BROWSER_TOOLS)
        self.assertEqual(TOOL_ALIASES.get("browser_press"), "agent_browser_press")
        self.assertEqual(TOOL_ALIASES.get("browser_press_key"), "agent_browser_press")
        self.assertEqual(TOOL_ALIASES.get("browser_tab_close"), "agent_browser_tab_close")
        self.assertEqual(TOOL_ALIASES.get("browser_click"), "agent_browser_click")
        self.assertEqual(TOOL_ALIASES.get("browser_fill"), "agent_browser_fill")
        self.assertEqual(TOOL_ALIASES.get("browser_extract_text"), "agent_browser_read")
        self.assertEqual(TOOL_ALIASES.get("browser_read"), "agent_browser_read")

    def test_key_map_normalizations(self):
        """Verifies case normalization for common keyboard keys."""
        self.assertEqual(KEY_MAP.get("enter"), "Enter")
        self.assertEqual(KEY_MAP.get("tab"), "Tab")
        self.assertEqual(KEY_MAP.get("escape"), "Escape")
        self.assertEqual(KEY_MAP.get("esc"), "Escape")
        self.assertEqual(KEY_MAP.get("control+a"), "Control+a")
        self.assertEqual(KEY_MAP.get("ctrl+a"), "Control+a")
        self.assertEqual(KEY_MAP.get("control+z"), "Control+z")
        self.assertEqual(KEY_MAP.get("backspace"), "Backspace")

    def test_heal_truncated_json(self):
        """Verifies that truncated JSON strings and objects heal into valid JSON."""
        # Unclosed string inside nested object
        raw = '{"thought": "Writing code", "action": "Tool-exec", "payload": {"name": "browser_fill", "args": {"text": "def bubble_sort(arr):\\n    if arr[j] > arr[j+1]'
        healed = heal_truncated_json(raw)
        step = parse_agent_step(healed)
        self.assertEqual(step.action, "Tool-exec")
        self.assertEqual(step.tool_name, "browser_fill")
        self.assertTrue(step.tool_args.get("text", "").startswith("def bubble_sort"))

        # Incomplete markdown fenced code block
        raw_fence = '```json\n{"thought": "Evaluating output", "action": "Final", "final_answer": "Done testing'
        extracted = extract_json(raw_fence)
        self.assertIsNotNone(extracted)
        step_fence = parse_agent_step(extracted)
        self.assertEqual(step_fence.action, "Final")
        self.assertEqual(step_fence.final_answer, "Done testing")


if __name__ == "__main__":
    unittest.main()

