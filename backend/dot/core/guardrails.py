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


def check_guardrails(step_obj: Any) -> Optional[str]:
    """Validates the structure of the specified agent step.

    Returns an error message if validation fails.
    Returns none when the step is valid.
    """
    action = getattr(step_obj, "action", None)

    if action == "Tool":
        tool_query = getattr(step_obj, "get_tool", None)
        tool_service = getattr(step_obj, "tool_service", None)
        if not is_real_value(tool_query):
            return "action='Tool' requires a search query in the payload. Example: {'query': 'search'}"
        if tool_service == "github" or (tool_query and "github" in str(tool_query).lower()):
            from dot.config.settings import get_github_token
            if not get_github_token():
                return "GitHub Personal Access Token (PAT) is missing. Configure a valid GitHub PAT in Settings (3 dots > MCP Tools) or set the GITHUB_TOKEN environment variable."
        return None

    if action == "Tool-exec":
        tool_name = getattr(step_obj, "tool_name", None) or ""
        tool_service = getattr(step_obj, "tool_service", None) or ""
        if not tool_name:
            return "action='Tool-exec' requires a 'name' in the payload."
        if tool_service == "github" or tool_name.startswith("github_"):
            from dot.config.settings import get_github_token
            if not get_github_token():
                return "GitHub Personal Access Token (PAT) is missing. Configure a valid GitHub PAT in Settings (3 dots > MCP Tools) or set the GITHUB_TOKEN environment variable."
        return None

    return None

