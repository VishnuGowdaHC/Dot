import asyncio
import json
import os
import sys
from dotenv import load_dotenv

from src.dot.mcp_files.client_core import fetch_server_tools
from src.dot.memory.collections.tools_collection import upsert_tools
from src.dot.memory.collections.native_tools_collection import sync_native_tools
from src.dot.memory.vector_store import get_all_services

# Load .env from multiple candidate locations
for env_path in [
    os.path.join(os.path.dirname(__file__), "..", ".env"),
    os.path.join(os.path.dirname(__file__), "..", "..", ".env"),
    os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"),
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".env"),
    ".env"
]:
    if os.path.exists(env_path):
        load_dotenv(os.path.abspath(env_path))

def load_server_config() -> dict:
    """Loads MCP server configurations and injects environment variables."""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "config",
        "mcp_servers.json"
    )
    with open(config_path, 'r', encoding='utf-8') as f:
        config_data = f.read()

    github_token = os.getenv("GITHUB_TOKEN", "")
    config_data = config_data.replace("${GITHUB_TOKEN}", github_token)
    config_dict = json.loads(config_data)

    # Resolve python interpreter and absolute binary paths.
    base_dume = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    for server_name, server_cfg in config_dict.get("mcpServers", {}).items():
        cmd = server_cfg.get("command", "")
        if cmd in ("py", "python", "python3"):
            server_cfg["command"] = sys.executable
        elif not os.path.isabs(cmd):
            # Check relative to dum-e directory.
            cand = os.path.join(base_dume, cmd)
            if os.path.exists(cand):
                server_cfg["command"] = cand

        # Ensure working directory is set to dum-e.
        if "cwd" not in server_cfg:
            server_cfg["cwd"] = base_dume

        # Ensure PYTHONPATH includes base_dume so module imports succeed.
        env = server_cfg.setdefault("env", {})
        existing_pythonpath = env.get("PYTHONPATH", os.environ.get("PYTHONPATH", ""))
        env["PYTHONPATH"] = f"{base_dume}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else base_dume

    return config_dict

async def sync_registry(active_client=None):
    """Synchronizes all MCP and native tools into the ChromaDB catalog.

    Uses the active client session when provided to prevent duplicate process launches.
    """
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
                "inputSchema": schema
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