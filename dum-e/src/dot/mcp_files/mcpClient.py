from fastmcp import Client
import json
from src.dot.mcp_files.registry import load_server_config

def get_multi_server_client() -> Client:
    config = load_server_config()

    return Client(config)

async def execute_mcp_tool(active_client: Client, tool_service: str, tool_name: str, tool_args):
        result = await active_client.call_tool(tool_name, tool_args)
        
        if result.content:
            text = result.content[0].text
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        
        return None
