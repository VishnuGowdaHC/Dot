import re
import os
import time
import uuid
import json
from src.dot.mcp_files.mcpClient import execute_mcp_tool
from src.dot.memory.collections.native_tools_collection import NATIVE_TOOLS


OBS_LOG_DIR = 'logs/observations'
os.makedirs(OBS_LOG_DIR, exist_ok=True)

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

def trim_observation(obs, session, max_tokens=700):
    text = auto_format_observation(obs)
    tokens = session.tokenizer.encode(text)
    if len(tokens) <= max_tokens:
        return text
    truncated_tokens = tokens[:max_tokens]
    truncated_text = session.tokenizer.decode(truncated_tokens)
    return truncated_text + "...[truncated]"

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

def summarize_plan_log(results_log, aborted_at):
    if aborted_at is None:
        return f"All {len(results_log)} steps completed successfully."
    done = aborted_at
    failed_step = results_log[aborted_at]
    return (f"{done}/{len(results_log)} steps completed. "
            f"Failed at step {aborted_at} ({failed_step['tool']}): {failed_step.get('error', 'verification failed')}.")

async def dispatch_tool(planned_step, active_client) -> dict:
    """Executes one tool call (native or MCP) and returns its
    self-reported result. Assumes every automation tool follows
    the {success, detail, error} contract."""
    try:
        if planned_step.tool_service == "native":
            fn = NATIVE_TOOLS.get(planned_step.tool_name)
            if fn is None:
                return {"success": False, "detail": "", "error": f"Unknown native tool: {planned_step.tool_name}"}
            result = fn(**(planned_step.tool_args or {}))
        else:
            result = await execute_mcp_tool(active_client, planned_step.tool_service, planned_step.tool_name, planned_step.tool_args)

        # guard against tools that don't yet follow the contract
        if not isinstance(result, dict) or "success" not in result:
            return {"success": True, "detail": str(result), "error": None}  # legacy passthrough, assume ok
        return result

    except Exception as e:
        return {"success": False, "detail": "", "error": str(e)}

async def act_and_verify(planned_step, active_client, max_retries=2):
    last_result = None
    for attempt in range(max_retries):
        last_result = await dispatch_tool(planned_step, active_client)
        if last_result["success"]:
            return last_result
    return last_result  # return the last failure if all retries exhausted


