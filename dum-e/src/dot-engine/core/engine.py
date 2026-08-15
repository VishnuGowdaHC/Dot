from core.llm import llm
from pydantic import BaseModel, Field
from typing import Literal, Optional
import json
import re



class AgentStep(BaseModel):
    thought: str
    action: Optional[Literal['Search', 'Tool', 'Final']] = None
    action_input: Optional[str] = None
    final_answer: Optional[str] = None

def extract_json(raw):
    # Remove ```json ... ``` or ``` ... ``` wrapper if present
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    print(f"raw: {raw}")
    print(f"match: {match}")
    if match:
        return match.group(1)
    stripped = raw.strip()
    print(f"stripped: {stripped}")
    if stripped.startswith("{"):
        return stripped
    return None 

def reAct_loop(query, llm, tools, max_steps=5):
    schema = AgentStep.model_json_schema()
    history = f"user: {query}\n"

    for step in range(max_steps):
        print(f"Step {step}")
        prompt  = f"""Respond ONLY with JSON matching this schema: {json.dumps(schema)}

        Tools available: {', '.join(tools.keys())}
        If the tools available is not respond with need_tool and need_action you want to perform and mention the COUNT u tried to find tool in this format COUNT: <number> 
        If you have the answer, set action to "Final" and fill final_answer.
        {history}
        """
        print("Thinking...")
        raw = llm(prompt)
        print("Completed thinking...")

        extracted = extract_json(raw)
        print("extracted: ", extracted)
        if extracted is None: return raw.strip()

        try:
            print("\nIn try block history: ", history)
            step_obj = AgentStep.model_validate_json(extracted)
        except Exception as e:
            history += f"\n[Invalid out: {e}. Retry with valid JSON]"
            continue

        history += f"\n{step_obj.thought}"
        print("\nhistory: ", history)
        print("\nstep_obj: ", step_obj)
        if step_obj.action == 'Final':
            return step_obj.final_answer

        if step_obj.action in tools:
            observation = f"tools called "
            history += f"{observation}"
        else:
            history += f"\n[Invalid action: {step_obj.action}. Retry with valid action]"
    return "Max steps reached"

print(reAct_loop("hello", llm, {}, max_steps=5))

