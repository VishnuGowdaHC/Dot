"""
Unit tests for thought headline sanitization and prompt constraints.
Complies with ASD-STE100 standards.
"""

import unittest
from dot.core.engine import format_thought_headline
from dot.core.prompts import (
    SYSTEM_PROMPT_2B,
    SYSTEM_PROMPT_BALANCED,
    SYSTEM_PROMPT_CLOUD,
)


class TestThoughtHeadline(unittest.TestCase):
    """Tests headline formatting and system prompt rules."""

    def test_sanitizes_persona_and_system_prompt_leaks(self) -> None:
        """Verify that persona and system prompt keywords are removed."""
        raw_thought = (
            "The user provided a simple greeting. I will respond with a witty "
            "and sarcastic greeting as per the persona."
        )
        headline = format_thought_headline(raw_thought)
        self.assertNotIn("persona", headline.lower())
        self.assertNotIn("sarcastic", headline.lower())
        self.assertNotIn("system prompt", headline.lower())
        self.assertTrue(len(headline) <= 45)

    def test_formats_tool_execution_headline(self) -> None:
        """Verify tool execution headlines format cleanly."""
        headline = format_thought_headline(
            thought=None,
            action="Tool-exec",
            tool_name="browser_search_web",
        )
        self.assertEqual(headline, "Executing Browser Search Web...")

    def test_formats_tool_discovery_headline(self) -> None:
        """Verify tool discovery headlines format cleanly."""
        headline = format_thought_headline(thought=None, action="Tool")
        self.assertEqual(headline, "Searching available tools...")

    def test_fallback_when_empty(self) -> None:
        """Verify fallback when thought is empty or None."""
        self.assertEqual(format_thought_headline(None), "Thinking...")
        self.assertEqual(format_thought_headline(""), "Thinking...")

    def test_truncates_long_thought(self) -> None:
        """Verify long thoughts are truncated to at most 45 characters."""
        long_thought = "Analyzing user intent and checking every available tool across all system services"
        headline = format_thought_headline(long_thought)
        self.assertTrue(len(headline) <= 45)
        self.assertTrue(headline.endswith("..."))

    def test_prompt_templates_contain_anti_leak_rules(self) -> None:
        """Verify all prompts forbid persona and instructions in thought."""
        for prompt in [SYSTEM_PROMPT_2B, SYSTEM_PROMPT_BALANCED, SYSTEM_PROMPT_CLOUD]:
            self.assertIn("NEVER", prompt)
            self.assertIn("thought", prompt)
            self.assertIn("2-5 word", prompt)


if __name__ == "__main__":
    unittest.main()
