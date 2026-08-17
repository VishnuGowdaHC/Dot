from pydantic import BaseModel, field_validator
from typing import Literal, Optional
import os
import time
import uuid
import asyncio
import json

from src.dot.memory.vector_store import get_relevant_tools, get_all_services, get_full_service_tools_text
from src.dot.core.gaurdrails import check_guardrails, _missing_dependencies
from src.dot.mcp_files.mcpClient import execute_mcp_tool, get_multi_server_client
from src.dot.memory.session_memory.manager import SessionStorage
from src.dot.memory.collections.native_tools_collection import NATIVE_TOOLS
from src.dot.core.llm import llm
from src.dot.core.utils import *  
from src.dot.automation_mcp.browser_automation import TOOL_DEPENDENCIES

active_session = SessionStorage(session_id=str(uuid.uuid4()))


class PlannedStep(BaseModel):
    tool_service: str
    tool_name: str
    tool_args: dict


class AgentStep(BaseModel):
    thought: str = ""
    action: Optional[Literal['Tool', 'Tool-exec', 'Plan', 'Auto-tool', 'Final']] = None
    get_tool: Optional[str] = None
    tool_service: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None
    plan_steps: Optional[list[PlannedStep]] = None
    final_answer: Optional[str] = None

    @field_validator('tool_args', mode='before')
    @classmethod
    def parse_tool_args(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v


MAX_LOOP_TOKENS = 6000
MAX_IDENTICAL_FAILURES = 3
BYPASS_SERVICES = {"browser", "native"}

def _failure_signature(step_obj: AgentStep, error_text: str) -> str:
    return f"{step_obj.action}:{error_text[:60]}"


async def reAct_loop(query, llm, session: SessionStorage, max_steps=8):
    run_id = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    run_log_path = os.path.join(OBS_LOG_DIR, f"run_{run_id}.json")
    run_log = {"query": query, "steps": []}

    multi_server_client = get_multi_server_client()
    schema = AgentStep.model_json_schema()

    active_history_context = session.get_context_string()
    available_services = get_all_services()

    bypass_tools_text = "\n\n".join(
        f"<{svc.upper()}_TOOLS>\n{get_full_service_tools_text(svc)}\n</{svc.upper()}_TOOLS>"
        for svc in BYPASS_SERVICES if svc in available_services
    )

    print(bypass_tools_text)

    history_parts = [{
        "role": "context",
        "text": f"""
            <AVAILABLE_TOOL_SERVICES>
            {', '.join(available_services) if available_services else 'None registered.'}
            </AVAILABLE_TOOL_SERVICES>

            {bypass_tools_text}

            <PREVIOUS_SESSION_CONTEXT>
            {active_history_context or "No previous history."}
            </PREVIOUS_SESSION_CONTEXT>

            <CURRENT_QUERY>
            user: {query}
            </CURRENT_QUERY>
            """,
        "pinned": True,
    }]

    pending_plan = None
    last_failure_sig = None
    identical_failure_count = 0

    def record_error(step_obj, error_text):
        nonlocal last_failure_sig, identical_failure_count
        sig = _failure_signature(step_obj, error_text)
        if sig == last_failure_sig:
            identical_failure_count += 1
        else:
            identical_failure_count = 1
        last_failure_sig = sig

        if identical_failure_count >= MAX_IDENTICAL_FAILURES:
            return True

        if identical_failure_count == 2:
            error_text += "\n[Repeated mistake — re-read the fix instructions above carefully and apply them exactly.]"

        history_parts.append({"role": "error", "text": f"[{error_text}]", "pinned": False})
        return False

    async with multi_server_client as active_client:
        for step in range(max_steps):
            print(f"Step {step}")

            if session.count_tokens(render_history(history_parts)) > MAX_LOOP_TOKENS:
                history_parts = compress_history(history_parts, session)

            prompt = render_history(history_parts)
            raw = llm(prompt, schema=schema)
            extracted = extract_json(raw)

            print("extracted: ", extracted)
            if extracted is None:
                return raw.strip()

            try:
                step_obj = AgentStep.model_validate_json(extracted)
            except Exception as e:
                if record_error(AgentStep(), f"Invalid output: {e}. Retry with valid JSON"):
                    return "I ran into repeated errors trying to process this — could you rephrase your request?"
                continue

            # self-heal: model filled Tool-exec-shaped data but mislabeled the action
            if step_obj.action == 'Tool' and step_obj.tool_name and step_obj.tool_args:
                step_obj.action = 'Tool-exec'

            if step_obj.thought:
                history_parts.append({"role": "thought", "text": step_obj.thought, "pinned": False})

            print("\nhistory: ", history_parts)
            print("\nstep_obj: ", step_obj)

            # final answer
            if step_obj.action == 'Final' or (step_obj.action is None and step_obj.final_answer):
                session.add_turn(query, step_obj.final_answer)
                return step_obj.final_answer

            # tool discovery
            elif step_obj.action == 'Tool':
                # guard: already found a tool last step - re-searching instead of using it
                violation = check_guardrails(step_obj, history_parts, pending_plan)
                if violation:
                    if record_error(step_obj, violation):
                        return "I couldn't figure out the right tool to use for this — could you rephrase your request?"
                    continue

                # self-heal: model nested get_tool inside tool_args instead of top-level
                if step_obj.action == 'Tool' and not step_obj.get_tool and step_obj.tool_args and 'get_tool' in step_obj.tool_args:
                    step_obj.get_tool = step_obj.tool_args.pop('get_tool')

                results = get_relevant_tools(query=step_obj.get_tool, k=5, service_hint=step_obj.tool_service)
                if results:
                    lines = [f"- {t['tool_name']} via {t['tool_service']}: {t['schema']}" for t in results]
                    tools_text = "\n".join(lines)
                    new_entry_text = f"[Found tools:\n{tools_text}]\n[Next step: use action='Tool-exec' for a single call, or action='Plan' if this needs multiple steps — using only the exact tool_name values shown above.]"

                    # skip appending if identical to the immediately preceding tool_found (avoids duplicate bloat)
                    already_present = (
                        history_parts and history_parts[-1].get("role") == "tool_found"
                        and history_parts[-1].get("text") == new_entry_text
                    )
                    if not already_present:
                        history_parts.append({"role": "tool_found", "text": new_entry_text, "pinned": False})
                    identical_failure_count = 0
                else:
                    if record_error(step_obj, f"No tools found for '{step_obj.get_tool}' in service '{step_obj.tool_service}'. Try a different search phrase."):
                        return "I couldn't find a matching tool for this request."
                    continue

            elif step_obj.action == 'Tool-exec':
                # guard: required tools not found
                violation = check_guardrails(step_obj, history_parts, pending_plan)
                if violation:
                    if record_error(step_obj, violation):
                        return "I couldn't reliably interact with the page — could you try again?"
                    continue

                # guard: already ran this tool last step
                if run_log["steps"]:
                    last_step = run_log["steps"][-1]
                    if last_step.get("tool") == step_obj.tool_name and history_parts[-1].get("role") == "observation":
                        history_parts.append({
                            "role": "error",
                            "text": "[You just executed this exact tool. The data is already in the Observation above. You MUST immediately output action='Final' and answer the user.]",
                            "pinned": False,
                        })
                        continue

                # run tool
                if step_obj.tool_service == 'native':
                    fn = NATIVE_TOOLS.get(step_obj.tool_name)
                    if fn is None:
                        observation = f"Native tool '{step_obj.tool_name}' not found."
                    else:
                        try:
                            observation = fn(**(step_obj.tool_args or {}))
                        except Exception as e:
                            observation = f"Native tool '{step_obj.tool_name}' failed: {e}"
                else:
                    observation = await execute_mcp_tool(active_client, step_obj.tool_service, step_obj.tool_name, step_obj.tool_args)

                run_log["steps"].append({"step": step, "tool": step_obj.tool_name, "observation": observation})
                with open(run_log_path, "w") as f:
                    json.dump(run_log, f, indent=2, default=str)

                log_path = dump_observation(observation, step, step_obj.tool_name)
                trimmed = trim_observation(observation, session)
                history_parts.append({
                    "role": "observation",
                    "text": f"\n[Observation: {trimmed}]\n[Full data saved: {log_path}]", 
                    "source_tool": step_obj.tool_name,
                    "pinned": False})
                identical_failure_count = 0

            elif step_obj.action == 'Plan':
                violation = check_guardrails(step_obj, history_parts, pending_plan)
                if violation:
                    if record_error(step_obj, violation):
                        return "I need more information before I can plan this out — could you clarify what you'd like me to do?"
                    continue

                pending_plan = step_obj.plan_steps
                plan_preview = "; ".join(f"{s.tool_name}({s.tool_args})" for s in pending_plan)
                history_parts.append({
                    "role": "plan",
                    "text": f"[Plan formed: {plan_preview}]\n[Next step: set action='Auto-tool' to execute this plan]",
                    "pinned": False,
                })
                identical_failure_count = 0

            elif step_obj.action == 'Auto-tool':
                violation = check_guardrails(step_obj, history_parts, pending_plan)
                if violation:
                    if record_error(step_obj, violation):
                        return "I lost track of the plan for this task — could you try again?"
                    continue

                results_log = []
                aborted_at = None

                for i, planned_step in enumerate(pending_plan):
                    result = await act_and_verify(planned_step, active_client)
                    results_log.append({"step": i, "tool": planned_step.tool_name, **result})

                    obs_text = str(result.get("detail", result))
                    history_parts.append({
                        "role": "observation",
                        "text": f"[Step {i} ({planned_step.tool_name}) Data: {obs_text[:1500]}]",
                        "source_tool": planned_step.tool_name,
                        "pinned": False,
                    })

                    if not result["success"]:
                        aborted_at = i
                        break

                summary = summarize_plan_log(results_log, aborted_at)
                history_parts.append({"role": "plan_result", "text": f"[Plan result: {summary}]", "pinned": False})
                pending_plan = None
                identical_failure_count = 0

            else:
                if record_error(step_obj, f"Invalid action: {step_obj.action}. Retry with a valid action."):
                    return "I ran into repeated errors handling this request — could you rephrase it?"
                continue

    failure_msg = "Agent loop aborted: Max steps reached without a final answer."
    session.add_turn(query, failure_msg)
    return failure_msg


if __name__ == "__main__":
    query1 = "play bbno$ two on youtube"
    query3 = "can u list the browser tools with schema on what all they can do?"
    query2 = "can u list the browser tools with schema on what all they can do?"
    result = asyncio.run(reAct_loop(query1, llm, active_session, max_steps=8))
    print(result)