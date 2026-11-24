"""
ReAct loop engine for the Dot assistant.
Coordinates context construction, model inference, tool execution, and response streaming.
"""

import asyncio
import json
import re
import time
import uuid
from typing import Optional, Any, Dict

from dot.core.parser import AgentStep, extract_json, parse_agent_step, normalize_choice_text
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
)
from dot.core.llm import async_llm
from dot.core.utils import render_history, log_agent_context, prune_obsolete_observations
from dot.memory.vector_store import get_all_services, get_speculative_tools
from dot.memory.rolling_memory import get_rolling_memory

# Global registry for active human-in-the-loop clarifications.
_ACTIVE_CLARIFICATIONS: Dict[str, asyncio.Future] = {}

PROMISE_PATTERNS = [
    r"\bi (?:will|shall|am going to)(?: now)? (?:paste|type|open|launch|start|click|fill|save|create|extract|run|execute|read)\b",
    r"\bnow (?:pasting|opening|typing|launching|starting|saving|clicking|extracting)\b",
    r"\blet me (?:now )?(?:paste|open|launch|type|start|click|save|run|extract)\b",
    r"\bi (?:will|shall|am going to) proceed to\b",
]

DELIVERY_TOOLS = {
    "browser_fill",
    "agent_browser_fill",
    "os_keyboard_type",
    "os_tools_os_keyboard_type",
    "write_file",
    "sandbox_write_file",
}

NON_DELIVERY_DESTINATIONS = {
    "chat", "here", "short", "detail", "english", "brief", "words", "sentences",
    "bullet", "bullets", "point", "points", "mind", "advance", "future", "return",
    "fact", "facts", "summary", "response", "reply",
}


def extract_delivery_destination(query: str) -> Optional[str]:
    """Extracts external target surface from user query without hardcoding application names.

    Matches action phrases like:
      - 'paste it in notepad' -> 'notepad'
      - 'type this into vscode' -> 'vscode'
      - 'fill it in the search box' -> 'the search box'
      - 'save it to summary.txt' -> 'summary.txt'
    Complies with ASD-STE100 rules.
    """
    if not query:
        return None

    pattern = r"\b(?:paste|type|fill|save|write|put|enter|insert)\s+(?:it|this|that|the\s+text|the\s+summary|the\s+code|content|everything|data)?\s*(?:in|into|to)\s+([a-zA-Z0-9_\-\.\s]{2,30})"
    match = re.search(pattern, query, re.IGNORECASE)
    if not match:
        return None

    candidate = match.group(1).strip()
    tokens = candidate.split()
    if not tokens:
        return None

    first_token = tokens[0].lower().rstrip(".,;:")
    if first_token in NON_DELIVERY_DESTINATIONS:
        return None

    if tokens[0].lower() in ("the", "a", "an") and len(tokens) > 1:
        return f"{tokens[0]} {tokens[1]}".lower().rstrip(".,;:")

    return first_token


def check_unfulfilled_delivery(query: str, executed_tool_names: set) -> Optional[str]:
    """Verifies that an external delivery request executed before allowing Final action.

    Complies with ASD-STE100 rules.
    """
    dest = extract_delivery_destination(query)
    if not dest:
        return None

    has_delivered = any(t in DELIVERY_TOOLS for t in executed_tool_names)
    if not has_delivered:
        return (
            f"[System Directive: The user instruction requested delivering output to '{dest}'. "
            "You have generated or retrieved content, but you have not delivered it to the target surface yet. "
            "Determine where you are typing (web input vs desktop application) and execute the appropriate delivery tool before emitting Final.]"
        )
    return None


def check_action_promises(text: str) -> bool:
    """Detects unexecuted future action promises in model output text.

    Complies with ASD-STE100 rules.
    """
    if not text:
        return False
    lower = text.lower()
    return any(bool(re.search(pat, lower)) for pat in PROMISE_PATTERNS)


def resolve_clarification(clarification_id: str, answer: str) -> bool:
    """Resolves an active clarification future to resume the ReAct loop.

    Complies with ASD-STE100 rules.
    """
    future = _ACTIVE_CLARIFICATIONS.get(clarification_id)
    if future and not future.done():
        future.set_result(answer)
        return True
    return False


def format_thought_headline(
    thought: Optional[str] = None,
    action: Optional[str] = None,
    tool_name: Optional[str] = None,
) -> str:
    """Format an objective status headline from step telemetry.

    Complies with ASD-STE100 rules.
    """
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

    rolling_mem = get_rolling_memory()
    rolling_mem.set_goal(query)

    executed_signatures = set()
    executed_tool_names = set()
    last_tool_sig = None
    loop_strikes = 0
    browser_used = False
    collected_thoughts: list[str] = []

    async def finish_turn(text: str) -> str:
        # Keep the browser open on the desktop for user inspection.
        # Omit raw thought dumps to prevent leaking prompts to the chat completion stream.
        return await stream_response(websocket, text, thoughts=None)

    # Enforce safe upper bound on steps to prevent runaway loops (default 10, max 12)
    effective_max_steps = min(max_steps or 10, 12)
    step = 0
    raw_failures = 0
    consecutive_tool_failures = 0
    while step < effective_max_steps:
        # Ephemeral Observation Pruning: condense older DOM snapshots to keep context under 2,200 tokens
        history_parts = prune_obsolete_observations(history_parts)

        # Compress older steps if unpinned tokens exceed threshold
        history_parts = await compress_if_needed(history_parts, session, custom_system_prompt)

        # Emit active token telemetry for this step
        await emit_token_telemetry(websocket, session, custom_system_prompt, history_parts)

        # Log complete context snapshot to agent_context.log
        if session is not None:
            active_prompt = custom_system_prompt or ""
            sys_tok = session.count_tokens(f"<|think|> {active_prompt}")
            hist_tok = session.count_tokens(render_history(history_parts))
            log_agent_context(
                query=query,
                step=step + 1,
                history_parts=history_parts,
                system_prompt=active_prompt,
                total_tokens=sys_tok + hist_tok,
                context_limit=session.context_size,
            )

        prompt = render_history(history_parts)
        llm_start_time = time.time()
        try:
            raw = await async_llm(prompt, schema=schema, system_prompt=custom_system_prompt)
        except Exception as llm_err:
            fallback = f"Connection to the local model server failed: {llm_err}."
            await record_session_turn(session, query, fallback)
            return await finish_turn(fallback)

        llm_duration_ms = round((time.time() - llm_start_time) * 1000)
        prompt_tokens = session.count_tokens(prompt) if session else len(prompt) // 4
        output_tokens = len(raw) // 4
        tps = round(output_tokens / (llm_duration_ms / 1000), 1) if llm_duration_ms > 0 else 0.0

        if websocket:
            try:
                await websocket.send_text(json.dumps({
                    "type": "hop_telemetry",
                    "data": {
                        "hop": step + 1,
                        "duration_ms": llm_duration_ms,
                        "tokens_per_sec": tps,
                        "prompt_tokens": prompt_tokens,
                        "output_tokens": output_tokens,
                    }
                }))
            except Exception:
                pass

        extracted = extract_json(raw)
        if not extracted:
            print(f"[Engine Warning] Failed to extract JSON from raw model output: {raw!r}")
            raw_failures += 1
            if raw_failures < 3:
                append_or_update_error(
                    history_parts,
                    "[Output was not valid JSON. Emit ONLY a single JSON object with 'thought', 'action', 'tool_service', and 'payload'.]"
                )
                step += 1
                continue
            fallback = "I encountered an internal error processing that. Please try rephrasing."
            await record_session_turn(session, query, fallback)
            return await finish_turn(fallback)
        raw_failures = 0

        try:
            step_obj = parse_agent_step(extracted)
        except Exception as val_err:
            append_or_update_error(history_parts, f"[Invalid JSON: {val_err}. Retry with valid JSON.]")
            step += 1
            continue

        if not step_obj.action:
            append_or_update_error(
                history_parts,
                "[Incomplete step: 'action' is required. Specify action='Tool-exec' with payload, or action='Final' with final_answer.]"
            )
            step += 1
            continue

        # Format and display step telemetry cleanly in the console
        step_label = f"{step + 1}/{max_steps}" if max_steps else f"{step + 1}"
        print(f"\n--- [ReAct Step {step_label}] ---")
        headline = format_thought_headline(step_obj.thought, step_obj.action, step_obj.tool_name)
        if step_obj.thought:
            print(f"[Thought] {step_obj.thought}")
            collected_thoughts.append(headline)
            if websocket:
                try:
                    await websocket.send_text(json.dumps({
                        "type": "agent_action",
                        "data": {
                            "headline": headline,
                            "thought": headline,
                            "action": step_obj.action,
                            "tool_name": step_obj.tool_name,
                        }
                    }))
                except Exception:
                    pass

        history_parts.append({"role": "model", "text": extracted, "pinned": False})
        if step_obj.thought:
            history_parts.append({"role": "thought", "text": f"[Thought]: {step_obj.thought}", "pinned": False})

        # 1. Final Answer Action
        if step_obj.action == "Final" and step_obj.final_answer and step_obj.final_answer != "...":
            # Action Promise Interceptor: prevent premature Final with unexecuted tool promises
            if check_action_promises(step_obj.final_answer) and (max_steps is None or step < (max_steps - 1)):
                print(f"[Promise Interceptor] Detected future action promise in final_answer: {step_obj.final_answer[:80]}")
                append_or_update_error(
                    history_parts,
                    "[System Directive: You stated you will perform an action in final_answer, but you have not executed the tool yet. "
                    "Do not promise future actions in final_answer. Execute the tool immediately using action='Tool-exec'.]"
                )
                step += 1
                continue

            # Generic Delivery Sink Guard: prevent premature Final when an external destination was requested
            delivery_warning = check_unfulfilled_delivery(query, executed_tool_names)
            if delivery_warning and (max_steps is None or step < (max_steps - 1)):
                print(f"[Delivery Guard] Intercepted premature Final: unfulfilled delivery sink requested in query.")
                append_or_update_error(history_parts, delivery_warning)
                step += 1
                continue

            ans = step_obj.final_answer
            print(f"[Final Answer] {ans}")
            await record_session_turn(session, query, ans)
            if rolling_mem:
                rolling_mem.clear()
            return await finish_turn(ans)

        # 2. Clarification Action (Human-in-the-Loop Pause & Resume)
        elif step_obj.action == "Clarify":
            # Action Promise Interceptor on Clarify: prevent model from asking confirmation on planned actions
            clarify_text = f"{step_obj.question or ''} {step_obj.thought or ''}"
            is_promise = check_action_promises(clarify_text)
            has_trivial_choices = bool(
                step_obj.choices and any(
                    normalize_choice_text(c).lower() in ("ok", "yes", "proceed", "continue")
                    for c in step_obj.choices
                )
            )
            if (is_promise or has_trivial_choices) and (max_steps is None or step < (max_steps - 1)):
                print(f"[Promise Interceptor] Intercepted action promise inside Clarify: {clarify_text[:80]}")
                append_or_update_error(
                    history_parts,
                    "[System Directive: Do not emit Clarify to announce or confirm your planned actions. "
                    "Execute the required tool immediately using action='Tool-exec'.]"
                )
                step += 1
                continue

            # Intercept invalid clarification when content is already present in conversation context or observations
            has_prior_content = bool(session and session.get_context_string() and len(session.get_context_string().strip()) > 40)
            has_retrieved_data = any(
                p.get("role") == "observation" and len(p.get("text", "")) > 40
                for p in history_parts
            )
            is_delivery_or_pronoun = bool(
                extract_delivery_destination(query) or
                any(p in query.lower() for p in ("paste", "type", "fill", "save", "this", "that", "it"))
            )
            if (has_prior_content or has_retrieved_data) and is_delivery_or_pronoun and (max_steps is None or step < (max_steps - 1)):
                print(f"[Clarification Interceptor] Intercepted premature Clarify when prior context or observation contains required content.")
                append_or_update_error(
                    history_parts,
                    "[System Directive: Do not request clarification. The content to deliver is already available in the observations or history. "
                    "Determine where you are typing (web input vs desktop application) and execute the delivery tool immediately.]"
                )
                step += 1
                continue

            clarification_id = str(uuid.uuid4())
            clarify_question = step_obj.question or step_obj.thought or "Please clarify your request."
            print(f"[Clarification Request] {clarify_question} (ID: {clarification_id})")
            collected_thoughts.append(f"Awaiting user clarification: {clarify_question}")

            future = asyncio.get_event_loop().create_future()
            _ACTIVE_CLARIFICATIONS[clarification_id] = future

            if websocket:
                try:
                    await websocket.send_text(json.dumps({
                        "type": "clarification_request",
                        "data": {
                            "id": clarification_id,
                            "question": clarify_question,
                            "choices": [
                                normalize_choice_text(c)
                                for c in (step_obj.choices or [])
                                if normalize_choice_text(c)
                            ],
                        }
                    }))
                except Exception:
                    pass

            try:
                user_reply = await asyncio.wait_for(future, timeout=120.0)
            except asyncio.TimeoutError:
                user_reply = "No response provided by user within timeout."
            finally:
                _ACTIVE_CLARIFICATIONS.pop(clarification_id, None)

            print(f"[User Clarification Received] {user_reply}")
            history_parts.append({
                "role": "observation",
                "text": f"[User Clarification]: {user_reply}",
                "pinned": False,
            })
            if rolling_mem:
                rolling_mem.add_step(f"Clarified: {clarify_question[:60]}", str(user_reply)[:80])

        # 3. Tool Discovery Action
        elif step_obj.action == "Tool":
            print(f"[Discovery Search] {step_obj.tool_service} -> '{step_obj.get_tool}'")
            collected_thoughts.append(f"Searching tools for: {step_obj.get_tool}")
            res = await execute_tool_discovery(step_obj, history_parts, executed_signatures)
            if res.tripped_circuit_breaker:
                fallback = "I cannot find the required tools to complete this request."
                await record_session_turn(session, query, fallback)
                return await finish_turn(fallback)

        # 4. Tool Execution Action
        elif step_obj.action == "Tool-exec":
            if step_obj.tool_name:
                executed_tool_names.add(step_obj.tool_name)
            print(f"[Tool Action] {step_obj.tool_service}.{step_obj.tool_name}({step_obj.tool_args or {}})")
            collected_thoughts.append(f"Action: {step_obj.tool_name}")
            if websocket:
                try:
                    tool_headline = format_thought_headline(None, "Tool-exec", step_obj.tool_name)
                    await websocket.send_text(json.dumps({
                        "type": "agent_action",
                        "data": {
                            "headline": tool_headline,
                            "thought": tool_headline,
                            "action": "Tool-exec",
                            "tool_name": step_obj.tool_name,
                        }
                    }))
                except Exception:
                    pass
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
                max_steps=effective_max_steps,
            )
            if res.observation:
                obs_prev = res.observation.replace("\n", " ")[:100]
                print(f"[Observation] {obs_prev}...")
                if "failed to execute" in res.observation.lower():
                    consecutive_tool_failures += 1
                else:
                    consecutive_tool_failures = 0
                if rolling_mem:
                    rolling_mem.add_step(f"{step_obj.tool_name}", obs_prev)

            if consecutive_tool_failures >= 3:
                print(f"[Circuit Breaker] Tripped: 3 consecutive tool failures detected.")
                res.tripped_circuit_breaker = True
            if res.browser_used:
                browser_used = True

            if res.is_terminal:
                is_continuous = any(
                    w in query.lower()
                    for w in ["quiz", "all questions", "each question", "multi", "fill all", "step by step", "continuous", "attend"]
                )
                if is_continuous:
                    history_parts.append({
                        "role": "observation",
                        "text": f"[Action Completed]: {res.terminal_message}. Proceed with next action or question.",
                        "pinned": False,
                    })
                else:
                    await record_session_turn(session, query, res.terminal_message)
                    return await finish_turn(res.terminal_message)

            if res.tripped_circuit_breaker:
                has_obs = any(h.get("role") == "observation" and "failed to execute" not in h.get("text", "").lower() for h in history_parts)
                if has_obs:
                    synth_history = list(history_parts)
                    synth_history.append({
                        "role": "thought",
                        "text": "[System: Tool loop stopped by circuit breaker. Synthesize a concise final answer using only the successful observations gathered so far.]",
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
                fallback = "Tool execution limit reached. I could not complete the operation."
                await record_session_turn(session, query, fallback)
                return await finish_turn(fallback)

        step += 1

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

