from fastmcp import Client
import json
from src.dot.mcp_files.registry import load_server_config

async def execute_mcp_tool(tool_service: str, tool_name: str, tool_args):
    config = load_server_config()

    server_settings = config["mcpServers"][tool_service]

    async with Client({"mcpServers": {tool_service: server_settings}}) as active_session:
        result = await active_session.call_tool(tool_name, tool_args)
        if result.content:
            text = result.content[0].text
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        
        return None
