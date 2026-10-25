"""
Validation module for agent steps and tool parameters.
Ensures the model produces complete and valid actions.
"""

from typing import Optional, Any

TOOL_DEPENDENCIES = {
    "browser_click": ["browser_snapshot"],
    "browser_fill": ["browser_snapshot"],
}


def is_real_value(value: Any) -> bool:
    """Verifies that the value contains usable content.
    
    Returns false for null, empty strings, and empty dictionaries.
    """
    if value is None:
        return False
    if isinstance(value, str):
        cleaned = value.strip().lower()
        return cleaned != "" and cleaned not in ("none", "null", "n/a")
    if isinstance(value, dict):
        return len(value) > 0
    return bool(value)


def check_guardrails(step_obj) -> Optional[str]:
    """Validates the structure of the specified agent step.
    
    Returns an error message if validation fails.
    Returns none when the step is valid.
    """
    action = step_obj.action

    if action == "Tool":
        if not is_real_value(step_obj.get_tool):
            return "action='Tool' requires a search query in the payload. Example: {'query': 'search'}"
        return None

    if action == "Tool-exec":
        if not step_obj.tool_name:
            return "action='Tool-exec' requires a 'name' in the payload."
        return None

    return None


# Backward-compatible alias for existing imports
_is_real_value = is_real_value
