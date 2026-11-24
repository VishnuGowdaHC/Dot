"""
Context builder, turn history manager, and token usage telemetry emitter.
"""

import asyncio
import json
import re
from typing import List, Dict, Optional, Tuple, Any

from dot.core.prompts import get_system_prompt
from dot.core.utils import render_history, async_compress_history, log_agent_context

STREAM_CHUNK_SIZE = 16
MAX_LOOP_TOKENS = 3500

SERVICE_MAP = {
    "github": "GitHub API (search repos/commits/code)",
    "browser": "browser automation/YouTube/web search",
    "os_tools": "OS management/processes",
    "native": "local session memory only",
    "sandbox": "isolated container (shell CLI, test runs, sandboxed browser, git)",
}


def build_turn_context(
    query: str,
    session: Any,
    available_services: List[str],
    speculative_tools: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Builds initial context history and system prompt with speculative tools."""
    from dot.memory.vector_store import format_compact_tool
    from dot.memory.rolling_memory import get_rolling_memory

    compact_lines = [format_compact_tool(t) for t in (speculative_tools or [])]
    tools_context_text = "\n".join(compact_lines)

    active_history_context = session.get_context_string() if session else ""
    services_text = "\n".join([f"- {s}: {SERVICE_MAP.get(s, 'additional tools')}" for s in available_services])

    tools_block = (
        f"<CURRENT_CONTEXT_TOOLS>\n{tools_context_text}\n</CURRENT_CONTEXT_TOOLS>\n"
        if tools_context_text else ""
    )

    rolling_mem = get_rolling_memory()
    ledger_text = rolling_mem.render_context() if (rolling_mem and rolling_mem.goal) else ""
    ledger_block = (
        f"<ACTIVE_GOAL_LEDGER>\n{ledger_text}\n</ACTIVE_GOAL_LEDGER>\n"
        if ledger_text else ""
    )

    history_parts = [{
        "role": "context",
        "text": f"""
            <AVAILABLE_TOOL_SERVICES>\n{services_text or 'None registered.'}\n</AVAILABLE_TOOL_SERVICES>
            {tools_block}{ledger_block}<PREVIOUS_SESSION_CONTEXT>\n{active_history_context or 'No previous history.'}\n</PREVIOUS_SESSION_CONTEXT>
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
    sys_tokens: Optional[int] = None,
    prompt_tokens: Optional[int] = None,
) -> None:
    """Calculates active context tokens including system prompt and emits telemetry."""
    if not websocket or not session:
        return
    try:
        if sys_tokens is None:
            sys_text = f"<|think|> {custom_system_prompt or get_system_prompt()}"
            sys_tokens = session.count_tokens(sys_text)
        if prompt_tokens is None:
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


async def stream_response(websocket: Any, text: str, thoughts: Optional[str] = None) -> str:
    """Sends model response over WebSocket without artificial sleep delays."""
    if not websocket:
        return text

    await websocket.send_text(json.dumps({"type": "stream_start", "thoughts": thoughts}))
    for i in range(0, len(text), STREAM_CHUNK_SIZE):
        chunk = text[i:i + STREAM_CHUNK_SIZE]
        await websocket.send_text(json.dumps({"type": "stream", "data": chunk}))
    await websocket.send_text(json.dumps({"type": "stream_end", "thoughts": thoughts}))
    return text


async def compress_if_needed(
    history_parts: List[Dict[str, Any]],
    session: Any,
    custom_system_prompt: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Compresses unpinned history when total tokens exceed the context limit."""
    if not session:
        return history_parts

    sys_text = f"<|think|> {custom_system_prompt or get_system_prompt()}"
    sys_tokens = await asyncio.to_thread(session.count_tokens, sys_text)
    hist_tokens = await asyncio.to_thread(session.count_tokens, render_history(history_parts))
    total_tokens = sys_tokens + hist_tokens

    # Reserve 2000 tokens for model output generation within the context limit.
    generation_reserve = 2000
    safe_limit = max(session.context_size - generation_reserve, MAX_LOOP_TOKENS)

    if total_tokens > safe_limit:
        target_hist = max(safe_limit - sys_tokens, 1500)
        return await async_compress_history(history_parts, session, target_tokens=target_hist)
    return history_parts


def format_thought_headline(
    thought: Optional[str] = None,
    action: Optional[str] = None,
    tool_name: Optional[str] = None,
) -> str:
    """Formats an objective status headline from step telemetry."""
    if action == "Tool-exec" and tool_name:
        clean_name = tool_name.replace("_", " ").title()
        return f"Executing {clean_name}..."
    if action == "Tool":
        return "Searching available tools..."
    if not thought:
        return "Thinking..."

    cleaned = thought.strip()
    leak_patterns = [
        r"as per the persona",
        r"as per persona",
        r"per the persona",
        r"system prompt",
        r"with a witty and sarcastic",
        r"witty and sarcastic",
        r"persona",
    ]
    for pattern in leak_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    headline = cleaned.split(".")[0].split("\n")[0].strip()
    headline = re.sub(r"\s+", " ", headline).strip(" -:;,")
    if not headline:
        return "Thinking..."
    if len(headline) > 45:
        headline = headline[:42] + "..."
    return headline


async def prepare_step_context(
    websocket: Any,
    query: str,
    step: int,
    history_parts: List[Dict[str, Any]],
    session: Any,
    custom_system_prompt: Optional[str],
) -> Tuple[List[Dict[str, Any]], str, int]:
    """Compresses history, emits telemetry once, logs context, and returns prompt and token count."""
    history_parts = await compress_if_needed(history_parts, session, custom_system_prompt)
    prompt = render_history(history_parts)
    if session is None:
        return history_parts, prompt, len(prompt) // 4

    active_prompt = custom_system_prompt or get_system_prompt()
    sys_tok = await asyncio.to_thread(session.count_tokens, f"<|think|> {active_prompt}")
    hist_tok = await asyncio.to_thread(session.count_tokens, prompt)
    await emit_token_telemetry(
        websocket, session, custom_system_prompt, history_parts,
        sys_tokens=sys_tok, prompt_tokens=hist_tok,
    )
    await asyncio.to_thread(
        log_agent_context,
        query=query,
        step=step + 1,
        history_parts=history_parts,
        system_prompt=active_prompt,
        total_tokens=sys_tok + hist_tok,
        context_limit=session.context_size,
    )
    return history_parts, prompt, hist_tok


async def init_turn_context(
    websocket: Any,
    query: str,
    session: Any,
    speculative_tools: Optional[list] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Retrieves speculative tools, builds initial turn context, and emits initial telemetry."""
    from dot.memory.vector_store import get_all_services, get_speculative_tools

    if speculative_tools is None:
        try:
            speculative_tools = await asyncio.to_thread(get_speculative_tools, query, 3)
        except Exception:
            speculative_tools = []
    available_services = await asyncio.to_thread(get_all_services)
    history_parts, sys_prompt = build_turn_context(
        query=query, session=session, available_services=available_services, speculative_tools=speculative_tools,
    )
    await emit_token_telemetry(websocket, session, sys_prompt, history_parts)
    return history_parts, sys_prompt


async def send_ws_event(websocket: Any, payload: Dict[str, Any]) -> None:
    """Sends a JSON event over the WebSocket and ignores disconnect errors."""
    if not websocket:
        return
    try:
        await websocket.send_text(json.dumps(payload))
    except Exception:
        pass


_ACTIVE_CLARIFICATIONS: Dict[str, asyncio.Future] = {}


def resolve_clarification(clarification_id: str, answer: str) -> bool:
    """Resolves an active clarification future to resume the ReAct loop."""
    future = _ACTIVE_CLARIFICATIONS.get(clarification_id)
    if future and not future.done():
        future.set_result(answer)
        return True
    return False


async def request_user_clarification(
    websocket: Any,
    question: str,
    choices: List[str],
    collected_thoughts: list,
) -> str:
    """Pauses the ReAct loop for user clarification and returns the reply."""
    import uuid
    clarification_id = str(uuid.uuid4())
    collected_thoughts.append(f"Awaiting user clarification: {question}")
    future = asyncio.get_running_loop().create_future()
    _ACTIVE_CLARIFICATIONS[clarification_id] = future
    await send_ws_event(websocket, {
        "type": "clarification_request",
        "data": {"id": clarification_id, "question": question, "choices": choices},
    })
    try:
        return await asyncio.wait_for(future, timeout=120.0)
    except asyncio.TimeoutError:
        return "No response provided by user within timeout."
    finally:
        _ACTIVE_CLARIFICATIONS.pop(clarification_id, None)


async def synthesize_from_observations(
    history_parts: list,
    schema: dict,
    directive: str,
    llm_fn: Any,
    extract_fn: Any,
    parse_fn: Any,
) -> Optional[str]:
    """Attempts final answer synthesis from gathered observations."""
    synth_history = list(history_parts) + [{"role": "thought", "text": directive, "pinned": False}]
    try:
        raw = await llm_fn(render_history(synth_history), schema=schema)
        ext = extract_fn(raw)
        if ext:
            parsed = parse_fn(ext)
            if parsed.final_answer and parsed.final_answer != "...":
                return parsed.final_answer
    except Exception:
        pass
    return None

