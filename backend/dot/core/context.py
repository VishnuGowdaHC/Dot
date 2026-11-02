"""
Context builder, turn history manager, and token usage telemetry emitter.
"""

import asyncio
import json
from typing import List, Dict, Optional, Tuple, Any

from dot.core.prompts import get_system_prompt
from dot.core.utils import render_history, async_compress_history

STREAM_CHUNK_SIZE = 16
STREAM_DELAY = 0.002
MAX_LOOP_TOKENS = 3500

SERVICE_MAP = {
    "github": "GitHub API (search repos/commits/code)",
    "browser": "browser automation/YouTube/web search",
    "os_tools": "OS management/processes",
    "native": "local session memory only",
}


def build_turn_context(
    query: str,
    session: Any,
    available_services: List[str],
    speculative_tools: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Builds initial context history and system prompt with speculative tools."""
    from dot.memory.vector_store import format_compact_tool

    compact_lines = [format_compact_tool(t) for t in (speculative_tools or [])]
    tools_context_text = "\n".join(compact_lines)

    active_history_context = session.get_context_string() if session else ""
    services_text = "\n".join([f"- {s}: {SERVICE_MAP.get(s, 'additional tools')}" for s in available_services])

    tools_block = (
        f"<CURRENT_CONTEXT_TOOLS>\n{tools_context_text}\n</CURRENT_CONTEXT_TOOLS>\n"
        if tools_context_text else ""
    )

    history_parts = [{
        "role": "context",
        "text": f"""
            <AVAILABLE_TOOL_SERVICES>\n{services_text or 'None registered.'}\n</AVAILABLE_TOOL_SERVICES>
            {tools_block}<PREVIOUS_SESSION_CONTEXT>\n{active_history_context or 'No previous history.'}\n</PREVIOUS_SESSION_CONTEXT>
            <CURRENT_QUERY>\nuser: {query}\n</CURRENT_QUERY>
            """,
        "pinned": True,
    }]

    custom_system_prompt = get_system_prompt(tools_context_text) if tools_context_text else get_system_prompt()
    return history_parts, custom_system_prompt


async def emit_token_telemetry(
    websocket: Any,
    session: Any,
    custom_system_prompt: Optional[str],
    history_parts: List[Dict[str, Any]],
) -> None:
    """Calculates active context tokens including system prompt and emits telemetry."""
    if not websocket or not session:
        return
    try:
        sys_text = f"<|think|> {custom_system_prompt or get_system_prompt()}"
        sys_tokens = session.count_tokens(sys_text)
        prompt_text = render_history(history_parts)
        prompt_tokens = session.count_tokens(prompt_text)
        total = sys_tokens + prompt_tokens
        limit = session.context_size
        pct = round((total / limit) * 100, 1) if limit > 0 else 0

        await websocket.send_text(json.dumps({
            "type": "token_usage",
            "data": {
                "total_tokens": total,
                "context_limit": limit,
                "system_tokens": sys_tokens,
                "history_tokens": prompt_tokens,
                "compaction_threshold": session.compaction_threshold,
                "percentage": pct,
            }
        }))
    except Exception:
        pass


def append_or_update_error(history_parts: List[Dict[str, Any]], error_msg: str) -> None:
    """Updates the last error block instead of creating redundant error entries."""
    if history_parts and history_parts[-1].get("role") == "error":
        history_parts[-1]["text"] = error_msg
    else:
        history_parts.append({"role": "error", "text": error_msg, "pinned": False})


async def record_session_turn(session: Any, query: str, answer: str) -> None:
    """Appends turn to session storage and awaits compaction when needed."""
    if session is not None:
        task = session.add_turn(query, answer)
        if task is not None:
            try:
                await task
            except Exception:
                pass


async def stream_response(websocket: Any, text: str) -> str:
    """Sends model response in small WebSocket chunks for genuine streaming."""
    if not websocket:
        return text

    await websocket.send_text(json.dumps({"type": "stream_start"}))
    for i in range(0, len(text), STREAM_CHUNK_SIZE):
        chunk = text[i:i + STREAM_CHUNK_SIZE]
        await websocket.send_text(json.dumps({"type": "stream", "data": chunk}))
        if STREAM_DELAY > 0:
            await asyncio.sleep(STREAM_DELAY)
    await websocket.send_text(json.dumps({"type": "stream_end"}))
    return text


async def compress_if_needed(
    history_parts: List[Dict[str, Any]],
    session: Any,
) -> List[Dict[str, Any]]:
    """Compresses unpinned history when total tokens exceed the compaction threshold."""
    if not session:
        return history_parts

    current_tokens = session.count_tokens(render_history(history_parts))
    loop_limit = getattr(session, "compaction_threshold", MAX_LOOP_TOKENS)

    if current_tokens > loop_limit:
        return await async_compress_history(history_parts, session, target_tokens=loop_limit)
    return history_parts

