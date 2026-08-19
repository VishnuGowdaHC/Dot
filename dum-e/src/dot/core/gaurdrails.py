TOOL_DEPENDENCIES = {
    "browser_click": ["browser_snapshot"],
    "browser_fill": ["browser_snapshot"],
   
}
def _is_real_value(v):
    """True only for actual usable string/dict content."""
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != "" and v.strip().lower() not in ("none", "null", "n/a")
    if isinstance(v, dict):
        return len(v) > 0
    return bool(v)

def check_guardrails(step_obj) -> str | None:
    """
    Minimal guardrails for a small Gemma model. 
    Returns an error string if violated, else None.
    """
    action = step_obj.action

    if action == 'Tool':
        if not _is_real_value(step_obj.get_tool):
            return "action='Tool' requires a search query in the payload. Example: {'query': 'search'}"
        return None

    if action == 'Tool-exec':
        if not step_obj.tool_name:
            return "action='Tool-exec' requires a 'name' in the payload."
        return None

    return None