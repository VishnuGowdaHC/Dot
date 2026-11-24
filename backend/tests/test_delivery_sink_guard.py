"""
Unit tests for the Generic Delivery Sink Guard and Premature Clarification Interceptor.
Verifies that multi-step goals cannot terminate before delivering to external sinks.
"""

import unittest
from unittest.mock import AsyncMock, patch

from dot.core.engine import (
    extract_delivery_destination,
    check_unfulfilled_delivery,
    reAct_loop,
)


class TestDeliverySinkGuard(unittest.IsolatedAsyncioTestCase):
    """Test suite for delivery sink extraction and unfulfilled delivery guardrails."""

    def test_extract_delivery_destinations(self):
        """Verifies correct target extraction across desktop, web, and file targets."""
        test_cases = [
            ("paste it in notepad whatever u find", "notepad"),
            ("Open hn and quote the title and paste in notepad", "notepad"),
            ("fill it in the search box", "the search"),
            ("type this into vscode", "vscode"),
            ("save to summary.txt", "summary.txt"),
            ("paste into calculator", "calculator"),
            ("write content into notes.md", "notes.md"),
        ]
        for query, expected in test_cases:
            actual = extract_delivery_destination(query)
            self.assertEqual(actual, expected, f"Failed for query: {query}")

    def test_ignores_non_delivery_conversational_phrases(self):
        """Verifies that pure conversational queries do not trigger delivery guards."""
        conversational_queries = [
            "summarize andrew ng in 500 words",
            "explain quantum computing in detail",
            "who is the ceo of nvidia",
            "write a poem in english",
            "give me the key points in bullet format",
            "tell me three facts in short",
        ]
        for query in conversational_queries:
            dest = extract_delivery_destination(query)
            self.assertIsNone(dest, f"False positive delivery destination in: {query} (got: {dest})")

    def test_check_unfulfilled_delivery_blocks_until_delivery_tool_runs(self):
        """Verifies that unfulfilled delivery warning returns until a delivery tool executes."""
        query = "find the story and paste it in notepad"

        # No tools executed
        warning = check_unfulfilled_delivery(query, set())
        self.assertIsNotNone(warning)
        self.assertIn("notepad", warning)

        # Non-delivery tools executed (navigate, search, launch process)
        warning = check_unfulfilled_delivery(query, {"browser_navigate", "os_manage_process"})
        self.assertIsNotNone(warning)
        self.assertIn("notepad", warning)

        # Delivery tool executed (os_keyboard_type)
        warning = check_unfulfilled_delivery(query, {"browser_navigate", "os_manage_process", "os_keyboard_type"})
        self.assertIsNone(warning)

    @patch("dot.core.engine.async_llm")
    async def test_engine_intercepts_premature_clarify_when_context_present(self, mock_llm):
        """Verifies that engine intercepts Clarify if previous context has content to deliver."""
        # Turn 1: Model asks clarification unnecessarily
        step1_clarify = (
            '{"thought": "Asking for content.", "action": "Clarify", "tool_service": null, '
            '"payload": {}, "question": "What content would you like me to paste into Notepad?", '
            '"choices": [], "final_answer": null}'
        )
        # Turn 2: Model recovers from directive and types
        step2_type = (
            '{"thought": "Typing content into Notepad.", "action": "Tool-exec", "tool_service": "os_tools", '
            '"payload": {"name": "os_keyboard_type", "args": {"text": "Andrew Ng is a prominent computer scientist."}}, '
            '"final_answer": null}'
        )
        # Turn 3: Model finishes cleanly
        step3_final = (
            '{"thought": "Task complete.", "action": "Final", "tool_service": null, '
            '"payload": {}, "final_answer": "Pasted the summary into Notepad."}'
        )
        mock_llm.side_effect = [step1_clarify, step2_type, step3_final]

        from unittest.mock import MagicMock
        mock_session = MagicMock()
        mock_session.get_context_string.return_value = "Andrew Ng is a prominent computer scientist and AI pioneer."
        mock_session.count_tokens.return_value = 10
        mock_session.context_size = 8192
        mock_session.compaction_threshold = 7000
        mock_session.add_turn = AsyncMock()
        mock_session.tokenizer = MagicMock()
        mock_session.tokenizer.encode.return_value = [1, 2, 3, 4, 5]

        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value="Typed text into active window 'Untitled - Notepad'")

        query = "i want u to paste this in notepad"
        res = await reAct_loop(
            websocket=None,
            query=query,
            session=mock_session,
            active_client=mock_client,
            max_steps=5,
            speculative_tools=[]
        )

        self.assertIn("Pasted the summary into Notepad", res)
        # Verify 3 LLM calls occurred (clarify was rejected and recovered)
        self.assertEqual(mock_llm.call_count, 3)


if __name__ == "__main__":
    unittest.main()
