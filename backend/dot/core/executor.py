"""
Tool execution dispatcher, anti-loop circuit breaker, and observation formatter.
"""

import json
import re
import time
from typing import Dict, Any, List, Set, Optional, Tuple

from dot.core.parser import AgentStep
from dot.core.guardrails import check_guardrails
from dot.core.utils import dump_observation, trim_observation, log_tool_execution
from dot.core.context import append_or_update_error
from dot.memory.vector_store import get_relevant_tools
from dot.mcp.client import execute_mcp_tool
from dot.memory.collections.native_tools_collection import NATIVE_TOOLS

INSPECTION_TOOLS = {
    "browser_extract_text",
    "browser_snapshot",
    "browser_screenshot",
    "os_take_screenshot",
    "os_get_active_window",
}

STATE_CHANGING_TOOLS = {
    "browser_navigate",
    "browser_ai_background_load_page",
    "browser_open_in_browser",
    "browser_play_video",
    "browser_search_web",
    "browser_click",
    "browser_fill",
    "browser_press_key",
    "browser_select_option",
    "browser_scroll",
    "os_focus_window",
    "os_send_hotkey",
    "os_type_text",
    "os_click_at",
}


class ExecutionResult:
    """Carries tool execution output and control flags."""
    def __init__(
        self,
        observation: Optional[str] = None,
        is_terminal: bool = False,
        terminal_message: Optional[str] = None,
        should_retry: bool = False,
        tripped_circuit_breaker: bool = False,
        browser_used: bool = False,
    ):
        self.observation = observation
        self.is_terminal = is_terminal
        self.terminal_message = terminal_message
        self.should_retry = should_retry
        self.tripped_circuit_breaker = tripped_circuit_breaker
        self.browser_used = browser_used


async def execute_tool_discovery(
    step_obj: AgentStep,
    history_parts: List[Dict[str, Any]],
    executed_signatures: Set[str],
) -> ExecutionResult:
    """Executes tool discovery search and updates the found tools block."""
    error = check_guardrails(step_obj)
    if error:
        append_or_update_error(history_parts, f"[{error}]")
        return ExecutionResult(should_retry=True)

    discovery_sig = f"search_{step_obj.tool_service}_{step_obj.get_tool}"
    if discovery_sig in executed_signatures:
        append_or_update_error(
            history_parts,
            f"[Warning: You already searched for '{step_obj.get_tool}'. Use action='Tool-exec' with an available tool, or search with a different query.]"
        )
        return ExecutionResult(should_retry=True)

    executed_signatures.add(discovery_sig)
    results = get_relevant_tools(query=step_obj.get_tool, k=1, service_hint=step_obj.tool_service)

    if results:
        lines = []
        for t in results:
            schema_dict = t.get("schema", {})
            preserved_schema = {
                "properties": schema_dict.get("properties", {}),
                "required": schema_dict.get("required", []),
            }
            lines.append(f"- {t['tool_name']} via {t['tool_service']}: {json.dumps(preserved_schema)}")

        new_tools_text = "\n".join(lines)
        existing_tools_role = next((h for h in history_parts if h.get("role") == "tool_found"), None)
        rule_text = "[If the exact tool you need is listed above, use action='Tool-exec'. If the tool you need is MISSING, use action='Tool' to search again with a DIFFERENT query.]"

        if existing_tools_role:
            current_text = existing_tools_role["text"]
            clean_text = re.sub(r"\[If the exact tool you need.*\]", "", current_text).strip()
            if clean_text.endswith("]"):
                clean_text = clean_text[:-1].strip()

            existing_lines = set(clean_text.split("\n"))
            for line in new_tools_text.split("\n"):
                if line and line not in existing_lines:
                    clean_text += f"\n{line}"
                    existing_lines.add(line)

            existing_tools_role["text"] = f"{clean_text}\n]\n{rule_text}"
        else:
            history_parts.append({
                "role": "tool_found",
                "text": f"[Found tools:\n{new_tools_text}]\n{rule_text}",
                "pinned": True,
            })
    else:
        append_or_update_error(history_parts, f"[No tools found for '{step_obj.get_tool}'. Try a different search phrase.]")

    return ExecutionResult()


async def execute_tool_call(
    step_obj: AgentStep,
    step_num: int,
    query: str,
    session: Any,
    active_client: Any,
    history_parts: List[Dict[str, Any]],
    executed_signatures: Set[str],
    last_tool_sig: Optional[str],
    loop_strikes: int,
    max_steps: int,
) -> Tuple[ExecutionResult, Optional[str], int]:
    """Executes a target tool call with anti-loop protection and observation logging."""
    error = check_guardrails(step_obj)
    if error:
        append_or_update_error(history_parts, f"[{error}]")
        return ExecutionResult(should_retry=True), last_tool_sig, loop_strikes

    clean_args = {k: v for k, v in (step_obj.tool_args or {}).items() if v is not None}

    # Reject template placeholder parameters
    if any(isinstance(v, str) and re.search(r"<\w+>", v) for v in clean_args.values()):
        append_or_update_error(
            history_parts,
            "[Error: You used a placeholder like '<username>'. Use the actual values from the user's query.]"
        )
        return ExecutionResult(should_retry=True), last_tool_sig, loop_strikes

    # Circuit breaker: detect duplicate executions
    current_sig = f"{step_obj.tool_name}_{sorted(clean_args.items())}"
    is_inspection = step_obj.tool_name in INSPECTION_TOOLS

    is_duplicate = False
    if is_inspection:
        if current_sig == last_tool_sig:
            is_duplicate = True
    else:
        if current_sig in executed_signatures:
            is_duplicate = True

    if is_duplicate:
        loop_strikes += 1
        if loop_strikes <= 3:
            has_obs = any(h.get("role") == "observation" for h in history_parts)
            hint = (
                f"[Anti-Loop Warning (Attempt {loop_strikes}/3): You are calling '{step_obj.tool_name}' on the same page. Call 'browser_navigate' to read a different page or synthesize your answer with action='Final'.]"
                if is_inspection else
                f"[Anti-Loop Warning (Attempt {loop_strikes}/3): You already executed '{step_obj.tool_name}' with these arguments. {'Synthesize your final answer using action=\"Final\".' if has_obs else 'Try different arguments or another tool.'}]"
            )
            append_or_update_error(history_parts, hint)
            return ExecutionResult(should_retry=True), last_tool_sig, loop_strikes
        else:
            return ExecutionResult(tripped_circuit_breaker=True), last_tool_sig, loop_strikes

    loop_strikes = 0
    executed_signatures.add(current_sig)
    last_tool_sig = current_sig
    browser_used = False
    start_time = time.time()

    # Execute tool on native handler or FastMCP client
    if step_obj.tool_service == "native":
        fn = NATIVE_TOOLS.get(step_obj.tool_name)
        try:
            observation = fn(**clean_args) if fn else f"Native tool '{step_obj.tool_name}' not found."
        except Exception as e:
            observation = f"Native tool failed: {e}"
    else:
        if step_obj.tool_service == "browser":
            browser_used = True
        try:
            observation = await execute_mcp_tool(active_client, step_obj.tool_service, step_obj.tool_name, clean_args)
        except Exception as e:
            observation = f"Failed to execute tool '{step_obj.tool_name}': {e}."

    duration_sec = time.time() - start_time
    log_tool_execution(
        step=step_num,
        service=step_obj.tool_service,
        tool_name=step_obj.tool_name,
        tool_args=clean_args,
        observation=observation,
        duration_sec=duration_sec,
    )

    # Clear inspection signatures when state-changing actions execute
    if step_obj.tool_name in STATE_CHANGING_TOOLS:
        executed_signatures.difference_update({s for s in executed_signatures if any(s.startswith(t + "_") for t in INSPECTION_TOOLS)})
        last_tool_sig = None

    obs_dict = observation
    if isinstance(observation, str):
        try:
            obs_dict = json.loads(observation)
        except Exception:
            pass

    # Handle tools signaling terminal completion
    if isinstance(obs_dict, dict) and obs_dict.get("success") and obs_dict.get("terminal"):
        is_info_query = any(w in query.lower() for w in ["find", "search", "explain", "code", "example", "how", "what", "compare", "sample", "extract", "summarize", "look up", "docs"])
        if is_info_query and step_num < max_steps - 1:
            history_parts.append({
                "role": "observation",
                "text": f"\n[Observation from {step_obj.tool_name}]: {obs_dict.get('detail')}\n[Note: You opened an external desktop tab, but the user requested information/code. Use browser_navigate and browser_extract_text to read the docs and provide a complete answer.]",
                "source_tool": step_obj.tool_name,
                "pinned": False,
            })
            return ExecutionResult(browser_used=browser_used), last_tool_sig, loop_strikes
        else:
            final_msg = f"Done — {obs_dict.get('detail', 'action completed')}."
            return ExecutionResult(is_terminal=True, terminal_message=final_msg, browser_used=browser_used), last_tool_sig, loop_strikes

    log_path = dump_observation(observation, step_num, step_obj.tool_name)
    trimmed = trim_observation(observation, session)

    history_parts.append({
        "role": "observation",
        "text": f"\n[Observation from {step_obj.tool_name}]: {trimmed}\n[Full data saved: {log_path}]",
        "source_tool": step_obj.tool_name,
        "pinned": False,
    })

    return ExecutionResult(observation=trimmed, browser_used=browser_used), last_tool_sig, loop_strikes


async def cleanup_browser(active_client: Any) -> None:
    """Closes Playwright browser sessions after run completion."""
    if active_client:
        try:
            await execute_mcp_tool(active_client, "browser", "close_browser", {})
        except Exception:
            pass

