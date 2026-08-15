from pydantic import BaseModel, field_validator
from typing import Literal, Optional
import os
import time
import uuid
import re
import asyncio
import json
from src.dot.memory.vector_store import get_relevant_tools
from src.dot.mcp_files.mcpClient import execute_mcp_tool

OBS_LOG_DIR = 'logs/observations'
os.makedirs(OBS_LOG_DIR, exist_ok=True)

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

def trim_observation(obs, max_tokens=1500):
    text = json.dumps(obs) if not isinstance(obs, str) else obs
    if len(text) > max_tokens:
        return text
    return text[:max_tokens] + "...[truncated]"

async def reAct_loop(websocket, query, llm, max_steps=8):
    run_id = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    run_log_path = os.path.join(OBS_LOG_DIR, f"run_{run_id}.json")
    run_log = {"query": query, "steps": []}

    schema = AgentStep.model_json_schema()

    history = f"user: {query}\n"

    for step in range(max_steps):
        print(f"Step {step}")

        prompt = f"""{history}"""

        raw = llm(prompt, schema=schema)
        extracted = extract_json(raw)

        print("extracted: ", extracted)
        if extracted is None: return raw.strip()

        try:
            step_obj = AgentStep.model_validate_json(extracted)
        except Exception as e:
            history += f"\n[Invalid out: {e}. Retry with valid JSON]"
            continue

        history += f"\n{step_obj.thought}"
        print("\nhistory: ", history)
        
        print("\nstep_obj: ", step_obj)

        if step_obj.action == 'Final' or (step_obj.action is None and step_obj.final_answer):
            return await websocket.send_text(json.dumps({"type": "result", "data": step_obj.final_answer}))

        if step_obj.action == 'Tool':
            result = get_relevant_tools(step_obj.get_tool, k=1, service_hint=step_obj.tool_service)
            if result:
                tool = result[0]
                history += f"\n[Found tool: {tool['tool_name']} via {tool['tool_service']}. Schema: {tool['schema']}]\n[Next step: set action='Tool-exec', tool_service='{tool['tool_service']}', tool_name='{tool['tool_name']}', and fill tool_args matching the schema above.]"

        elif step_obj.action == 'Tool-exec':
            observation = await execute_mcp_tool(step_obj.tool_service, step_obj.tool_name, step_obj.tool_args)

            run_log["steps"].append({"step": step, "tool": step_obj.tool_name, "observation": observation})
            with open(run_log_path, "w") as f:
                json.dump(run_log, f, indent=2, default=str)
            
            log_path = dump_observation(observation, step, step_obj.tool_name)
            trimmed = trim_observation(observation)
            
            history += f"\n[Observation: {trimmed}]\n[Full data saved: {log_path}]"

        else:
            history += f"\n[Invalid action: {step_obj.action}. Retry with valid action]"
            
            
    return "Max steps reached"



