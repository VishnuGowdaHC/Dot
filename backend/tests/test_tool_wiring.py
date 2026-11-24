"""
Integration tests for the tool wiring layer.
Verifies ChromaDB indexing and retrieval of all tool layers.
Complies with ASD-STE100 technical writing standards.
"""

import sys
from pathlib import Path

# Add backend directory to module search path.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import unittest
from unittest.mock import patch, MagicMock


class TestToolWiring(unittest.IsolatedAsyncioTestCase):
    """Test suite for tool wiring, ChromaDB indexing, and MCP boundaries."""

    def test_sandbox_tool_format_for_upsert(self):
        """Verifies that sandbox tools produce valid upsert dicts."""
        from dot.sandbox.tools import SANDBOX_TOOL_SCHEMAS
        expected_tools = {
            "sandbox_exec",
            "sandbox_browser_navigate",
            "sandbox_browser_search",
            "sandbox_screenshot",
            "request_human_intervention",
        }
        self.assertTrue(expected_tools.issubset(set(SANDBOX_TOOL_SCHEMAS.keys())))
        for name, schema_def in SANDBOX_TOOL_SCHEMAS.items():
            self.assertIn("description", schema_def, f"{name} missing description")
            self.assertIn("inputSchema", schema_def, f"{name} missing inputSchema")
            self.assertIsInstance(schema_def["inputSchema"], dict)

    def test_upsert_tools_stores_description(self):
        """Verifies that upsert_tools stores description in ChromaDB metadata."""
        mock_collection = MagicMock()
        with patch("dot.memory.collections.tools_collection.collection", mock_collection):
            from dot.memory.collections.tools_collection import upsert_tools
            upsert_tools([{
                "service": "sandbox",
                "toolName": "sandbox_exec",
                "description": "Execute a command in the sandbox.",
                "inputSchema": {"type": "object", "properties": {}, "required": []}
            }])
        call_kwargs = mock_collection.upsert.call_args[1]
        metadata_stored = call_kwargs["metadatas"][0]
        self.assertIn("description", metadata_stored)
        self.assertEqual(metadata_stored["description"], "Execute a command in the sandbox.")

    def test_sandbox_in_bypass_services(self):
        """Verifies that the sandbox service is included in the bypass set."""
        from dot.memory.vector_store import BYPASS_SERVICES
        self.assertIn("sandbox", BYPASS_SERVICES)

    def test_sync_sandbox_tools_indexes_tools(self):
        """Verifies that sync_sandbox_tools registers all sandbox tools."""
        with patch("dot.mcp.registry.upsert_tools") as mock_upsert:
            from dot.mcp.registry import sync_sandbox_tools
            sync_sandbox_tools()
            self.assertTrue(mock_upsert.called)
            tools_list = mock_upsert.call_args[0][0]
            services = {t["service"] for t in tools_list}
            self.assertEqual(services, {"sandbox"})
            tool_names = {t["toolName"] for t in tools_list}
            self.assertIn("sandbox_exec", tool_names)
            self.assertIn("sandbox_screenshot", tool_names)

    async def test_mcp_client_rejects_sandbox_tool(self):
        """Verifies that execute_mcp_tool rejects sandbox tools early."""
        from dot.mcp.client import execute_mcp_tool
        mock_client = MagicMock()
        with self.assertRaises(RuntimeError) as ctx:
            await execute_mcp_tool(mock_client, "sandbox", "sandbox_exec", {})
        self.assertIn("sandbox tool", str(ctx.exception).lower())

    def test_format_compact_tool_preserves_enum(self):
        """Verifies that format_compact_tool preserves enum values in tool signatures."""
        from dot.memory.vector_store import format_compact_tool
        sig = format_compact_tool({
            "tool_name": "os_manage_process",
            "description": "Manage processes.",
            "schema": {
                "properties": {
                    "action": {"type": "string", "enum": ["list", "kill", "start"]},
                },
                "required": ["action"],
            },
        })
        self.assertIn("'list'|'kill'|'start'", sig)

    def test_probe_page_in_browser_registry(self):
        """Verifies that browser_probe_page is registered in browser registry lists."""
        from dot.mcp.registry import ALLOWED_BROWSER_TOOLS, PRESERVED_BROWSER_TOOLS
        self.assertIn("browser_probe_page", ALLOWED_BROWSER_TOOLS)
        names = {t["toolName"] for t in PRESERVED_BROWSER_TOOLS}
        self.assertIn("browser_probe_page", names)

    async def test_mcp_client_does_not_retry_execution_error(self):
        """Verifies that execute_mcp_tool stops retrying on non-unknown-tool errors."""
        from unittest.mock import AsyncMock
        from dot.mcp.client import execute_mcp_tool
        mock_client = MagicMock()
        mock_client.call_tool = AsyncMock(side_effect=RuntimeError("Permission denied"))
        with self.assertRaises(RuntimeError) as ctx:
            await execute_mcp_tool(mock_client, "os_tools", "os_manage_process", {"action": "list"})
        self.assertIn("Permission denied", str(ctx.exception))
        self.assertEqual(mock_client.call_tool.call_count, 1)


if __name__ == "__main__":
    unittest.main()
