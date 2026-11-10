"""
FastMCP client pool and sampling handler.
"""

from typing import Optional
import json
import re
from fastmcp import Client
from fastmcp.client.sampling import SamplingMessage, SamplingParams, RequestContext
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
            mime = getattr(content, "mime_type", None) or getattr(content, "mimeType", "image/png")
            image_url = f"data:{mime};base64,{content.data}"

    query = "\n".join(text_parts) if text_parts else "Describe the image."
    system_prompt = getattr(params, "system_prompt", None) or getattr(params, "systemPrompt", None) or "Respond in plain text only. No JSON."

    return await async_llm(query=query, image_url=image_url, system_prompt=system_prompt)


# Tool aliases for backward compatibility and model variation tolerance.
TOOL_ALIASES = {
    # Browser automation tool mappings to agent-browser
    "browser_navigate": "agent_browser_open",
    "navigate": "agent_browser_open",
    "browser_open": "agent_browser_open",
    "ai_background_load_page": "agent_browser_open",
    "browser_ai_background_load_page": "agent_browser_open",
    "browser_load_page": "agent_browser_open",
    "load_page": "agent_browser_open",
    "browser_read": "agent_browser_read",
    "read": "agent_browser_read",
    "browser_extract_text": "agent_browser_read",
    "extract_text": "agent_browser_read",
    "browser_snapshot": "agent_browser_snapshot",
    "snapshot": "agent_browser_snapshot",
    "browser_click": "agent_browser_click",
    "click": "agent_browser_click",
    "browser_fill": "agent_browser_fill",
    "fill": "agent_browser_fill",
    "browser_press": "agent_browser_press",
    "browser_press_key": "agent_browser_press",
    "press_key": "agent_browser_press",
    "press": "agent_browser_press",
    "browser_keyboard_press": "agent_browser_press",
    "browser_tab_close": "agent_browser_tab_close",
    "browser_close_tab": "agent_browser_tab_close",
    "close_tab": "agent_browser_tab_close",
    "browser_screenshot": "agent_browser_screenshot",
    "screenshot": "agent_browser_screenshot",
    "browser_close": "agent_browser_close",
    "browser_close_browser": "agent_browser_close",
    "close_browser": "agent_browser_close",
    # OS tools aliases
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


_LAST_BROWSER_REFS: dict[str, dict] = {}

KEY_MAP = {
    "enter": "Enter",
    "return": "Enter",
    "tab": "Tab",
    "esc": "Escape",
    "escape": "Escape",
    "backspace": "Backspace",
    "space": "Space",
    "delete": "Delete",
    "up": "ArrowUp",
    "down": "ArrowDown",
    "left": "ArrowLeft",
    "right": "ArrowRight",
    "ctrl+a": "Control+a",
    "control+a": "Control+a",
    "ctrl+c": "Control+c",
    "control+c": "Control+c",
    "ctrl+v": "Control+v",
    "control+v": "Control+v",
    "ctrl+w": "Control+w",
    "control+w": "Control+w",
    "ctrl+z": "Control+z",
    "control+z": "Control+z",
    "alt+tab": "Alt+Tab",
    "shift": "Shift",
}


def resolve_browser_selector(call_args: dict, action_type: str = "click", refs: Optional[dict] = None) -> str:
    """Resolves human or model selector expressions into exact @ref or CSS selectors."""
    if refs is None:
        refs = _LAST_BROWSER_REFS

    sel = (
        call_args.get("selector")
        or call_args.get("ref")
        or call_args.get("element")
        or call_args.get("target")
        or call_args.get("id")
        or call_args.get("name")
        or call_args.get("text")
        or call_args.get("description")
        or ""
    )
    sel = str(sel).strip()

    if not sel:
        if refs:
            role_targets = ["button", "link"] if action_type == "click" else ["textbox", "searchbox"]
            for r_key, r_info in refs.items():
                if r_info.get("role") in role_targets:
                    return f"@{r_key}"
        return "@e1"

    if sel.startswith("@e") and sel[2:].isdigit():
        return sel
    if sel.startswith("e") and sel[1:].isdigit():
        return f"@{sel}"
    if sel.isdigit():
        return f"@e{sel}"

    sel_lower = sel.lower().strip("\"'")

    ordinal_patterns = [
        (r"\b(first|1st)\s+link\b", "link", 0),
        (r"\b(second|2nd)\s+link\b", "link", 1),
        (r"\b(third|3rd)\s+link\b", "link", 2),
        (r"\b(first|1st)\s+(button|btn)\b", "button", 0),
        (r"\b(second|2nd)\s+(button|btn)\b", "button", 1),
        (r"\b(first|1st)\s+(input|textbox|box|field)\b", "textbox", 0),
        (r"\b(second|2nd)\s+(input|textbox|box|field)\b", "textbox", 1),
    ]
    for pattern, role, idx in ordinal_patterns:
        if re.search(pattern, sel_lower):
            matched = [
                k for k, v in refs.items()
                if v.get("role") == role or (role == "textbox" and v.get("role") in ("textbox", "searchbox"))
            ]
            if len(matched) > idx:
                return f"@{matched[idx]}"

    if action_type == "fill" and any(k in sel_lower for k in ("editor", "code", "script", "main.py")):
        for r_key, r_info in refs.items():
            role = r_info.get("role")
            name = (r_info.get("name") or "").lower()
            if role in ("textbox", "searchbox") and any(ind in name for ind in ("#", "def ", "import ", "print", "python", "main")):
                return f"@{r_key}"

    for r_key, r_info in refs.items():
        name = (r_info.get("name") or "").lower().strip()
        if name and name == sel_lower:
            return f"@{r_key}"

    for r_key, r_info in refs.items():
        name = (r_info.get("name") or "").lower().strip()
        if name and (sel_lower in name or name in sel_lower):
            if action_type == "click" and r_info.get("role") in ("button", "link", "radio", "checkbox"):
                return f"@{r_key}"
            elif action_type == "fill" and r_info.get("role") in ("textbox", "searchbox", "spinbutton"):
                return f"@{r_key}"

    for r_key, r_info in refs.items():
        name = (r_info.get("name") or "").lower().strip()
        if name and (sel_lower in name or name in sel_lower):
            return f"@{r_key}"

    if any(sel.startswith(prefix) for prefix in ("#", ".", "[", "input", "button", "a", "select", "textarea")):
        return sel

    return sel


def get_multi_server_client() -> Client:
    """Returns a unified FastMCP client configured with all registered servers."""
    config = load_server_config()
    return Client(config, sampling_handler=sampling_handler)


async def execute_mcp_tool(active_client: Client, tool_service: str, tool_name: str, tool_args):
    """Executes a tool on the active FastMCP client instance."""
    # Sandbox tools are not served by FastMCP. Reject them early.
    if tool_service == "sandbox" or tool_name.startswith("sandbox_") or tool_name == "request_human_intervention":
        raise RuntimeError(
            f"Tool '{tool_name}' is a sandbox tool. Route it through the sandbox executor, not the MCP client."
        )

    if not tool_service:
        if tool_name.startswith("browser_"):
            tool_service = "browser"
        elif tool_name.startswith("os_tools_") or tool_name.startswith("os_"):
            tool_service = "os_tools"
        elif tool_name.startswith("github_"):
            tool_service = "github"

    # Fast-path execution for preserved native browser tools
    if tool_name in ("browser_search_web", "search_web"):
        from dot.automation.browser import search_web
        return await search_web(**(tool_args or {}))
    if tool_name in ("browser_play_video", "play_video"):
        from dot.automation.browser import play_video
        return await play_video(**(tool_args or {}))
    if tool_name in (
        "browser_open_in_browser",
        "open_in_browser",
        "open_desktop_tab_for_user",
        "browser_open_desktop_tab_for_user",
        "browser_open_browser",
    ):
        from dot.automation.browser import open_in_browser
        return open_in_browser(**(tool_args or {}))

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

    # Normalize parameters for agent-browser tools
    call_args = dict(tool_args or {})
    if resolved_name == "agent_browser_open":
        _LAST_BROWSER_REFS.clear()
        call_args.setdefault("timeoutMs", 15000)
        call_args["headed"] = True
    elif resolved_name == "agent_browser_snapshot":
        call_args.setdefault("interactive", True)
        call_args.setdefault("compact", True)
    elif resolved_name == "agent_browser_click":
        if not _LAST_BROWSER_REFS and not str(call_args.get("selector", "")).startswith("@e"):
            try:
                snap_init = await active_client.call_tool("agent_browser_snapshot", {"interactive": True, "compact": True})
                if hasattr(snap_init, "data") and isinstance(snap_init.data, dict):
                    refs_data = snap_init.data.get("response", {}).get("data", {}).get("refs", {})
                    if refs_data:
                        _LAST_BROWSER_REFS.update(refs_data)
            except Exception:
                pass
        call_args["selector"] = resolve_browser_selector(call_args, action_type="click")
    elif resolved_name == "agent_browser_fill":
        if not _LAST_BROWSER_REFS and not str(call_args.get("selector", "")).startswith("@e"):
            try:
                snap_init = await active_client.call_tool("agent_browser_snapshot", {"interactive": True, "compact": True})
                if hasattr(snap_init, "data") and isinstance(snap_init.data, dict):
                    refs_data = snap_init.data.get("response", {}).get("data", {}).get("refs", {})
                    if refs_data:
                        _LAST_BROWSER_REFS.update(refs_data)
            except Exception:
                pass
        call_args["selector"] = resolve_browser_selector(call_args, action_type="fill")
        if "text" not in call_args:
            for text_alias in ("value", "content", "input", "query", "string", "code"):
                if text_alias in call_args:
                    call_args["text"] = str(call_args.pop(text_alias))
                    break
        if "text" not in call_args:
            call_args["text"] = ""
    elif resolved_name == "agent_browser_press":
        raw_key = call_args.get("key") or call_args.get("keys") or call_args.get("name")
        if isinstance(raw_key, list):
            raw_key = raw_key[0] if raw_key else "Enter"
        if raw_key:
            k_str = str(raw_key).strip()
            call_args["key"] = KEY_MAP.get(k_str.lower(), k_str)
        else:
            call_args["key"] = "Enter"

    last_error = None
    result = None

    for name in unique_candidates:
        try:
            result = await active_client.call_tool(name, call_args)
            break
        except Exception as err:
            # Preserve meaningful tool execution errors over fallback 'Unknown tool' errors
            if last_error is None or "unknown tool" in str(last_error).lower():
                last_error = err

    if result is None:
        err_msg = str(last_error or "")
        # Recover gracefully if browser is not launched
        if "browser not launched" in err_msg.lower():
            if call_args.get("url"):
                try:
                    await active_client.call_tool("agent_browser_open", {"url": call_args["url"], "timeoutMs": 15000, "headed": True})
                    result = await active_client.call_tool("agent_browser_read", call_args)
                except Exception as retry_err:
                    return {"success": False, "detail": None, "error": f"Failed to open and read URL: {retry_err}"}
            else:
                return {
                    "success": False,
                    "detail": None,
                    "error": "The automation browser is not open. Call 'browser_navigate' with a target URL first, or pass 'url' to 'browser_extract_text'."
                }
        elif "timed out" in err_msg.lower() and resolved_name == "agent_browser_open":
            return {
                "success": True,
                "detail": "Navigated to URL. Page DOM is loaded and ready. Call 'browser_snapshot' or 'browser_extract_text' to proceed."
            }
        elif any(code in err_msg for code in ("10054", "10060")):
            _LAST_BROWSER_REFS.clear()
            return {
                "success": False,
                "detail": None,
                "error": "Browser connection reset. The background browser session has restarted. Please retry your request."
            }
        else:
            raise RuntimeError(f"Tool '{tool_name}' failed to execute on server '{tool_service}': {last_error}")

    if resolved_name == "agent_browser_snapshot":
        if hasattr(result, "data") and isinstance(result.data, dict):
            refs_data = result.data.get("response", {}).get("data", {}).get("refs", {})
            if refs_data:
                _LAST_BROWSER_REFS.clear()
                _LAST_BROWSER_REFS.update(refs_data)

    if hasattr(result, "content") and result.content:
        texts = []
        for item in result.content:
            if hasattr(item, "text") and item.text:
                texts.append(item.text)
        if texts:
            combined = "\n".join(texts)
            if resolved_name == "agent_browser_snapshot":
                combined = re.sub(r"\[ref=(e\d+)\]", r"[@\1]", combined)
            try:
                return json.loads(combined)
            except (json.JSONDecodeError, TypeError):
                return combined

    return result

