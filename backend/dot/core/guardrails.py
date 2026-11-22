"""
Validation module for agent steps and tool parameters.
Ensures the model produces complete and valid actions.
"""

import os
import re
from typing import Optional, Any, Dict
from dot.config import settings

# Export functions for backwards compatibility.
get_github_token = settings.get_github_token
get_allowed_workspace = settings.get_allowed_workspace

TOOL_DEPENDENCIES = {
    "browser_click": ["browser_snapshot"],
    "browser_fill": ["browser_snapshot"],
}

DESTRUCTIVE_COMMAND_PATTERNS = [
    r"\brm\s+",
    r"\bdel\s+",
    r"\brmdir\s+",
    r"\bRemove-Item\s+",
    r"\bshutil\.rmtree\b",
    r"\bos\.remove\b",
    r"\bunlink\b",
    r"\bformat\s+[a-zA-Z]:",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\bdrop\s+(database|table)\b",
    r"\btruncate\s+table\b",
]


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


def check_destructive_action(tool_name: str, tool_args: Dict[str, Any]) -> Optional[str]:
    """Validates that destructive actions stay within the allowed workspace.

    Blocks operations that delete files outside the allowed folder.
    """
    allowed_workspace = settings.get_allowed_workspace()
    allowed_workspace_norm = os.path.realpath(os.path.abspath(allowed_workspace))

    # Check for destructive tool names.
    lowered_tool = tool_name.lower()
    is_delete_tool = any(k in lowered_tool for k in ("delete_file", "remove_file", "unlink_file", "rm_file"))

    # Check for process termination actions.
    if lowered_tool in ("os_manage_process", "manage_process"):
        proc_action = str(tool_args.get("action", "")).lower()
        if proc_action in ("terminate", "kill", "force_close"):
            return "Guardrail Notice: Terminating desktop processes requires explicit user confirmation."

    # Check command strings for destructive shell commands.
    cmd_text = ""
    for k in ("command", "cmd", "script", "bash", "powershell", "code"):
        if k in tool_args and isinstance(tool_args[k], str):
            cmd_text += " " + tool_args[k]

    is_destructive_cmd = False
    if cmd_text:
        for pattern in DESTRUCTIVE_COMMAND_PATTERNS:
            if re.search(pattern, cmd_text, re.IGNORECASE):
                is_destructive_cmd = True
                break

    if is_delete_tool or is_destructive_cmd:
        # Extract target paths from arguments or command text.
        target_path = None
        for path_key in ("path", "filepath", "file", "target", "folder", "directory", "cwd"):
            if path_key in tool_args and isinstance(tool_args[path_key], str):
                target_path = tool_args[path_key].strip()
                break

        if not target_path and cmd_text:
            # Extract common path patterns from the command string.
            path_match = re.search(r'(?:[a-zA-Z]:[\\/][^\s"\']+|/[^\s"\']+|\.\.[\\/][^\s"\']+)', cmd_text)
            if path_match:
                target_path = path_match.group(0)

        if target_path:
            resolved_target = os.path.realpath(os.path.abspath(target_path))
            if resolved_target == allowed_workspace_norm:
                return "Guardrail Blocked: Deletion of root workspace directory is forbidden."
            if not resolved_target.startswith(allowed_workspace_norm):
                return (
                    f"Guardrail Blocked: Destructive operation outside allowed workspace. "
                    f"Path '{target_path}' is not within '{allowed_workspace}'."
                )
        else:
            # Destructive command with no explicit path requires safety confirmation.
            return "Guardrail Notice: Destructive command requires explicit path inside allowed workspace."

    return None


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
            if not settings.get_github_token():
                return "GitHub Personal Access Token (PAT) is missing. Configure a valid GitHub PAT in Settings."
        return None

    if action == "Tool-exec":
        tool_name = getattr(step_obj, "tool_name", None) or ""
        tool_service = getattr(step_obj, "tool_service", None) or ""
        tool_args = getattr(step_obj, "tool_args", {}) or {}

        if not tool_name:
            return "action='Tool-exec' requires a 'name' in the payload."

        if tool_service == "github" or tool_name.startswith("github_"):
            if not settings.get_github_token():
                return "GitHub Personal Access Token (PAT) is missing. Configure a valid GitHub PAT in Settings."

        # Enforce destructive action guardrail.
        destructive_error = check_destructive_action(tool_name, tool_args)
        if destructive_error:
            return destructive_error

        return None

    return None

