"""
Unit tests for GitHub PAT guardrails and execution barriers.
Verifies that the agent receives clear errors when attempting to use GitHub MCP without a PAT.
"""

import unittest
from unittest.mock import patch, MagicMock
from dot.core.parser import AgentStep
from dot.core.guardrails import check_guardrails
from dot.mcp.client import execute_mcp_tool


class TestGithubPATGuardrails(unittest.IsolatedAsyncioTestCase):
    """Validates GitHub Personal Access Token guardrail enforcement."""

    @patch("dot.config.settings.get_github_token", return_value="")
    def test_guardrails_blocks_tool_exec_without_token(self, mock_token):
        """Verifies that Tool-exec for GitHub tools returns an error when PAT is missing."""
        step = AgentStep(
            thought="Checking github repository issues.",
            action="Tool-exec",
            tool_service="github",
            payload={"name": "github_list_issues", "args": {}},
        )
        error = check_guardrails(step)
        self.assertIsNotNone(error)
        self.assertIn("GitHub Personal Access Token (PAT) is missing", error)

    @patch("dot.config.settings.get_github_token", return_value="ghp_mock_token_12345")
    def test_guardrails_allows_tool_exec_with_token(self, mock_token):
        """Verifies that Tool-exec for GitHub tools passes when PAT is present."""
        step = AgentStep(
            thought="Listing github issues.",
            action="Tool-exec",
            tool_service="github",
            payload={"name": "github_list_issues", "args": {}},
        )
        error = check_guardrails(step)
        self.assertIsNone(error)

    @patch("dot.config.settings.get_github_token", return_value="")
    def test_guardrails_blocks_tool_discovery_without_token(self, mock_token):
        """Verifies that Tool discovery for GitHub returns an error when PAT is missing."""
        step = AgentStep(
            thought="Searching for github tools.",
            action="Tool",
            tool_service="github",
            payload={"query": "list repositories"},
        )
        error = check_guardrails(step)
        self.assertIsNotNone(error)
        self.assertIn("GitHub Personal Access Token (PAT) is missing", error)

    @patch("dot.config.settings.get_github_token", return_value="")
    async def test_execute_mcp_tool_raises_without_token(self, mock_token):
        """Verifies that execute_mcp_tool raises RuntimeError when PAT is missing."""
        mock_client = MagicMock()
        with self.assertRaises(RuntimeError) as ctx:
            await execute_mcp_tool(mock_client, "github", "github_search_repositories", {})
        self.assertIn("GitHub Personal Access Token (PAT) is missing", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
