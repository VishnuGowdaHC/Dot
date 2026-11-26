"""
MCP server registry and tool synchronization with ChromaDB.
"""

import asyncio
import json
import os
import sys
import shutil

from dot.config.paths import MCP_CONFIG_PATH, BACKEND_DIR, ROOT_DIR
from dot.config.settings import get_github_token, load_config
from dot.mcp.client_core import fetch_server_tools
from dot.memory.collections.tools_collection import upsert_tools
from dot.memory.collections.native_tools_collection import sync_native_tools
from dot.sandbox.tools import SANDBOX_TOOL_SCHEMAS
from dot.memory.vector_store import get_all_services


def sync_sandbox_tools() -> None:
    """Indexes sandbox tool schemas into the ChromaDB tool catalog."""
    tool_list = []
    for tool_name, schema_def in SANDBOX_TOOL_SCHEMAS.items():
        tool_list.append({
            "service": "sandbox",
            "toolName": tool_name,
            "description": schema_def.get("description", ""),
            "inputSchema": schema_def.get("inputSchema", {}),
        })
    upsert_tools(tool_list, clear_before=True)


def load_server_config() -> dict:
    """Loads MCP server configurations and injects environment variables."""
    with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
        config_data = f.read()

    github_token = get_github_token()
    config_dict = json.loads(config_data)

    # Resolve python interpreter and absolute binary paths.
    base_dir = str(BACKEND_DIR)
    venv_py = os.path.join(str(BACKEND_DIR.parent), ".venv", "Scripts", "python.exe")
    active_py = venv_py if os.path.exists(venv_py) else sys.executable

    valid_servers = {}
    for server_name, server_cfg in config_dict.get("mcpServers", {}).items():
        cmd = server_cfg.get("command", "")
        if cmd in ("py", "python", "python3"):
            server_cfg["command"] = active_py
        elif not os.path.isabs(cmd):
            cand = os.path.join(base_dir, cmd)
            bin_cand = os.path.join(base_dir, "dot", "mcp", "bin", os.path.basename(cmd))
            if os.path.exists(cand):
                server_cfg["command"] = cand
            elif os.path.exists(bin_cand):
                server_cfg["command"] = bin_cand
            elif shutil.which(cmd):
                server_cfg["command"] = shutil.which(cmd)
            else:
                print(f"[MCP Warning] Executable for '{server_name}' not found: {cmd}")
                continue
        elif not os.path.exists(cmd) and not shutil.which(cmd):
            print(f"[MCP Warning] Executable for '{server_name}' not found: {cmd}")
            continue

        if "cwd" not in server_cfg:
            server_cfg["cwd"] = base_dir

        env = server_cfg.setdefault("env", {})
        for env_key, env_val in list(env.items()):
            if isinstance(env_val, str) and "${GITHUB_TOKEN}" in env_val:
                env[env_key] = env_val.replace("${GITHUB_TOKEN}", github_token)
        env["FASTMCP_SHOW_SERVER_BANNER"] = "false"
        existing_pythonpath = env.get("PYTHONPATH", os.environ.get("PYTHONPATH", ""))
        env["PYTHONPATH"] = f"{base_dir}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else base_dir

        if server_name == "browser":
            app_cfg = load_config()
            active_cfg = app_cfg.get("active_settings", {})
            if not active_cfg.get("browser_headless", False):
                env["AGENT_BROWSER_HEADED"] = "1"
            else:
                env.pop("AGENT_BROWSER_HEADED", None)

            profile_mode = str(active_cfg.get("browser_profile_mode", "persistent")).strip()
            if profile_mode == "auto_connect":
                env["AGENT_BROWSER_AUTO_CONNECT"] = "1"
            elif profile_mode == "chrome_profile":
                profile_name = str(active_cfg.get("browser_profile_name", "Default")).strip()
                if profile_name:
                    env["AGENT_BROWSER_PROFILE"] = profile_name
            elif profile_mode == "persistent":
                profile_dir = ROOT_DIR / "data" / "browser_profile"
                profile_dir.mkdir(parents=True, exist_ok=True)
                if not active_cfg.get("browser_headless", False):
                    from dot.automation.browser import ensure_clean_chrome_cdp
                    if ensure_clean_chrome_cdp(port=9222, profile_dir=profile_dir):
                        env["AGENT_BROWSER_CDP"] = "9222"
                        env.pop("AGENT_BROWSER_PROFILE", None)
                    else:
                        env["AGENT_BROWSER_PROFILE"] = str(profile_dir)
                else:
                    env["AGENT_BROWSER_PROFILE"] = str(profile_dir)

        valid_servers[server_name] = server_cfg

    config_dict["mcpServers"] = valid_servers
    return config_dict


# Whitelist of high-signal browser tools indexed in ChromaDB.
ALLOWED_BROWSER_TOOLS = {
    "browser_navigate",
    "browser_read",
    "browser_snapshot",
    "browser_click",
    "browser_fill",
    "browser_press",
    "browser_tab_close",
    "browser_screenshot",
    "browser_close",
    "browser_probe_page",
}

# Explicit high-clarity descriptions for whitelisted browser tools to avoid semantic collision.
BROWSER_TOOL_DESCRIPTIONS = {
    "browser_navigate": "Open, visit, or navigate to a website or URL in the automation browser. Use this to open web pages, Wikipedia, search results, or documentation for reading and clicking.",
    "browser_read": "Read and extract clean text or markdown content from the active webpage or a specified URL. Provide url to directly read a page.",
    "browser_snapshot": "Inspect and return interactive elements on the current webpage with reusable @ref identifiers (@e1, @e2). Call this before clicking or filling.",
    "browser_click": "Click an interactive element, link, or button on the webpage using a @ref identifier (e.g. @e1), text, or CSS selector.",
    "browser_fill": "Clear and enter text into an input field or search box using a @ref identifier (e.g. @e2) or label.",
    "browser_press": "Press a keyboard key or hotkey (e.g. 'Enter', 'Tab', 'Escape', 'Backspace', 'Control+A') in the active automation browser window.",
    "browser_tab_close": "Close the active automation browser tab.",
    "browser_screenshot": "Capture a screenshot of the automated browser webpage.",
    "browser_close": "Close the active automation browser session and free resources.",
}

# Preserved native fast-path browser utilities.
PRESERVED_BROWSER_TOOLS = [
    {
        "service": "browser",
        "toolName": "browser_search_web",
        "description": "Search the web for links and information. Returns organic results with titles, URLs, and snippets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search keywords or question."},
                "max_results": {"type": "integer", "description": "Maximum search results to return. Defaults to 4."}
            },
            "required": ["query"]
        }
    },
    {
        "service": "browser",
        "toolName": "browser_play_video",
        "description": "Find and play a video or song on YouTube directly in the default desktop player.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The video or song name to find and play."}
            },
            "required": ["query"]
        }
    },
    {
        "service": "browser",
        "toolName": "browser_open_in_browser",
        "description": "Open a URL or search query in the external desktop browser window for the human user to view. Do NOT use this tool for agent web research, scraping, or automation; use browser_navigate instead.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Web address or search term to show to the human user."}
            },
            "required": ["target"]
        }
    },
    {
        "service": "browser",
        "toolName": "browser_probe_page",
        "description": "Search cached controls from the last page snapshot by keyword, tag type, or section heading without extra browser roundtrips.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword to match against element text, name, or @ref ID."},
                "tag_type": {"type": "string", "description": "Optional element kind: button, radio, checkbox, input, or link."},
                "section_hint": {"type": "string", "description": "Optional heading or section name to disambiguate labels."}
            },
            "required": ["query"]
        }
    }
]


async def sync_registry(active_client=None):
    """Synchronizes curated MCP and native tools into the ChromaDB catalog."""
    mcp_config = load_server_config()
    servers_dict = mcp_config.get("mcpServers", {})
    server_names = list(servers_dict.keys())

    all_tools = []
    if active_client is not None:
        tools_resp = await active_client.list_tools()
        tools_list = getattr(tools_resp, "tools", tools_resp)
        for t in tools_list:
            tool_name = t.name
            if tool_name.startswith("browser_agent_browser_"):
                clean = tool_name[len("browser_agent_browser_"):]
                clean = "navigate" if clean == "open" else clean
                tool_name = f"browser_{clean}"
                service = "browser"
            elif tool_name.startswith("agent_browser_"):
                clean = tool_name[len("agent_browser_"):]
                clean = "navigate" if clean == "open" else clean
                tool_name = f"browser_{clean}"
                service = "browser"
            elif tool_name.startswith("os_tools_"):
                # Remove redundant server prefix for OS tools.
                tool_name = tool_name[len("os_tools_"):]
                service = "os_tools"
            elif tool_name.startswith("os_"):
                # Preserve native os_ tool prefix and classify under os_tools.
                service = "os_tools"
            else:
                service = next((s for s in server_names if tool_name.startswith(f"{s}_")), "unknown")

            if service == "browser" and tool_name not in ALLOWED_BROWSER_TOOLS:
                continue

            schema = t.input_schema if hasattr(t, "input_schema") else getattr(t, "inputSchema", {})
            desc = BROWSER_TOOL_DESCRIPTIONS.get(tool_name, t.description)
            all_tools.append({
                "service": service,
                "toolName": tool_name,
                "description": desc,
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
                for t in server_list:
                    tool_name = t.get("toolName", "")
                    if t.get("service") == "browser":
                        if tool_name not in ALLOWED_BROWSER_TOOLS:
                            continue
                        if tool_name in BROWSER_TOOL_DESCRIPTIONS:
                            t["description"] = BROWSER_TOOL_DESCRIPTIONS[tool_name]
                    elif t.get("service") == "os_tools":
                        if tool_name.startswith("os_tools_"):
                            tool_name = tool_name[len("os_tools_"):]
                            t["toolName"] = tool_name
                    all_tools.append(t)

    # Ensure core browser schemas exist even if agent-browser.exe failed to mount.
    existing_names = {t.get("toolName") for t in all_tools}
    fallback_browser_schemas = {
        "browser_navigate": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
        "browser_read": {"type": "object", "properties": {"url": {"type": "string"}}, "required": []},
        "browser_snapshot": {"type": "object", "properties": {}, "required": []},
        "browser_click": {"type": "object", "properties": {"selector": {"type": "string"}, "text": {"type": "string"}}, "required": []},
        "browser_fill": {"type": "object", "properties": {"selector": {"type": "string"}, "text": {"type": "string"}}, "required": ["selector", "text"]},
        "browser_press": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]},
    }
    for fb_name, fb_schema in fallback_browser_schemas.items():
        if fb_name not in existing_names:
            all_tools.append({
                "service": "browser",
                "toolName": fb_name,
                "description": BROWSER_TOOL_DESCRIPTIONS.get(fb_name, fb_name),
                "inputSchema": fb_schema,
            })

    # Register preserved native fast-path tools
    all_tools.extend(PRESERVED_BROWSER_TOOLS)

    upsert_tools(all_tools, clear_before=True)
    sync_native_tools()
    sync_sandbox_tools()
    get_all_services(force_refresh=True)


if __name__ == "__main__":
    asyncio.run(sync_registry())

