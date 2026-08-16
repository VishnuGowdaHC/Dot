from pydantic import BaseModel, field_validator
from typing import Literal, Optional
import os
import time
import uuid
import re
import asyncio
import json
from src.dot.memory.vector_store import get_relevant_tools
from src.dot.mcp_files.mcpClient import execute_mcp_tool, get_multi_server_client
from src.dot.memory.session_memory.manager import SessionStorage
from src.dot.memory.collections.native_tools_collection import NATIVE_TOOLS
from src.dot.core.llm import llm
from src.dot.memory.vector_store import get_all_services

OBS_LOG_DIR = 'logs/observations'
os.makedirs(OBS_LOG_DIR, exist_ok=True)

active_session = SessionStorage(session_id=str(uuid.uuid4()))

class AgentStep(BaseModel):
    thought: str = ""
    action: Optional[Literal['Tool', 'Tool-exec', 'Final']] = None
    get_tool: Optional[str] = None
    tool_service: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None 
    action_input: Optional[str] = None
    final_answer: Optional[str] = None
    

    @field_validator('tool_args', mode='before')
    @classmethod
    def parse_tool_args(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

def extract_json(raw):
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    if match:
        return match.group(1)
    stripped = raw.strip()
    if stripped.startswith("{"):
        return stripped
    return None 

def render_history(history_parts) -> str:
    return "\n".join(p["text"] for p in history_parts)

def dump_observation(obs, step: int, action: str):
    record = {
        'step': step,
        'action': action,
        'data': obs,
        'timestamp': time.time(),
    }
    filename = f"{int(time.time())}_{uuid.uuid4().hex[:8]}.json"
    path = os.path.join(OBS_LOG_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, default=str)
    return path

def trim_observation(obs, session, max_tokens=700):
    text = auto_format_observation(obs)
    tokens = session.tokenizer.encode(text)
    if len(tokens) <= max_tokens:
        return text
    truncated_tokens = tokens[:max_tokens]
    truncated_text = session.tokenizer.decode(truncated_tokens)
    return truncated_text + "...[truncated]"

async def reAct_loop( query, llm, session: SessionStorage, max_steps=8):
    run_id = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    run_log_path = os.path.join(OBS_LOG_DIR, f"run_{run_id}.json")
    run_log = {"query": query, "steps": []}

    multi_server_client = get_multi_server_client()
    schema = AgentStep.model_json_schema()

    active_history_context = session.get_context_string()
    available_services = get_all_services()

    history_parts = [{
        "role": "context",
        "text": f"""
            <AVAILABLE_TOOL_SERVICES>
            {', '.join(available_services) if available_services else 'None registered.'}
            </AVAILABLE_TOOL_SERVICES>
            
            <PREVIOUS_SESSION_CONTEXT>
            {active_history_context or "No previous history."}
            </PREVIOUS_SESSION_CONTEXT>

            <CURRENT_QUERY>
            user: {query}
            </CURRENT_QUERY>
            """,
        "pinned": True
    }]

    MAX_LOOP_TOKENS = 6000

    async with multi_server_client as active_client:
        for step in range(max_steps):
            print(f"Step {step}")

            if session.count_tokens(render_history(history_parts)) > MAX_LOOP_TOKENS:
                history_parts = compress_history(history_parts, session)

            prompt = f"""{history_parts}"""

            raw = llm(prompt, schema=schema)
            extracted = extract_json(raw)

            print("extracted: ", extracted)
            if extracted is None: return raw.strip()

            try:
                step_obj = AgentStep.model_validate_json(extracted)
            except Exception as e:
                history_parts.append({
                    "role": "error",
                    "text": f"[Invalid output: {e}. Retry with valid JSON]",
                    "pinned": False,
                })
                continue

            if step_obj.thought:
                history_parts.append({"role": "thought", "text": step_obj.thought, "pinned": False})
            
            print("\nhistory: ", history_parts)
            print("\nstep_obj: ", step_obj)

            if step_obj.action == 'Final' or (step_obj.action is None and step_obj.final_answer):
                session.add_turn(query, step_obj.final_answer)
                return step_obj.final_answer
                #return await websocket.send_text(json.dumps({"type": "result", "data": step_obj.final_answer}))

            if step_obj.action == 'Tool':
                result = get_relevant_tools(step_obj.get_tool, k=2, service_hint=step_obj.tool_service)
                if result:
                    tool = result[0]
                    history_parts.append({"role": "tool_found", "text": f"[Found tool: {tool['tool_name']} via {tool['tool_service']}. Schema: {tool['schema']}]\n[Next step: set action='Tool-exec', tool_service='{tool['tool_service']}', tool_name='{tool['tool_name']}', and fill tool_args matching the schema above.]", "pinned": False})

            elif step_obj.action == 'Tool-exec':
                if step_obj.tool_service == 'native':
                    fn = NATIVE_TOOLS.get(step_obj.tool_name)
                    if fn is None:
                        observation = f"Native tool '{step_obj.tool_name}' not found."
                    else:
                        try:
                            observation = fn(**(step_obj.tool_args) or {})
                        except Exception as e:
                            observation = f"Native tool '{step_obj.tool_name}' failed: {e}"
                else:
                    observation = await execute_mcp_tool(active_client, step_obj.tool_service, step_obj.tool_name, step_obj.tool_args)

                run_log["steps"].append({"step": step, "tool": step_obj.tool_name, "observation": observation})

                with open(run_log_path, "w") as f:
                    json.dump(run_log, f, indent=2, default=str)
                
                log_path = dump_observation(observation, step, step_obj.tool_name)
                trimmed = trim_observation(observation, session)

                history_parts.append({"role": "observation", "text": f"\n[Observation: {trimmed}]\n[Full data saved: {log_path}]", "pinned": False})

            else:
                history_parts.append({"role": "error", "text": f"[Invalid action: {step_obj.action}. Retry with valid action]", "pinned": False})

    failure_msg = "Agent loop aborted: Max steps reached without a final answer."
    session.add_turn(query, failure_msg)
            
    return failure_msg

def compress_history(history_parts, session, target_tokens=4000):
    """Keeps pinned context + current query + most recent steps verbatim.
    Collapses everything older into one summary line."""
    pinned = [p for p in history_parts if p["pinned"]]
    unpinned = [p for p in history_parts if not p["pinned"]]

    recent_errors = [p for p in unpinned if p["role"] == "error"]
    unpinned = [p for p in unpinned if p not in recent_errors]

    # Walk backwards, keep recent entries until we'd exceed the budget
    kept = []
    running = sum(session.count_tokens(p["text"]) for p in pinned)

    for part in reversed(unpinned):
        cost = session.count_tokens(part["text"])
        if running + cost > target_tokens:
            break
        kept.insert(0, part)
        running += cost

    dropped = unpinned[: len(unpinned) - len(kept)]

    if dropped:
        dropped_text = "\n".join(p["text"] for p in dropped)
        summary = summarize_dropped(dropped_text)  # see below
        kept.insert(0, {"role": "summary", "text": f"[Earlier steps summarized: {summary}]", "pinned": False})

    return pinned + recent_errors + kept

def summarize_dropped(text: str) -> str:
    # crude but cheap: pull tool names + outcomes, skip full reasoning text
    tool_calls = re.findall(r"\[Found tool: (\w+)", text)
    observations = re.findall(r"\[Observation: (.{0,80})", text)
    parts = []
    if tool_calls:
        parts.append(f"tools used: {', '.join(tool_calls)}")
    if observations:
        parts.append(f"{len(observations)} observation(s) retrieved, details discarded")
    return "; ".join(parts) or "earlier reasoning steps (no tool calls)"

def auto_format_observation(obs, max_fields=4, max_items=25) -> str:
    """
    Generic formatter: turns common tool-output shapes into compact,
    information-dense text before token trimming ever needs to kick in.
    Falls back to raw JSON for shapes it doesn't recognize.
    """
    data = obs

    # unwrap common "results wrapper" shapes: {"items": [...], "total_count": N}
    wrapper_keys = None
    if isinstance(data, dict):
        for list_key in ("items", "results", "repositories", "data"):
            if list_key in data and isinstance(data[list_key], list):
                wrapper_keys = {
                    "list": data[list_key],
                    "total": data.get("total_count") or data.get("total") or len(data[list_key]),
                }
                break

    items = wrapper_keys["list"] if wrapper_keys else (data if isinstance(data, list) else None)

    if isinstance(items, list) and items and isinstance(items[0], dict):
        # pick a small set of high-signal fields, preferring common identifying keys
        priority_fields = ["name", "title", "full_name", "url", "html_url", "language", "description"]
        sample_keys = list(items[0].keys())
        chosen_fields = [f for f in priority_fields if f in sample_keys][:max_fields]
        if not chosen_fields:
            chosen_fields = sample_keys[:max_fields]

        lines = []
        for entry in items[:max_items]:
            parts = [str(entry.get(f, "")) for f in chosen_fields if entry.get(f) not in (None, "")]
            lines.append("- " + " | ".join(parts))

        header = f"{wrapper_keys['total']} results" if wrapper_keys else f"{len(items)} items"
        omitted = ""
        if len(items) > max_items:
            omitted = f"\n...and {len(items) - max_items} more (see full data log)"
        return f"{header}:\n" + "\n".join(lines) + omitted

    if isinstance(data, dict):
        # plain dict, no list wrapper — show top-level keys compactly
        lines = [f"{k}: {v}" for k, v in list(data.items())[:max_fields * 2]]
        return "\n".join(lines)

    if isinstance(data, str):
        return data

    return json.dumps(data)

query1 = "can u search up all the github repos from user VishnuGowdaHC"
query2 = "can u use search_active_session tool and retrive summerized infor"

result = asyncio.run(reAct_loop(query1, llm, active_session, max_steps=8))
print(result)



