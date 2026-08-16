import asyncio
import json
import os
from dotenv import load_dotenv

from src.dot.mcp_files.client_core import fetch_server_tools
from src.dot.memory.collections.tools_collection import upsert_tools
from src.dot.memory.collections.native_tools_collection import sync_native_tools
from src.dot.memory.vector_store import get_all_services

load_dotenv()

import os
import json

def load_server_config() -> dict:
    config_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),  # dot-engine folder
    "config",
    "mcp_servers.json"
    )
    with open(config_path, 'r') as f:
        config_data = f.read()

    github_token = os.getenv("GITHUB_TOKEN", "")
    config_data = config_data.replace("${GITHUB_TOKEN}", github_token)

    config_dict = json.loads(config_data)

    return config_dict

async def sync_registry():
    mcp_config = load_server_config()

    servers_dict = mcp_config.get("mcpServers", {})

    tasks = [
        fetch_server_tools(server, server_settings) 
        for server, server_settings in servers_dict.items()
    ]

    results = await asyncio.gather(*tasks)

    all_tools = [tool for server_list in results for tool in server_list]

    upsert_tools(all_tools)
    get_all_services(force_refresh=True)
    sync_native_tools()

if __name__ == "__main__":
    asyncio.run(sync_registry())