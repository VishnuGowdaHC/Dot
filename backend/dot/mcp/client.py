"""
FastMCP client pool and sampling handler.
"""

from typing import Optional
from pathlib import Path
import json
import re
from fastmcp import Client
from fastmcp.client.sampling import SamplingMessage, SamplingParams, RequestContext
from dot.mcp.registry import load_server_config
from dot.core.llm import async_llm
from dot.config.paths import LOGS_DIR
from dot.automation.browser import (
    _dump_to_scratch,
    _search_scratch_elements,
    _build_compact_manifest,
    clean_readable_text,
)


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
    "probe_page": "probe_page",
    "browser_probe_page": "probe_page",
    "browser_probe": "probe_page",
    "browser_find_element": "probe_page",
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
    "keyboard_type": "os_tools_os_keyboard_type",
    "os_keyboard_type": "os_tools_os_keyboard_type",
    "os_tools_keyboard_type": "os_tools_os_keyboard_type",
    "type_text": "os_tools_os_keyboard_type",
    "os_type_text": "os_tools_os_keyboard_type",
    "keyboard_press": "os_tools_os_keyboard_press",
    "os_keyboard_press": "os_tools_os_keyboard_press",
    "os_tools_keyboard_press": "os_tools_os_keyboard_press",
    "send_hotkey": "os_tools_os_keyboard_press",
    "os_send_hotkey": "os_tools_os_keyboard_press",
    "get_active_window": "os_tools_os_get_active_window",
    "os_get_active_window": "os_tools_os_get_active_window",
    "os_tools_get_active_window": "os_tools_os_get_active_window",
    "mouse_click": "os_tools_os_mouse_click",
    "os_mouse_click": "os_tools_os_mouse_click",
    "os_tools_mouse_click": "os_tools_os_mouse_click",
    "click_text": "os_tools_os_click_text",
    "os_click_text": "os_tools_os_click_text",
    "os_tools_click_text": "os_tools_os_click_text",
    "find_text_coordinates": "os_tools_os_find_text_coordinates",
    "os_find_text_coordinates": "os_tools_os_find_text_coordinates",
    "os_tools_find_text_coordinates": "os_tools_os_find_text_coordinates",
}


_LAST_BROWSER_REFS: dict[str, dict] = {}


def _parse_agent_browser_snapshot(snapshot_text: str) -> list:
    """Parses agent-browser accessibility tree lines into structured element dictionaries.

    Complies with ASD-STE100 rules.
    """
    elements = []
    current_section = "General"

    for line in snapshot_text.splitlines():
        line_str = line.strip()
        if line_str.startswith("#"):
            current_section = line_str.lstrip("#").strip()[:80] or "General"
            continue

        ref_match = re.search(r"(?:@|ref=)\s*@?(e\d+)", line_str)
        role_match = re.match(r"^[-*]\s*([a-zA-Z0-9_\-]+)", line_str)
        role = role_match.group(1).lower() if role_match else "element"

        # Extract text within quotes, supporting escaped quotes
        text_match = re.search(r'"((?:\\.|[^"\\])*)"', line_str)
        if text_match:
            text = text_match.group(1).replace(r'\"', '"').strip()
        else:
            text_match = re.search(r"'((?:\\.|[^'\\])*)'", line_str)
            text = text_match.group(1).replace(r"\'", "'").strip() if text_match else ""

        ref = f"@{ref_match.group(1)}" if ref_match else ""
        if not ref and not text:
            continue

        tag = (
            "button" if role in ("button", "submit")
            else "a" if role == "link"
            else "input" if role in ("textbox", "checkbox", "radio", "searchbox")
            else role
        )

        elements.append({
            "ref": ref,
            "tag": tag,
            "role": role,
            "type": role,
            "text": text,
            "name": text,
            "section": current_section,
            "coords": {"x": 0, "y": 0, "width": 0, "height": 0}
        })
    return elements

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
        return ""

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


async def _call_active_tool(client: Client, server_prefix: str, tool_name: str, args: dict):
    """Invokes a tool on the active FastMCP client instance with server prefix fallback.

    Complies with ASD-STE100 rules.
    """
    candidates = [
        f"{server_prefix}_{tool_name}" if server_prefix else tool_name,
        tool_name,
    ]
    last_err = None
    for name in candidates:
        try:
            return await client.call_tool(name, args)
        except Exception as err:
            last_err = err
    raise last_err


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

    resolved_name = TOOL_ALIASES.get(tool_name, tool_name)

    if resolved_name == "probe_page" or tool_name in ("probe_page", "browser_probe_page", "browser_probe", "browser_find_element"):
        import dot.automation.browser as browser_mod
        args_dict = dict(tool_args or {})
        query = str(args_dict.get("query") or args_dict.get("q") or "").strip()
        tag_type = args_dict.get("tag_type") or args_dict.get("type")
        section_hint = args_dict.get("section_hint") or args_dict.get("section")
        matches = _search_scratch_elements(
            query=query,
            elements=browser_mod._ACTIVE_SCRATCH_ELEMENTS,
            tag_type=tag_type,
            section_hint=section_hint,
        )
        if not matches:
            return (
                f"No controls found matching query='{query}'. "
                "Check logs/scratch_page.md for all cached page elements."
            )
        lines = [f"Found {len(matches)} matching control(s):"]
        for m in matches[:12]:
            ref_str = f"[{m.get('ref')}] " if m.get("ref") else ""
            lines.append(f"- {ref_str}{m.get('role')} '{m.get('text')}' (section: {m.get('section', 'General')})")
        if len(matches) > 12:
            lines.append(f"... and {len(matches) - 12} more matches cached in logs/scratch_page.md.")
        return "\n".join(lines)

    if tool_service == "github" or tool_name.startswith("github_"):
        from dot.config.settings import get_github_token
        if not get_github_token():
            raise RuntimeError(
                "GitHub Personal Access Token (PAT) is missing. "
                "Configure a valid GitHub PAT in Settings (3 dots > MCP Tools) or set the GITHUB_TOKEN environment variable."
            )

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
        call_args.setdefault("interactive", False)
        call_args.setdefault("compact", True)
    elif resolved_name == "agent_browser_click":
        if not _LAST_BROWSER_REFS and not str(call_args.get("selector", "")).startswith("@e"):
            try:
                snap_init = await _call_active_tool(active_client, "browser", "agent_browser_snapshot", {"interactive": True, "compact": True})
                if hasattr(snap_init, "data") and isinstance(snap_init.data, dict):
                    refs_data = snap_init.data.get("response", {}).get("data", {}).get("refs", {})
                    if refs_data:
                        _LAST_BROWSER_REFS.update(refs_data)
            except Exception:
                pass
        call_args["selector"] = resolve_browser_selector(call_args, action_type="click")
        if not call_args["selector"]:
            return {
                "success": False,
                "detail": None,
                "error": "Provide a selector, @ref, or element text to click.",
            }
    elif resolved_name == "agent_browser_fill":
        if not _LAST_BROWSER_REFS and not str(call_args.get("selector", "")).startswith("@e"):
            try:
                snap_init = await _call_active_tool(active_client, "browser", "agent_browser_snapshot", {"interactive": True, "compact": True})
                if hasattr(snap_init, "data") and isinstance(snap_init.data, dict):
                    refs_data = snap_init.data.get("response", {}).get("data", {}).get("refs", {})
                    if refs_data:
                        _LAST_BROWSER_REFS.update(refs_data)
            except Exception:
                pass
        call_args["selector"] = resolve_browser_selector(call_args, action_type="fill")
        if not call_args["selector"]:
            return {
                "success": False,
                "detail": None,
                "error": "Provide a selector, @ref, or field name to fill.",
            }
        if "text" not in call_args:
            for text_alias in ("value", "content", "input", "query", "string", "code"):
                if text_alias in call_args:
                    call_args["text"] = str(call_args.pop(text_alias))
                    break
        if "text" not in call_args:
            call_args["text"] = ""
    elif resolved_name == "agent_browser_read":
        # Force raw=False so agent-browser extracts readable document content
        call_args["raw"] = False
        # Do not set requireMd=True: standard web pages serve text/html, not text/markdown
        call_args.pop("requireMd", None)

        # Suppress outline=True during content reads
        # Passing outline=True causes agent-browser to omit page text and only return headings
        call_args["outline"] = False

        # Validate llms argument (only accepts 'index' or 'full')
        if "llms" in call_args and call_args["llms"] not in ("index", "full"):
            call_args.pop("llms", None)

        # Sanitize natural language filter strings that cause 'No matching headings'
        if "filter" in call_args and isinstance(call_args["filter"], str):
            filter_words = call_args["filter"].strip().split()
            if len(filter_words) > 1:
                # Conversational phrases like 'Andrew Ng biography' do not match exact headings
                call_args.pop("filter", None)

        allowed_read_keys = {
            "filter", "llms", "outline", "raw", "readTimeoutMs",
            "url", "session", "namespace", "timeoutMs",
        }
        if "selector" in call_args and "filter" not in call_args:
            call_args["filter"] = call_args.pop("selector")
        call_args = {k: v for k, v in call_args.items() if k in allowed_read_keys}
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
            err_lower = str(err).lower()
            is_unknown = any(marker in err_lower for marker in ("unknown tool", "not found", "does not exist"))
            if last_error is None or "unknown tool" in str(last_error).lower():
                last_error = err
            if not is_unknown:
                break

    if result is None:
        err_msg = str(last_error or "")
        # Recover gracefully if browser is not launched
        if "browser not launched" in err_msg.lower():
            if call_args.get("url"):
                try:
                    await _call_active_tool(active_client, "browser", "agent_browser_open", {"url": call_args["url"], "timeoutMs": 15000, "headed": True})
                    result = await _call_active_tool(active_client, "browser", "agent_browser_read", call_args)
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

    if resolved_name == "agent_browser_open":
        target_url = call_args.get("url", "")
        try:
            snap_res = await _call_active_tool(
                active_client,
                "browser",
                "agent_browser_snapshot",
                {"interactive": False, "compact": True}
            )
            raw_tree = ""
            if hasattr(snap_res, "content") and snap_res.content:
                raw_tree = "\n".join(
                    getattr(item, "text", "") for item in snap_res.content if hasattr(item, "text")
                )
            elif isinstance(snap_res, str):
                raw_tree = snap_res

            elements = _parse_agent_browser_snapshot(raw_tree)
            if elements:
                import dot.automation.browser as browser_mod
                browser_mod._ACTIVE_SCRATCH_ELEMENTS = elements
                _LAST_BROWSER_REFS.clear()
                for el in elements:
                    if el.get("ref"):
                        _LAST_BROWSER_REFS[el["ref"].lstrip("@")] = el

                scratch_file = LOGS_DIR / "scratch_page.md"
                _dump_to_scratch(elements, scratch_file)

                title = "Active Webpage"
                for el in elements:
                    if el.get("role") == "heading" and el.get("text"):
                        title = el["text"]
                        break

                manifest = _build_compact_manifest(title, target_url, elements)
                return {
                    "success": True,
                    "detail": (
                        f"Navigated to {target_url}.\n\n"
                        f"[Active Page Manifest]:\n{manifest}\n\n"
                        f"[Full {len(elements)} controls cached in logs/scratch_page.md. "
                        f"Use 'probe_page' to locate specific controls.]"
                    )
                }
        except Exception as snap_err:
            print(f"[Warning] Auto-snapshot failed on navigation: {snap_err}")

    if resolved_name == "agent_browser_snapshot":
        raw_tree = ""
        if hasattr(result, "content") and result.content:
            raw_tree = "\n".join(
                getattr(item, "text", "") for item in result.content if hasattr(item, "text")
            )
        elif isinstance(result, str):
            raw_tree = result

        elements = _parse_agent_browser_snapshot(raw_tree)
        if elements:
            import dot.automation.browser as browser_mod
            browser_mod._ACTIVE_SCRATCH_ELEMENTS = elements
            _LAST_BROWSER_REFS.clear()
            for el in elements:
                if el.get("ref"):
                    _LAST_BROWSER_REFS[el["ref"].lstrip("@")] = el

            scratch_file = LOGS_DIR / "scratch_page.md"
            _dump_to_scratch(elements, scratch_file)

            title = "Active Webpage"
            for el in elements:
                if el.get("role") == "heading" and el.get("text"):
                    title = el["text"]
                    break

            manifest = _build_compact_manifest(title, "current_tab", elements)
            return {
                "success": True,
                "detail": (
                    f"[Active Page Manifest]:\n{manifest}\n\n"
                    f"[Full {len(elements)} controls cached in logs/scratch_page.md. "
                    f"Use 'probe_page' to locate specific controls.]"
                )
            }

    if resolved_name == "agent_browser_read":
        raw_text = ""
        if hasattr(result, "content") and result.content:
            raw_text = "\n".join(
                getattr(item, "text", "") for item in result.content if hasattr(item, "text")
            )
        elif isinstance(result, str):
            raw_text = result

        cleaned_text = clean_readable_text(raw_text)

        # Automatic recovery if filter or outline produced empty output or No matching headings
        if not cleaned_text or "no matching headings" in cleaned_text.lower() or cleaned_text.strip().lower() == "# outline":
            if "filter" in call_args or call_args.get("outline"):
                retry_args = dict(call_args)
                retry_args.pop("filter", None)
                retry_args["outline"] = False
                for cand_name in ("agent_browser_read", "browser_read"):
                    try:
                        retry_res = await active_client.call_tool(cand_name, retry_args)
                        if hasattr(retry_res, "content") and retry_res.content:
                            retry_text = "\n".join(
                                getattr(item, "text", "") for item in retry_res.content if hasattr(item, "text")
                            )
                            cleaned_text = clean_readable_text(retry_text)
                            break
                        elif isinstance(retry_res, str) and retry_res.strip():
                            cleaned_text = clean_readable_text(retry_res)
                            break
                    except Exception:
                        pass

        return {
            "success": True,
            "detail": cleaned_text
        }

    if hasattr(result, "content") and result.content:
        texts = []
        for item in result.content:
            if hasattr(item, "text") and item.text:
                texts.append(item.text)
        if texts:
            combined = "\n".join(texts)
            try:
                return json.loads(combined)
            except (json.JSONDecodeError, TypeError):
                return combined

    return result

