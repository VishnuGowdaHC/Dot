"""
ReAct loop orchestrator for the Dot assistant.
Coordinates context construction, model inference, tool execution, and response streaming.
"""

import time
from typing import Optional, Any

from dot.core.parser import AgentStep, extract_json, parse_agent_step, normalize_choice_text
from dot.core.context import (
    _ACTIVE_CLARIFICATIONS, append_or_update_error, format_thought_headline,
    init_turn_context, prepare_step_context, record_session_turn,
    request_user_clarification, resolve_clarification, send_ws_event,
    stream_response, synthesize_from_observations,
)
from dot.core.executor import execute_tool_discovery, execute_tool_call
from dot.core.guardrails import check_action_promises, check_clarify_interception, check_unfulfilled_delivery, extract_delivery_destination
from dot.core.llm import async_llm
from dot.core.utils import prune_obsolete_observations
from dot.memory.rolling_memory import get_rolling_memory

CONTINUOUS_HINTS = ("quiz", "all questions", "each question", "multi", "fill all", "step by step", "continuous", "attend")


async def reAct_loop(
    websocket: Any,
    query: str,
    llm: Any = None,
    session: Any = None,
    active_client: Any = None,
    max_steps: Optional[int] = None,
    speculative_tools: Optional[list] = None,
) -> str:
    """Executes the autonomous ReAct cycle for a single user query."""
    schema = AgentStep.model_json_schema()
    history_parts, sys_prompt = await init_turn_context(websocket, query, session, speculative_tools)
    rolling_mem = get_rolling_memory()
    rolling_mem.set_goal(query)
    executed_signatures, executed_tool_names = set(), set()
    last_tool_sig, loop_strikes, collected_thoughts = None, 0, []
    effective_max_steps = min(max_steps or 10, 12)
    step = raw_failures = consecutive_failures = 0

    async def finish_turn(text: str) -> str:
        await record_session_turn(session, query, text)
        return await stream_response(websocket, text, thoughts=None)

    try:
        while step < effective_max_steps:
            history_parts = prune_obsolete_observations(history_parts)
            history_parts, prompt, prompt_tok = await prepare_step_context(
                websocket, query, step, history_parts, session, sys_prompt,
            )
            llm_start = time.time()
            try:
                raw = await async_llm(prompt, schema=schema, system_prompt=sys_prompt)
            except Exception as llm_err:
                return await finish_turn(f"Connection to the local model server failed: {llm_err}.")

            dur_ms = round((time.time() - llm_start) * 1000)
            out_tok = len(raw) // 4
            tps = round(out_tok / (dur_ms / 1000), 1) if dur_ms > 0 else 0.0
            await send_ws_event(websocket, {
                "type": "hop_telemetry",
                "data": {"hop": step + 1, "duration_ms": dur_ms, "tokens_per_sec": tps, "prompt_tokens": prompt_tok, "output_tokens": out_tok},
            })

            extracted = extract_json(raw)
            if not extracted:
                raw_failures += 1
                if raw_failures < 3:
                    append_or_update_error(history_parts, "[Output was not valid JSON. Emit ONLY one JSON object.]")
                    step += 1
                    continue
                return await finish_turn("I encountered an internal error processing that. Please try rephrasing.")
            raw_failures = 0

            try:
                step_obj = parse_agent_step(extracted)
            except Exception as val_err:
                append_or_update_error(history_parts, f"[Invalid JSON: {val_err}. Retry with valid JSON.]")
                step += 1
                continue

            if not step_obj.action:
                append_or_update_error(history_parts, "[Incomplete step: 'action' is required.]")
                step += 1
                continue

            headline = format_thought_headline(step_obj.thought, step_obj.action, step_obj.tool_name)
            if step_obj.thought:
                collected_thoughts.append(headline)
                await send_ws_event(websocket, {"type": "agent_action", "data": {"headline": headline, "thought": headline, "action": step_obj.action, "tool_name": step_obj.tool_name}})

            history_parts.append({"role": "model", "text": extracted, "pinned": False})
            if step_obj.thought:
                history_parts.append({"role": "thought", "text": f"[Thought]: {step_obj.thought}", "pinned": False})

            if step_obj.action == "Final":
                if not step_obj.final_answer or step_obj.final_answer == "...":
                    append_or_update_error(history_parts, "[System Directive: 'final_answer' must contain a non-empty response.]")
                elif check_action_promises(step_obj.final_answer) and (max_steps is None or step < max_steps - 1):
                    append_or_update_error(history_parts, "[System Directive: Do not promise future actions in final_answer. Execute the tool using action='Tool-exec'.]")
                elif (warn := check_unfulfilled_delivery(query, executed_tool_names)) and (max_steps is None or step < max_steps - 1):
                    append_or_update_error(history_parts, warn)
                else:
                    return await finish_turn(step_obj.final_answer)
            elif step_obj.action == "Clarify":
                intercept = check_clarify_interception(step_obj, query, session, history_parts, normalize_choice_text)
                if intercept and (max_steps is None or step < max_steps - 1):
                    append_or_update_error(history_parts, intercept)
                else:
                    q = step_obj.question or step_obj.thought or "Please clarify your request."
                    choices = [c for c in (normalize_choice_text(x) for x in (step_obj.choices or [])) if c]
                    reply = await request_user_clarification(websocket, q, choices, collected_thoughts)
                    history_parts.append({"role": "observation", "text": f"[User Clarification]: {reply}", "pinned": False})
                    if rolling_mem:
                        rolling_mem.add_step(f"Clarified: {q[:60]}", str(reply)[:80])
            elif step_obj.action == "Tool":
                res = await execute_tool_discovery(step_obj, history_parts, executed_signatures)
                if res.tripped_circuit_breaker:
                    return await finish_turn("I cannot find the required tools to complete this request.")
            elif step_obj.action == "Tool-exec":
                if step_obj.tool_name:
                    executed_tool_names.add(step_obj.tool_name)
                await send_ws_event(websocket, {"type": "agent_action", "data": {"headline": format_thought_headline(None, "Tool-exec", step_obj.tool_name), "thought": headline, "action": "Tool-exec", "tool_name": step_obj.tool_name}})
                res, last_tool_sig, loop_strikes = await execute_tool_call(
                    step_obj=step_obj, step_num=step, query=query, session=session, active_client=active_client,
                    history_parts=history_parts, executed_signatures=executed_signatures,
                    last_tool_sig=last_tool_sig, loop_strikes=loop_strikes, max_steps=effective_max_steps,
                )
                if res.observation:
                    obs_prev = res.observation.replace("\n", " ")[:100]
                    consecutive_failures = consecutive_failures + 1 if "failed to execute" in res.observation.lower() else 0
                    if rolling_mem:
                        rolling_mem.add_step(f"{step_obj.tool_name}", obs_prev)
                if consecutive_failures >= 3:
                    res.tripped_circuit_breaker = True
                if res.is_terminal:
                    if any(w in query.lower() for w in CONTINUOUS_HINTS):
                        history_parts.append({"role": "observation", "text": f"[Action Completed]: {res.terminal_message}. Proceed with next action.", "pinned": False})
                    else:
                        return await finish_turn(res.terminal_message)
                if res.tripped_circuit_breaker:
                    if any(h.get("role") == "observation" and "failed to execute" not in h.get("text", "").lower() for h in history_parts):
                        synth = await synthesize_from_observations(history_parts, schema, "[System: Tool loop stopped. Synthesize a concise final answer now.]", async_llm, extract_json, parse_agent_step)
                        if synth:
                            return await finish_turn(synth)
                    return await finish_turn("Tool execution limit reached. I could not complete the operation.")
            step += 1

        if any(h.get("role") == "observation" for h in history_parts):
            synth = await synthesize_from_observations(history_parts, schema, "[System: Max steps reached. Synthesize a final answer now.]", async_llm, extract_json, parse_agent_step)
            if synth:
                return await finish_turn(synth)
        return await finish_turn("Agent loop reached the maximum step limit without a final answer.")
    finally:
        if rolling_mem:
            rolling_mem.clear()
