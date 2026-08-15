import asyncio
import json
import os
from dotenv import load_dotenv

from mcp_files.mcpClient import fetch_server_tools
from memory.collections.tools_collection import upsert_tools

load_dotenv()

import os
import json

def load_server_config() -> dict:
    
    base_dir = os.path.dirname(__file__) # Path to mcp_files folder
    dot_engine_dir = os.path.dirname(base_dir) # Path to dot-engine folder
    config_path = os.path.join(dot_engine_dir, 'config', 'mcp_servers.json')
    
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

if __name__ == "__main__":
    asyncio.run(sync_registry())