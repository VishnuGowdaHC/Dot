"""
MCP server client helpers and remote tool definition retrieval.
"""

from fastmcp import Client
import traceback
import sys
from dot.memory.vector_store import get_all_services, get_full_service_tools_text

BYPASS_SERVICES = {"browser", "native", "os_tools"}


async def fetch_server_tools(server: str, server_settings: dict) -> list:
    """Retrieves tool definitions from a single MCP server configuration."""
    try:
        client = Client({
            "mcpServers": {
                server: server_settings
            }
        })

        async with client as active_session:
            tools = await active_session.list_tools()
            tools_arr = getattr(tools, "tools", tools)

            server_tools = []
            for tool in tools_arr:
                schema = tool.input_schema if hasattr(tool, "input_schema") else getattr(tool, "inputSchema", {})
                tool_name = tool.name
                if not tool_name.startswith(f"{server}_"):
                    tool_name = f"{server}_{tool_name}"
                server_tools.append({
                    "service": server,
                    "toolName": tool_name,
                    "description": tool.description,
                    "inputSchema": schema,
                })
            return server_tools
    except Exception as e:
        print(f"[Warning] Failed to fetch tools from server '{server}': {e}", file=sys.stderr)
        traceback.print_exc()
        return []

