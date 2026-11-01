"""
Utility functions for JSON extraction, history formatting, and observation handling.
"""

import re
import os
import time
import uuid
import json
from typing import Any, List, Tuple
from dot.config.paths import OBS_LOG_DIR


def extract_json(raw: str):
    """Extracts a JSON object string from the model output."""
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    if match:
        return match.group(1).strip()
    stripped = raw.strip()
    if stripped.startswith("{"):
        if not stripped.endswith("}"):
            stripped += "}"
        return stripped
    return None


def render_history(history_parts: list) -> str:
    """Concatenates history entries into a single prompt text."""
    return "\n".join(p["text"] for p in history_parts)


def dump_observation(obs: Any, step: int, action: str) -> str:
    """Writes an observation record to disk for debugging."""
    record = {
        "step": step,
        "action": action,
        "data": obs,
        "timestamp": time.time(),
    }
    filename = f"{int(time.time())}_{uuid.uuid4().hex[:8]}.json"
    path = os.path.join(OBS_LOG_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, default=str)
    return str(path)


def auto_format_observation(obs: Any, max_fields: int = 4, max_items: int = 25) -> str:
    """Formats tool output into a compact string before token trimming."""
    data = obs

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
        lines = [f"{k}: {v}" for k, v in list(data.items())[:max_fields * 2]]
        return "\n".join(lines)

    if isinstance(data, str):
        return data

    return json.dumps(data)


def trim_observation(obs: Any, session: Any, max_tokens: int = 450) -> str:
    """Truncates tool observations that exceed the token limit."""
    text = auto_format_observation(obs)
    if not session or not hasattr(session, "tokenizer"):
        return text
    tokens = session.tokenizer.encode(text)
    if len(tokens) <= max_tokens:
        return text
    truncated_tokens = tokens[:max_tokens]
    truncated_text = session.tokenizer.decode(truncated_tokens)
    return truncated_text + "...[truncated]"


def _split_unpinned_steps(history_parts: list, session: Any, target_tokens: int) -> Tuple[list, list, list, list]:
    """Splits unpinned history parts into kept and dropped step lists."""
    pinned = [p for p in history_parts if p.get("pinned")]
    unpinned = [p for p in history_parts if not p.get("pinned")]

    recent_errors = [p for p in unpinned if p.get("role") == "error"]
    unpinned = [p for p in unpinned if p not in recent_errors]

    min_verbatim_count = min(2, len(unpinned))
    guaranteed_recent = unpinned[-min_verbatim_count:] if min_verbatim_count > 0 else []
    remaining_unpinned = unpinned[:-min_verbatim_count] if min_verbatim_count > 0 else []

    kept = list(guaranteed_recent)
    running = sum(session.count_tokens(p["text"]) for p in pinned) + \
              sum(session.count_tokens(p["text"]) for p in recent_errors) + \
              sum(session.count_tokens(p["text"]) for p in kept)

    for part in reversed(remaining_unpinned):
        cost = session.count_tokens(part["text"])
        if running + cost > target_tokens:
            break
        kept.insert(0, part)
        running += cost

    cutoff = len(remaining_unpinned) - (len(kept) - len(guaranteed_recent))
    dropped = remaining_unpinned[:cutoff]

    return pinned, recent_errors, kept, dropped


async def async_compress_history(history_parts: list, session: Any, target_tokens: int = 4000) -> list:
    """Compacts older ReAct steps into an ASD-STE100 summary asynchronously."""
    pinned, recent_errors, kept, dropped = _split_unpinned_steps(history_parts, session, target_tokens)

    if dropped:
        dump_observation(dropped, step=-1, action="pre_compaction_drop")
        dropped_text = "\n".join(p["text"] for p in dropped)

        prev_summary = None
        for p in dropped:
            if p.get("role") == "summary":
                prev_summary = p.get("text")

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

