from pydantic import BaseModel, field_validator, model_validator
from typing import Literal, Optional
import os
import time
import uuid
import asyncio
import json
import re

from src.dot.memory.vector_store import get_relevant_tools, get_all_services
from src.dot.core.gaurdrails import check_guardrails, _is_real_value 
from src.dot.mcp_files.mcpClient import execute_mcp_tool
from src.dot.memory.session_memory.manager import SessionStorage
from src.dot.memory.collections.native_tools_collection import NATIVE_TOOLS
from src.dot.core.llm import llm
from src.dot.core.utils import *  

# --- Debug Logger ---
DEBUG_LOG_FILE = "agent_debug.log"
CONTEXT_LOG_FILE = "agent_context.log"

def log_debug(message: str):
    """Prints to console AND appends to a debug log file."""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    formatted_msg = f"[{timestamp}] {message}"
    print(formatted_msg)
    try:
        with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted_msg + "\n")
    except Exception as e:
        print(f"[Log Error] Could not write to {DEBUG_LOG_FILE}: {e}")

def context_debug(message: str):
    """Prints to console AND appends to a debug log file."""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    formatted_msg = f"[{timestamp}] {message}"
    print(formatted_msg)
    try:
        with open(CONTEXT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted_msg + "\n")
    except Exception as e:
        print(f"[Log Error] Could not write to {CONTEXT_LOG_FILE}: {e}")


class AgentStep(BaseModel):
    thought: str
    action: Literal['Tool', 'Tool-exec', 'Final'] = None
    tool_service: Optional[str] = None
    payload: Optional[dict] = None  
    final_answer: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
    def remap_legacy_keys(cls, values: dict):
        if isinstance(values, dict) and not values.get('payload'):
            payload = {}
            action = values.get('action')
            
            if action == 'Tool':
                if values.get('get_tool'): payload['query'] = values.pop('get_tool')
                elif values.get('tool_name'): payload['query'] = values.pop('tool_name')
            else:
                if values.get('tool_name'): payload['name'] = values.pop('tool_name')
                if values.get('tool_args'):
                    t_args = values.pop('tool_args')
                    if isinstance(t_args, str):
                        try: t_args = json.loads(t_args)
                        except: t_args = {}
                    payload['args'] = t_args if isinstance(t_args, dict) else {}
                    
            if payload:
                values['payload'] = payload
        return values

    @property
    def get_tool(self):
        return self.payload.get("query") if self.payload and self.action == "Tool" else None
        
    @property
    def tool_name(self):
        return self.payload.get("name") if self.payload and self.action == "Tool-exec" else None

    @property
    def tool_args(self):
        return self.payload.get("args", {}) if self.payload and self.action == "Tool-exec" else {}
        
    @field_validator('payload', mode='before')
    @classmethod
    def parse_payload(cls, v):
        if isinstance(v, str):
            try: return json.loads(v)
            except: return {}
        return v or {}

def append_or_update_error(history_parts: list, error_msg: str):
    """Updates the last error instead of appending endless new ones."""
    if history_parts and history_parts[-1].get("role") == "error":
        history_parts[-1]["text"] = error_msg
    else:
        history_parts.append({"role": "error", "text": error_msg, "pinned": False})

MAX_LOOP_TOKENS = 6000

async def reAct_loop(websocket, query, llm, session: SessionStorage, active_client, max_steps=8):
    run_id = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    run_log_path = os.path.join(OBS_LOG_DIR, f"run_{run_id}.json")
    run_log = {"query": query, "steps": []}

    log_debug(f"\n{'='*40}\nSTARTING NEW RUN: {run_id}\nQUERY: {query}\n{'='*40}")

    schema = AgentStep.model_json_schema()
    
    # Leverages your robust sliding window for past context
    active_history_context = session.get_context_string() 
    available_services = get_all_services()

    SERVICE_MAP = {
        "github": "GitHub API (search repos/commits/code)",
        "browser": "browser automation/YouTube/web search",
        "os_tools": "OS management/processes",
        "native": "local session memory only"
    }
    services_text = "\n".join([f"- {s}: {SERVICE_MAP.get(s, 'additional tools')}" for s in available_services])

    history_parts = [{
        "role": "context",
        "text": f"""
            <AVAILABLE_TOOL_SERVICES>\n{services_text or 'None registered.'}\n</AVAILABLE_TOOL_SERVICES>
            <PREVIOUS_SESSION_CONTEXT>\n{active_history_context or "No previous history."}\n</PREVIOUS_SESSION_CONTEXT>
            <CURRENT_QUERY>\nuser: {query}\n</CURRENT_QUERY>
            """,
        "pinned": True,
    }]

    executed_signatures = set()

    for step in range(max_steps):
        log_debug(f"\n--- LOOP STEP {step} ---")

        # Fallback compression only if loop observations explode
        current_tokens = session.count_tokens(render_history(history_parts))
        if current_tokens > MAX_LOOP_TOKENS:
            log_debug(f"[WARNING] Token limit exceeded ({current_tokens} > {MAX_LOOP_TOKENS}). Compressing history...")
            history_parts = compress_history(history_parts, session)

        prompt = render_history(history_parts)
        context_debug(prompt)
      
        log_debug("Waiting for LLM generation...")
        raw = llm(prompt, schema=schema)
        log_debug(f"RAW LLM OUTPUT:\n{raw}")

        extracted = extract_json(raw)
        log_debug(f"EXTRACTED JSON:\n{extracted}")

        if extracted is None:
            log_debug("[CRITICAL]: Failed to extract any JSON from LLM output. Aborting.")
            fallback_msg = "I ran into an internal error processing that. Could you try rephrasing?"
            session.add_turn(query, fallback_msg)
            return await websocket.send_text(json.dumps({"type": "result", "data": fallback_msg}))

        try:
            step_obj = AgentStep.model_validate_json(extracted)
            log_debug(f"[PARSED AGENT STEP]: Action='{step_obj.action}', Service='{step_obj.tool_service}'")
        except Exception as e:
            error_msg = f"[Invalid JSON structure: {e}. Retry with valid JSON.]"
            log_debug(f"[JSON VALIDATION ERROR]: {e}")
            append_or_update_error(history_parts, error_msg)
            continue
        
        # Self-heal mislabeled actions
        if step_obj.action == 'Tool' and step_obj.payload and _is_real_value(step_obj.payload.get("name")):
            log_debug("[SELF-HEAL]: Action was 'Tool' but 'name' found in payload. Changing to 'Tool-exec'.")
            step_obj.action = 'Tool-exec'

        history_parts.append({"role": "model", "text": extracted, "pinned": False})

        if step_obj.thought:
            history_parts.append({"role": "thought", "text": f"[Thought]: {step_obj.thought}", "pinned": False})
            log_debug(f"[THOUGHT]: {step_obj.thought}")

        # 1. Final Answer
        if step_obj.action == 'Final' and step_obj.final_answer and step_obj.final_answer != "...":
            ans = step_obj.final_answer or "Task completed."
            log_debug(f"[FINAL ANSWER TRIGGERED]: {ans}")
            session.add_turn(query, ans)
            return await websocket.send_text(json.dumps({"type": "result", "data": ans}))

        # 2. Tool Discovery
        if step_obj.action == 'Tool':
            error = check_guardrails(step_obj)
            if error:
                log_debug(f"[GUARDRAIL BLOCKED TOOL DISCOVERY]: {error}")
                append_or_update_error(history_parts, f"[{error}]")
                continue
                
            discovery_sig = f"search_{step_obj.tool_service}_{step_obj.get_tool}"
            if discovery_sig in executed_signatures:
                

                log_debug(f"[ANTI-LOOP]: Caught duplicate tool discovery for '{step_obj.get_tool}'. Retry.")
                
                last_found = next((h for h in reversed(history_parts) if h.get("role") == "tool_found"), None)
                if last_found:
                    fallback_msg = "I'm having trouble figuring out how to use the available tools to complete this task. Could you try rephrasing?"
                else:
                    fallback_msg = "I don't seem to have the right tools to handle that request."
                
                session.add_turn(query, fallback_msg)
                return await websocket.send_text(json.dumps({"type": "result", "data": fallback_msg}))
                
            executed_signatures.add(discovery_sig)

            log_debug(f"[SEARCHING TOOLS]: query='{step_obj.get_tool}', service_hint='{step_obj.tool_service}'")
            results = get_relevant_tools(query=step_obj.get_tool, k=1, service_hint=step_obj.tool_service)
            
            if results:
                lines = []
                for t in results:
                    schema_dict = t.get('schema', {})
                    # FULL SCHEMA PRESERVATION: We never strip arguments, types, or descriptions.
                    preserved_schema = {
                        "properties": schema_dict.get('properties', {}),
                        "required": schema_dict.get('required', [])
                    }
                    lines.append(f"- {t['tool_name']} via {t['tool_service']}: {json.dumps(preserved_schema)}")
                    
                new_tools_text = "\n".join(lines)
                log_debug(f"[TOOLS FOUND]:\n{new_tools_text}")
                
                # UPDATE ROLE INSTEAD OF APPENDING
                existing_tools_role = next((h for h in history_parts if h.get("role") == "tool_found"), None)
                rule_text = "[If the exact tool you need is listed above, use action='Tool-exec'. If the tool you need is MISSING, use action='Tool' to search again with a DIFFERENT query.]"
                
                if existing_tools_role:
                    current_text = existing_tools_role["text"]
                    # Strip old rule if present so we don't duplicate it
                    clean_text = re.sub(r"\[If the exact tool you need.*\]", "", current_text).strip()
                    
                    # Safely open the bracket block to append new tools at the bottom
                    if clean_text.endswith("]"):
                        clean_text = clean_text[:-1].strip()
                    
                    # Add new tools gracefully
                    existing_lines = set(clean_text.split('\n'))
                    for line in new_tools_text.split('\n'):
                        if line and line not in existing_lines:
                            clean_text += f"\n{line}"
                            existing_lines.add(line)
                            
                    # Seal the bracket block and append the rule text
                    existing_tools_role["text"] = f"{clean_text}\n]\n{rule_text}"
                else:
                    history_parts.append({"role": "tool_found", "text": f"[Found tools:\n{new_tools_text}]\n{rule_text}", "pinned": True})
            else:
                log_debug("[WARNING] NO TOOLS FOUND matching query.")
                append_or_update_error(history_parts, f"[No tools found for '{step_obj.get_tool}'. Try a different search phrase.]")
                
        # 3. Tool Execution
        elif step_obj.action == 'Tool-exec':
            error = check_guardrails(step_obj)
            if error:
                log_debug(f"[GUARDRAIL BLOCKED TOOL EXEC]: {error}")
                append_or_update_error(history_parts, f"[{error}]")
                continue

            clean_args = {k: v for k, v in (step_obj.tool_args or {}).items() if v}
            
            # Simple placeholder check
            if any(isinstance(v, str) and re.search(r"<\w+>", v) for v in clean_args.values()):
                log_debug("[GUARDRAIL]: Placeholder detected in arguments.")
                append_or_update_error(history_parts, "[Error: You used a placeholder like '<username>'. Use the actual values from the user's query.]")
                continue

            # Anti-Loop with Hard Circuit Breaker
            current_sig = f"{step_obj.tool_name}_{sorted(clean_args.items())}"
            if current_sig in executed_signatures:
                log_debug(f"[ANTI-LOOP]: Caught duplicate execution of {step_obj.tool_name}. Forcing exit.")
                
                last_obs = next((h for h in reversed(history_parts) if h.get("role") == "observation"), {}).get("text", "")
                
                if "total_count: 0" in last_obs or "[]" in last_obs or "not found" in last_obs.lower():
                    fallback_msg = "I checked, but I couldn't find any results for that."
                else:
                    fallback_msg = "I'm having trouble getting the exact data you need right now. Could you clarify or rephrase?"
                
                session.add_turn(query, fallback_msg)
                return await websocket.send_text(json.dumps({"type": "result", "data": fallback_msg}))
                
            executed_signatures.add(current_sig)
            log_debug(f"[EXECUTING TOOL]: {step_obj.tool_name} | Args: {clean_args}")

            if step_obj.tool_service == 'native':
                fn = NATIVE_TOOLS.get(step_obj.tool_name)
                try:
                    observation = fn(**clean_args) if fn else f"Native tool '{step_obj.tool_name}' not found."
                except Exception as e:
                    observation = f"Native tool failed: {e}"
            else:
                try:
                    observation = await execute_mcp_tool(active_client, step_obj.tool_service, step_obj.tool_name, clean_args)
                except Exception as e:
                    observation = f"Failed to execute tool '{step_obj.tool_name}': {e}."

            log_debug(f"[OBSERVATION RECEIVED]: {str(observation)[:200]}...") 

            run_log["steps"].append({"step": step, "tool": step_obj.tool_name, "observation": observation})
            with open(run_log_path, "w") as f:
                json.dump(run_log, f, indent=2, default=str)

            obs_dict = observation
            if isinstance(observation, str):
                try: obs_dict = json.loads(observation)
                except: pass

            if isinstance(obs_dict, dict) and obs_dict.get("success") and obs_dict.get("terminal"):
                final_msg = f"Done — {obs_dict.get('detail', 'action completed')}."
                log_debug("[TERMINAL COMPLETION]: Tool signaled terminal completion. Exiting loop.")
                session.add_turn(query, final_msg)
                return await websocket.send_text(json.dumps({"type": "result", "data": final_msg}))
            
            log_path = dump_observation(observation, step, step_obj.tool_name)
            trimmed = trim_observation(observation, session)
            
            # Append Observation naturally, maintaining chronological flow of actions
            history_parts.append({
                "role": "observation",
                "text": f"\n[Observation from {step_obj.tool_name}]: {trimmed}\n[Full data saved: {log_path}]", 
                "source_tool": step_obj.tool_name,
                "pinned": False})

        else:
            log_debug(f"[UNKNOWN ACTION]: {step_obj.action}")
            append_or_update_error(history_parts, f"[Invalid action: {step_obj.action}. Use 'Tool', 'Tool-exec', or 'Final']")

    failure_msg = "Agent loop aborted: Max steps reached without a final answer."
    log_debug("[MAX STEPS REACHED]: Aborting loop.")
    session.add_turn(query, failure_msg)
    return await websocket.send_text(json.dumps({"type": "result", "data": failure_msg}))


def background_prompt_dump(run_id, step, query, prompt_text):
    """Safely writes the prompt dump in a background thread to prevent blocking/crashing."""
    try:
        # errors="replace" prevents crashes if the LLM generates weird characters
        with open("prompt_dump.txt", "a", encoding="utf-8", errors="replace") as f:
            f.write(f"\n\n{'='*20} RUN: {run_id} | STEP: {step} {'='*20}\n")
            f.write(f"QUERY: {str(query)}\n\n")
            f.write(str(prompt_text))
    except Exception as e:
        print(f"[DEBUG ERROR] Could not dump prompt: {e}")