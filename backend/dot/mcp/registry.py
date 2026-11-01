"""
MCP server registry and tool synchronization with ChromaDB.
"""

import asyncio
import json
import os
import sys

from dot.config.paths import MCP_CONFIG_PATH, BACKEND_DIR
from dot.config.settings import get_github_token
from dot.mcp.client_core import fetch_server_tools
from dot.memory.collections.tools_collection import upsert_tools
from dot.memory.collections.native_tools_collection import sync_native_tools
from dot.memory.vector_store import get_all_services


def load_server_config() -> dict:
    """Loads MCP server configurations and injects environment variables."""
    with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
        config_data = f.read()

    github_token = get_github_token()
    config_data = config_data.replace("${GITHUB_TOKEN}", github_token)
    config_dict = json.loads(config_data)

    # Resolve python interpreter and absolute binary paths.
    base_dir = str(BACKEND_DIR)
    for server_name, server_cfg in config_dict.get("mcpServers", {}).items():
        cmd = server_cfg.get("command", "")
        if cmd in ("py", "python", "python3"):
            server_cfg["command"] = sys.executable
        elif not os.path.isabs(cmd):
            cand = os.path.join(base_dir, cmd)
            if os.path.exists(cand):
                server_cfg["command"] = cand

        if "cwd" not in server_cfg:
            server_cfg["cwd"] = base_dir

        env = server_cfg.setdefault("env", {})
        existing_pythonpath = env.get("PYTHONPATH", os.environ.get("PYTHONPATH", ""))
        env["PYTHONPATH"] = f"{base_dir}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else base_dir

    return config_dict


async def sync_registry(active_client=None):
    """Synchronizes all MCP and native tools into the ChromaDB catalog."""
    mcp_config = load_server_config()
    servers_dict = mcp_config.get("mcpServers", {})
    server_names = list(servers_dict.keys())

    all_tools = []
    if active_client is not None:
        tools_resp = await active_client.list_tools()
        tools_list = getattr(tools_resp, "tools", tools_resp)
        for t in tools_list:
            service = next((s for s in server_names if t.name.startswith(f"{s}_")), "unknown")
            schema = t.input_schema if hasattr(t, "input_schema") else getattr(t, "inputSchema", {})
            all_tools.append({
                "service": service,
                "toolName": t.name,
                "description": t.description,
                "inputSchema": schema,
            })
    else:
        tasks = [
            fetch_server_tools(server, server_settings)
            for server, server_settings in servers_dict.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for server_list in results:
            if isinstance(server_list, list):
                all_tools.extend(server_list)

    upsert_tools(all_tools)
    get_all_services(force_refresh=True)
    sync_native_tools()


if __name__ == "__main__":
    asyncio.run(sync_registry())

