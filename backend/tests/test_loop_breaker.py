"""
Unit tests for the ReAct loop breaker, max-step limits, and agent_browser_read argument sanitization.
Verifies that infinite execution loops and context explosions are prevented.
"""

import unittest
from unittest.mock import AsyncMock, patch

from dot.core.executor import execute_tool_call
from dot.core.engine import reAct_loop
from dot.core.parser import AgentStep
from dot.mcp.client import execute_mcp_tool


class TestLoopBreaker(unittest.IsolatedAsyncioTestCase):
    """Test suite for circuit breaker, loop strikes, and tool parameter normalization."""

    async def test_browser_read_argument_sanitization(self):
        """Verifies that browser_read sanitizes raw, requireMd, llms, and long filters."""
        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value="Article content")

        # Case 1: requireMd passed, invalid llms passed, long filter passed
        args = {
            "requireMd": True,
            "raw": True,
            "llms": "summarize",
            "filter": "Andrew Ng biography summary outline",
            "url": "https://en.wikipedia.org/wiki/Andrew_Ng",
        }
        await execute_mcp_tool(mock_client, "browser", "browser_read", args)

        mock_client.call_tool.assert_called_once()
        passed_args = mock_client.call_tool.call_args[0][1]

        self.assertFalse(passed_args.get("raw"), "raw should be forced to False")
        self.assertNotIn("requireMd", passed_args, "requireMd must not be sent to agent-browser")
        self.assertNotIn("llms", passed_args, "Invalid llms value 'summarize' must be stripped")
        self.assertNotIn("filter", passed_args, "Long conversational filter must be stripped")

    async def test_browser_read_preserves_valid_llms(self):
        """Verifies that valid llms values ('index', 'full') are preserved."""
        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value="Index links")

        for valid_mode in ("index", "full"):
            mock_client.call_tool.reset_mock()
            args = {"llms": valid_mode, "url": "https://docs.example.com"}
            await execute_mcp_tool(mock_client, "browser", "browser_read", args)
            passed_args = mock_client.call_tool.call_args[0][1]
            self.assertEqual(passed_args.get("llms"), valid_mode)

    async def test_duplicate_tool_execution_trips_circuit_breaker(self):
        """Verifies that 2 duplicate tool calls trip the circuit breaker in executor."""
        step_obj = AgentStep(
            thought="Reading page",
            action="Tool-exec",
            tool_service="browser",
            payload={"name": "browser_read", "args": {"url": "https://example.com"}},
        )

        history_parts = []
        executed_sigs = set()
        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value="Content")

        # First call: executes normally
        res1, sig1, strikes1 = await execute_tool_call(
            step_obj=step_obj,
            step_num=0,
            query="read example.com",
            session=None,
            active_client=mock_client,
            history_parts=history_parts,
            executed_signatures=executed_sigs,
            last_tool_sig=None,
            loop_strikes=0,
            max_steps=10,
        )
        self.assertFalse(res1.tripped_circuit_breaker)
        self.assertEqual(strikes1, 0)

        # Second call with identical signature: first strike
        res2, sig2, strikes2 = await execute_tool_call(
            step_obj=step_obj,
            step_num=1,
            query="read example.com",
            session=None,
            active_client=mock_client,
            history_parts=history_parts,
            executed_signatures=executed_sigs,
            last_tool_sig=sig1,
            loop_strikes=strikes1,
            max_steps=10,
        )
        self.assertTrue(res2.should_retry)
        self.assertFalse(res2.tripped_circuit_breaker)
        self.assertEqual(strikes2, 1)

        # Third call with identical signature: circuit breaker trips
        res3, sig3, strikes3 = await execute_tool_call(
            step_obj=step_obj,
            step_num=2,
            query="read example.com",
            session=None,
            active_client=mock_client,
            history_parts=history_parts,
            executed_signatures=executed_sigs,
            last_tool_sig=sig2,
            loop_strikes=strikes2,
            max_steps=10,
        )
        self.assertTrue(res3.tripped_circuit_breaker, "Circuit breaker must trip on duplicate loop")

    @patch("dot.core.engine.async_llm")
    async def test_engine_halts_at_effective_max_steps(self, mock_llm):
        """Verifies that reAct_loop strictly respects the step cap even when model loops."""
        loop_step_json = (
            '{"thought": "Searching", "action": "Tool-exec", "tool_service": "browser", '
            '"payload": {"name": "browser_search_web", "args": {"query": "test"}}, "final_answer": null}'
        )
        mock_llm.return_value = loop_step_json

        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value="Search results")

        res = await reAct_loop(
            websocket=None,
            query="search test",
            session=None,
            active_client=mock_client,
            max_steps=5,
            speculative_tools=[]
        )

        # Loop must terminate without exceeding max_steps
        self.assertIsNotNone(res)
        self.assertLessEqual(mock_llm.call_count, 6)


if __name__ == "__main__":
    unittest.main()
