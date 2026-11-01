"""
ReAct loop engine for the Dot assistant.
Coordinates context construction, model inference, tool execution, and response streaming.
"""

import time
import uuid
from typing import Optional, Any

from dot.core.parser import AgentStep, extract_json, parse_agent_step
from dot.core.context import (
    build_turn_context,
    emit_token_telemetry,
    record_session_turn,
    stream_response,
    compress_if_needed,
    append_or_update_error,
)
from dot.core.executor import (
    execute_tool_discovery,
    execute_tool_call,
    cleanup_browser,
)
from dot.core.llm import async_llm
from dot.core.utils import render_history
from dot.memory.vector_store import get_all_services, get_speculative_tools


async def reAct_loop(
    websocket: Any,
    query: str,
    llm: Any = None,
    session: Any = None,
    active_client: Any = None,
    max_steps: int = 12,
    speculative_tools: Optional[list] = None,
) -> str:
    """Executes the autonomous ReAct cycle for a single user query."""
    schema = AgentStep.model_json_schema()

    # Pre-retrieve speculative tools if not already provided
    if speculative_tools is None:
        try:
            speculative_tools = get_speculative_tools(query, 3)
        except Exception:
            speculative_tools = []

    available_services = get_all_services()
    history_parts, custom_system_prompt = build_turn_context(
        query=query,
        session=session,
        available_services=available_services,
        speculative_tools=speculative_tools,
    )

    # Emit initial token telemetry for Turn 0
    await emit_token_telemetry(websocket, session, custom_system_prompt, history_parts)

    executed_signatures = set()
    last_tool_sig = None
    loop_strikes = 0
    browser_used = False

    async def finish_turn(text: str) -> str:
        if browser_used and active_client:
            await cleanup_browser(active_client)
        return await stream_response(websocket, text)

    for step in range(max_steps):
        # Compress older steps if unpinned tokens exceed threshold
        history_parts = await compress_if_needed(history_parts, session)

        # Emit active token telemetry for this step
        await emit_token_telemetry(websocket, session, custom_system_prompt, history_parts)

        prompt = render_history(history_parts)
        try:
            raw = await async_llm(prompt, schema=schema, system_prompt=custom_system_prompt)
        except Exception as llm_err:
            fallback = f"Connection to the local model server failed: {llm_err}."
            await record_session_turn(session, query, fallback)
            return await finish_turn(fallback)

        extracted = extract_json(raw)
        if not extracted:
            fallback = "I encountered an internal error processing that. Please try rephrasing."
            await record_session_turn(session, query, fallback)
            return await finish_turn(fallback)

        try:
            step_obj = parse_agent_step(extracted)
        except Exception as val_err:
            append_or_update_error(history_parts, f"[Invalid JSON: {val_err}. Retry with valid JSON.]")
            continue

        history_parts.append({"role": "model", "text": extracted, "pinned": False})
        if step_obj.thought:
            history_parts.append({"role": "thought", "text": f"[Thought]: {step_obj.thought}", "pinned": False})

        # 1. Final Answer Action
        if step_obj.action == "Final" and step_obj.final_answer and step_obj.final_answer != "...":
            ans = step_obj.final_answer
            await record_session_turn(session, query, ans)
            return await finish_turn(ans)

        # 2. Tool Discovery Action
        if step_obj.action == "Tool":
            res = await execute_tool_discovery(step_obj, history_parts, executed_signatures)
            if res.tripped_circuit_breaker:
                fallback = "I cannot find the required tools to complete this request."
                await record_session_turn(session, query, fallback)
                return await finish_turn(fallback)

        # 3. Tool Execution Action
        elif step_obj.action == "Tool-exec":
            res, last_tool_sig, loop_strikes = await execute_tool_call(
                step_obj=step_obj,
                step_num=step,
                query=query,
                session=session,
                active_client=active_client,
                history_parts=history_parts,
                executed_signatures=executed_signatures,
                last_tool_sig=last_tool_sig,
                loop_strikes=loop_strikes,
                max_steps=max_steps,
            )
            if res.browser_used:
                browser_used = True

            if res.is_terminal:
                await record_session_turn(session, query, res.terminal_message)
                return await finish_turn(res.terminal_message)

            if res.tripped_circuit_breaker:
                fallback = "Tool execution limit reached. I could not complete the operation."
                await record_session_turn(session, query, fallback)
                return await finish_turn(fallback)

    # Max steps reached: attempt final synthesis from gathered observations
    has_obs = any(h.get("role") == "observation" for h in history_parts)
    if has_obs:
        synth_history = list(history_parts)
        synth_history.append({
            "role": "thought",
            "text": "[System: Max steps reached. Synthesize a final answer from all observations now.]",
            "pinned": False,
        })
        try:
            raw_synth = await async_llm(render_history(synth_history), schema=schema)
            ext_synth = extract_json(raw_synth)
            if ext_synth:
                step_synth = parse_agent_step(ext_synth)
                if step_synth.final_answer and step_synth.final_answer != "...":
                    await record_session_turn(session, query, step_synth.final_answer)
                    return await finish_turn(step_synth.final_answer)
        except Exception:
            pass

    aborted = "Agent loop reached the maximum step limit without a final answer."
    await record_session_turn(session, query, aborted)
    return await finish_turn(aborted)

