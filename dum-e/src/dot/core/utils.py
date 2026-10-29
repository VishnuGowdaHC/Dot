import re
import os
import time
import uuid
import json

OBS_LOG_DIR = 'logs/observations'
os.makedirs(OBS_LOG_DIR, exist_ok=True)

def extract_json(raw):
    """Extracts a JSON object string from the model output."""
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    if match:
        return match.group(1)
    stripped = raw.strip()
    if stripped.startswith("{"):
        return stripped
    return None 

def render_history(history_parts) -> str:
    """Concatenates history entries into a single prompt text."""
    return "\n".join(p["text"] for p in history_parts)

def dump_observation(obs, step: int, action: str):
    """Writes an observation record to disk for debugging."""
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
    """Formats tool output into a compact string before token trimming."""
    data = obs

    # Normalize result dictionaries that contain an items list and total count.
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
        # Select primary identifying fields from the item dictionary.
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
        # Format plain dictionary entries as key-value pairs.
        lines = [f"{k}: {v}" for k, v in list(data.items())[:max_fields * 2]]
        return "\n".join(lines)

    if isinstance(data, str):
        return data

    return json.dumps(data)

def trim_observation(obs, session, max_tokens=450):
    """Truncates tool observations that exceed the token limit."""
    text = auto_format_observation(obs)
    tokens = session.tokenizer.encode(text)
    if len(tokens) <= max_tokens:
        return text
    truncated_tokens = tokens[:max_tokens]
    truncated_text = session.tokenizer.decode(truncated_tokens)
    return truncated_text + "...[truncated]"

def _split_unpinned_steps(history_parts, session, target_tokens):
    """Splits unpinned history parts into kept and dropped step lists."""
    pinned = [p for p in history_parts if p.get("pinned")]
    unpinned = [p for p in history_parts if not p.get("pinned")]

    recent_errors = [p for p in unpinned if p.get("role") == "error"]
    unpinned = [p for p in unpinned if p not in recent_errors]

    # Preserve the last 2 steps verbatim when available.
    min_verbatim_count = min(2, len(unpinned))
    guaranteed_recent = unpinned[-min_verbatim_count:] if min_verbatim_count > 0 else []
    remaining_unpinned = unpinned[:-min_verbatim_count] if min_verbatim_count > 0 else []

    kept = list(guaranteed_recent)
    running = sum(session.count_tokens(p["text"]) for p in pinned) + \
              sum(session.count_tokens(p["text"]) for p in recent_errors) + \
              sum(session.count_tokens(p["text"]) for p in kept)

    # Collect steps backward within the token budget.
    for part in reversed(remaining_unpinned):
        cost = session.count_tokens(part["text"])
        if running + cost > target_tokens:
            break
        kept.insert(0, part)
        running += cost

    cutoff = len(remaining_unpinned) - (len(kept) - len(guaranteed_recent))
    dropped = remaining_unpinned[:cutoff]

    return pinned, recent_errors, kept, dropped

def compress_history(history_parts, session, target_tokens=4000):
    """Retains pinned context and recent steps. Summarizes older history steps."""
    pinned, recent_errors, kept, dropped = _split_unpinned_steps(history_parts, session, target_tokens)

    if dropped:
        # Save snapshot of dropped steps to disk before compaction.
        dump_observation(dropped, step=-1, action="pre_compaction_drop")
        dropped_text = "\n".join(p["text"] for p in dropped)
        summary = summarize_dropped(dropped_text)
        kept.insert(0, {"role": "summary", "text": f"[Earlier steps summarized: {summary}]", "pinned": False})

    return pinned + recent_errors + kept

async def async_compress_history(history_parts, session, target_tokens=4000):
    """Compacts older ReAct steps into an ASD-STE100 summary asynchronously."""
    pinned, recent_errors, kept, dropped = _split_unpinned_steps(history_parts, session, target_tokens)

    if dropped:
        # Save snapshot of dropped steps to disk before compaction.
        dump_observation(dropped, step=-1, action="pre_compaction_drop")
        dropped_text = "\n".join(p["text"] for p in dropped)

        # Check for previous summary block in unpinned history.
        prev_summary = None
        for p in dropped:
            if p.get("role") == "summary":
                prev_summary = p.get("text")

        # Generate summary using the session compactor when available.
        if hasattr(session, "compactor") and session.compactor:
            summary = await session.compactor.compact(dropped_text, previous_summary=prev_summary)
            summary_text = f"[Earlier steps summarized in ASD-STE100:\n{summary}\n]"
        else:
            summary_text = f"[Earlier steps summarized: {summarize_dropped(dropped_text)}]"

        kept.insert(0, {"role": "summary", "text": summary_text, "pinned": False})

    return pinned + recent_errors + kept

def summarize_dropped(text: str) -> str:
    """Extract tool names and outcomes from previous steps. Omit reasoning text."""
    tool_calls = re.findall(r"^- (\w+) via", text, re.MULTILINE)
    observations = re.findall(r"\[Observation from (\w+)\]: (.{0,80})", text)
    parts = []
    if tool_calls:
        parts.append(f"tools used: {', '.join(tool_calls)}")
    if observations:
        parts.append(f"{len(observations)} observation(s) retrieved, details discarded")
    return "; ".join(parts) or "earlier reasoning steps (no tool calls)"

def summarize_plan_log(results_log, aborted_at):
    """Summarizes execution results for a multi-step plan log."""
    if aborted_at is None:
        return f"All {len(results_log)} steps completed successfully."
    done = aborted_at
    failed_step = results_log[aborted_at]
    return (f"{done}/{len(results_log)} steps completed. "
            f"Failed at step {aborted_at} ({failed_step['tool']}): {failed_step.get('error', 'verification failed')}.")
