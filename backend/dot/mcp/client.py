"""
FastMCP client pool and sampling handler.
"""

from typing import Optional
from fastmcp import Client
from fastmcp.client.sampling import SamplingMessage, SamplingParams, RequestContext
import json
from dot.mcp.registry import load_server_config
from dot.core.llm import async_llm


async def sampling_handler(
    messages: list[SamplingMessage],
    params: SamplingParams,
    context: Optional[RequestContext] = None,
) -> str:
    """Handles FastMCP sampling requests using the asynchronous LLM client."""
    text_parts = []
    image_url = None

    for m in messages:
        content = m.content
        if hasattr(content, "text"):
            text_parts.append(content.text)
        elif hasattr(content, "data"):
            image_url = f"data:{content.mimeType};base64,{content.data}"

    query = "\n".join(text_parts) if text_parts else "Describe the image."
    system_prompt = getattr(params, "system_prompt", None) or getattr(params, "systemPrompt", None) or "Respond in plain text only. No JSON."

    return await async_llm(query=query, image_url=image_url, system_prompt=system_prompt)


# Tool aliases for backward compatibility and model variation tolerance.
TOOL_ALIASES = {
    "ai_background_load_page": "browser_navigate",
    "browser_ai_background_load_page": "browser_navigate",
    "browser_load_page": "browser_navigate",
    "load_page": "browser_navigate",
    "open_desktop_tab_for_user": "browser_open_in_browser",
    "browser_open_desktop_tab_for_user": "browser_open_in_browser",
    "browser_open_browser": "browser_open_in_browser",
    "os_take_screenshot": "os_tools_os_take_screenshot",
    "take_screenshot": "os_tools_os_take_screenshot",
    "os_tools_take_screenshot": "os_tools_os_take_screenshot",
    "manage_process": "os_tools_os_manage_process",
    "os_manage_process": "os_tools_os_manage_process",
    "os_tools_manage_process": "os_tools_os_manage_process",
}


def get_multi_server_client() -> Client:
    """Returns a unified FastMCP client configured with all registered servers."""
    config = load_server_config()
    return Client(config, sampling_handler=sampling_handler)


async def execute_mcp_tool(active_client: Client, tool_service: str, tool_name: str, tool_args):
    """Executes a tool on the active FastMCP client instance."""
    if not tool_service:
        if tool_name.startswith("browser_"):
            tool_service = "browser"
        elif tool_name.startswith("os_tools_") or tool_name.startswith("os_"):
            tool_service = "os_tools"
        elif tool_name.startswith("github_"):
            tool_service = "github"

    if tool_service == "github" or tool_name.startswith("github_"):
        from dot.config.settings import get_github_token
        if not get_github_token():
            raise RuntimeError(
                "GitHub Personal Access Token (PAT) is missing. "
                "Configure a valid GitHub PAT in Settings (3 dots > MCP Tools) or set the GITHUB_TOKEN environment variable."
            )

    resolved_name = TOOL_ALIASES.get(tool_name, tool_name)
    raw_name = resolved_name
    if tool_service and resolved_name.startswith(f"{tool_service}_"):
        raw_name = resolved_name[len(tool_service) + 1:]

    prefixed_name = f"{tool_service}_{raw_name}" if tool_service else resolved_name
    candidates = [resolved_name, prefixed_name, raw_name, tool_name]

    seen = set()
    unique_candidates = [c for c in candidates if not (c in seen or seen.add(c))]

    last_error = None
    result = None

    for name in unique_candidates:
        try:
            result = await active_client.call_tool(name, tool_args or {})
            break
        except Exception as err:
            # Preserve meaningful tool execution errors over fallback 'Unknown tool' errors
            if last_error is None or "unknown tool" in str(last_error).lower():
                last_error = err

    if result is None:
        raise RuntimeError(f"Tool '{tool_name}' failed to execute on server '{tool_service}': {last_error}")

    if hasattr(result, "content") and result.content:
        first_item = result.content[0]
        if hasattr(first_item, "text"):
            text = first_item.text
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return text

    return result

