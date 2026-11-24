"""
Unit tests for the Action Promise Interceptor in the ReAct engine.
Verifies that premature Final answers with unexecuted action promises are intercepted.
Complies with ASD-STE100 technical writing rules.
"""

import sys
from pathlib import Path

# Add backend directory to module search path.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import unittest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from dot.core.parser import AgentStep
from dot.core.engine import check_action_promises, reAct_loop
from dot.memory.rolling_memory import get_rolling_memory


class TestActionPromiseGuard(unittest.IsolatedAsyncioTestCase):
    """Test suite for intercepting unfulfilled action promises in final_answer."""

    def setUp(self):
        self.rolling_mem = get_rolling_memory()
        self.rolling_mem.clear()

    def test_detects_future_action_promises(self):
        """Verifies that promise phrases trigger the promise guard."""
        promising_texts = [
            "The story has 355 points. I will now paste this into Notepad.",
            "I shall now open notepad and type the content.",
            "Found the story. Now pasting this into the editor.",
            "Let me now paste this into notepad.",
            "I am going to save this to a file now.",
        ]
        for text in promising_texts:
            is_promise = check_action_promises(text)
            self.assertTrue(is_promise, f"Failed to detect promise in: {text}")

    def test_allows_valid_completed_answers(self):
        """Verifies that normal completions without future promises pass cleanly."""
        completed_texts = [
            "I found the top story and pasted it into Notepad for you.",
            "The top story has 355 points. Here is the title.",
            "I created the file and completed your request.",
            "The weather in Tokyo is sunny with a temperature of 18 degrees.",
        ]
        for text in completed_texts:
            is_promise = check_action_promises(text)
            self.assertFalse(is_promise, f"Incorrectly flagged completed answer: {text}")

    @patch("dot.core.engine.async_llm")
    async def test_engine_intercepts_premature_final_and_recovers(self, mock_llm):
        """Verifies that engine rejects a promising Final and prompts for tool execution."""
        # Turn 1: Model promises action inside final_answer
        step1_json = (
            '{"thought": "Quoting story.", "action": "Final", "tool_service": null, '
            '"payload": {}, "final_answer": "Top story found. I will now paste this into Notepad."}'
        )
        # Turn 2: Model recovers and starts Notepad
        step2_json = (
            '{"thought": "Launching Notepad.", "action": "Tool-exec", "tool_service": "os_tools", '
            '"payload": {"name": "os_manage_process", "args": {"action": "start", "process_name": "notepad.exe"}}, '
            '"final_answer": null}'
        )
        # Turn 3: Model types into Notepad
        step3_json = (
            '{"thought": "Typing content into Notepad.", "action": "Tool-exec", "tool_service": "os_tools", '
            '"payload": {"name": "os_keyboard_type", "args": {"text": "Top story title"}}, '
            '"final_answer": null}'
        )
        # Turn 4: Model finishes cleanly
        step4_json = (
            '{"thought": "Task complete.", "action": "Final", "tool_service": null, '
            '"payload": {}, "final_answer": "Pasted into Notepad successfully."}'
        )
        mock_llm.side_effect = [step1_json, step2_json, step3_json, step4_json]

        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value="Successfully executed.")

        query = "Find story and paste into notepad"
        res = await reAct_loop(
            websocket=None,
            query=query,
            session=None,
            active_client=mock_client,
            max_steps=5,
            speculative_tools=[]
        )

        self.assertIn("Pasted into Notepad successfully", res)
        # Verify 4 LLM calls occurred (promise interception + delivery completion)
        self.assertEqual(mock_llm.call_count, 4)

    @patch("dot.core.engine.async_llm")
    async def test_engine_intercepts_premature_clarify_promise(self, mock_llm):
        """Verifies that engine rejects a Clarify action that promises a future action."""
        # Turn 1: Model emits Clarify with a promise and trivial choice
        step1_json = (
            '{"thought": "Promising action.", "action": "Clarify", "tool_service": null, '
            '"payload": {}, "question": "I will now paste this into Notepad.", "choices": ["ok"], "final_answer": null}'
        )
        # Turn 2: Model recovers and executes tool
        step2_json = (
            '{"thought": "Typing content.", "action": "Tool-exec", "tool_service": "os_tools", '
            '"payload": {"name": "os_keyboard_type", "args": {"text": "Top story title"}}, '
            '"final_answer": null}'
        )
        # Turn 3: Model finishes cleanly
        step3_json = (
            '{"thought": "Task complete.", "action": "Final", "tool_service": null, '
            '"payload": {}, "final_answer": "Pasted into Notepad successfully."}'
        )
        mock_llm.side_effect = [step1_json, step2_json, step3_json]

        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value="Successfully executed.")

        query = "Find story and paste into notepad"
        res = await reAct_loop(
            websocket=None,
            query=query,
            session=None,
            active_client=mock_client,
            max_steps=5,
            speculative_tools=[]
        )

        self.assertIn("Pasted into Notepad successfully", res)
        self.assertEqual(mock_llm.call_count, 3)

    @patch("dot.core.engine.async_llm")
    async def test_engine_intercepts_clarify_promise_with_dict_choices(self, mock_llm):
        """Verifies that engine rejects a Clarify action that contains dictionary choices."""
        # Turn 1: Model emits Clarify with a promise and dictionary choice {"text": "ok"}
        step1_json = (
            '{"thought": "Promising action.", "action": "Clarify", "tool_service": null, '
            '"payload": {}, "question": "I will now paste this into Notepad.", '
            '"choices": [{"text": "ok"}], "final_answer": null}'
        )
        # Turn 2: Model recovers and executes tool
        step2_json = (
            '{"thought": "Typing content.", "action": "Tool-exec", "tool_service": "os_tools", '
            '"payload": {"name": "os_keyboard_type", "args": {"text": "Top story title"}}, '
            '"final_answer": null}'
        )
        # Turn 3: Model finishes cleanly
        step3_json = (
            '{"thought": "Task complete.", "action": "Final", "tool_service": null, '
            '"payload": {}, "final_answer": "Pasted into Notepad successfully."}'
        )
        mock_llm.side_effect = [step1_json, step2_json, step3_json]

        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value="Successfully executed.")

        query = "Find story and paste into notepad"
        res = await reAct_loop(
            websocket=None,
            query=query,
            session=None,
            active_client=mock_client,
            max_steps=5,
            speculative_tools=[]
        )

        self.assertIn("Pasted into Notepad successfully", res)
        self.assertEqual(mock_llm.call_count, 3)


if __name__ == "__main__":
    unittest.main()
