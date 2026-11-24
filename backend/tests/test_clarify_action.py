"""
Unit tests for Clarify action parsing and AgentStep validation.
Follows ASD-STE100 guidelines.
"""

import sys
from pathlib import Path

# Add backend directory to module search path.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import unittest
from dot.core.parser import AgentStep, parse_agent_step, extract_json


class TestClarifyAction(unittest.TestCase):
    """Verifies parsing and schema adherence of Clarify action."""

    def test_parse_clarify_with_choices(self):
        """Verify AgentStep properly validates Clarify action with option choices."""
        raw_json = """{
            "thought": "Question 3 is ambiguous and requires user preference.",
            "action": "Clarify",
            "question": "Which Python version should this test target?",
            "choices": ["Python 3.10", "Python 3.12", "Python 3.13"],
            "tool_service": null,
            "payload": {},
            "final_answer": null
        }"""
        step = parse_agent_step(raw_json)
        self.assertEqual(step.action, "Clarify")
        self.assertEqual(step.question, "Which Python version should this test target?")
        self.assertEqual(len(step.choices), 3)
        self.assertIn("Python 3.12", step.choices)

    def test_parse_clarify_with_dict_choices(self):
        """Verify choices given as dictionaries are normalized to strings."""
        raw_json = """{
            "thought": "User confirmation required.",
            "action": "Clarify",
            "question": "Proceed with operation?",
            "choices": [{"text": "Proceed"}, {"label": "Cancel"}],
            "tool_service": null,
            "payload": {},
            "final_answer": null
        }"""
        step = parse_agent_step(raw_json)
        self.assertEqual(step.action, "Clarify")
        self.assertEqual(step.choices, ["Proceed", "Cancel"])

    def test_parse_clarify_with_mixed_and_nested_choices(self):
        """Verify choices with mixed types and null values are cleaned."""
        raw_json = """{
            "thought": "Select preference.",
            "action": "Clarify",
            "question": "Choose mode:",
            "choices": ["Fast", {"value": "Accurate"}, null, "", {"name": "Default"}],
            "tool_service": null,
            "payload": {},
            "final_answer": null
        }"""
        step = parse_agent_step(raw_json)
        self.assertEqual(step.action, "Clarify")
        self.assertEqual(step.choices, ["Fast", "Accurate", "Default"])

    def test_parse_clarify_fallback_to_thought(self):
        """Verify Clarify without explicit question field extracts question from thought."""
        raw_json = """{
            "thought": "Please provide the verification code sent to your email.",
            "action": "Clarify",
            "tool_service": null,
            "payload": {},
            "final_answer": null
        }"""
        step = parse_agent_step(raw_json)
        self.assertEqual(step.action, "Clarify")
        self.assertTrue(step.question is not None and len(step.question) > 0)

    def test_backward_compatibility_tool_exec(self):
        """Verify existing Tool-exec action continues to parse accurately."""
        raw_json = """{
            "thought": "Clicking button option def.",
            "action": "Tool-exec",
            "tool_service": "browser",
            "payload": {"name": "browser_click", "args": {"selector": "@e4"}},
            "final_answer": null
        }"""
        step = parse_agent_step(raw_json)
        self.assertEqual(step.action, "Tool-exec")
        self.assertEqual(step.tool_name, "browser_click")
        self.assertEqual(step.tool_args.get("selector"), "@e4")

    def test_backward_compatibility_final(self):
        """Verify existing Final action continues to parse accurately."""
        raw_json = """{
            "thought": "Quiz completed with perfect score.",
            "action": "Final",
            "tool_service": null,
            "payload": {},
            "final_answer": "You scored 100% on the quiz."
        }"""
        step = parse_agent_step(raw_json)
        self.assertEqual(step.action, "Final")
        self.assertEqual(step.final_answer, "You scored 100% on the quiz.")


if __name__ == "__main__":
    unittest.main()
