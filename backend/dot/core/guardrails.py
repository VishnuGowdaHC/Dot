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
            try:
                is_inside = os.path.commonpath([allowed_workspace_norm, resolved_target]) == allowed_workspace_norm
            except ValueError:
                is_inside = False
            if not is_inside:
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
        drill_service = getattr(step_obj, "drill_service", None)
        tool_service = drill_service or getattr(step_obj, "tool_service", None)
        if not is_real_value(tool_query) and not is_real_value(drill_service):
            return "action='Tool' requires a 'query' or 'service' in the payload. Example: {'query': 'search'} or {'service': 'os_tools'}"
        if tool_service == "github" or (tool_query and "github" in str(tool_query).lower()):
            if not settings.get_github_token():
                return "GitHub Personal Access Token (PAT) is missing. Configure a valid GitHub PAT in Settings."
        return None

    if action == "Tool-exec":
        tool_name = getattr(step_obj, "tool_name", None) or ""
        tool_service = getattr(step_obj, "tool_service", None) or ""
        tool_args = getattr(step_obj, "tool_args", {}) or {}

        if not tool_name:
            return "action='Tool-exec' requires 'name' and 'args' in payload. Example: {'name': 'os_replace_text', 'args': {...}}"

        if tool_service == "github" or tool_name.startswith("github_"):
            if not settings.get_github_token():
                return "GitHub Personal Access Token (PAT) is missing. Configure a valid GitHub PAT in Settings."

        # Enforce destructive action guardrail.
        destructive_error = check_destructive_action(tool_name, tool_args)
        if destructive_error:
            return destructive_error

        return None

    return None


PROMISE_PATTERNS = [
    r"\bi (?:will|shall|am going to)(?: now)? (?:paste|type|open|launch|start|click|fill|save|create|extract|run|execute|read)\b",
    r"\bnow (?:pasting|opening|typing|launching|starting|saving|clicking|extracting)\b",
    r"\blet me (?:now )?(?:paste|open|launch|type|start|click|save|run|extract)\b",
    r"\bi (?:will|shall|am going to) proceed to\b",
]

DELIVERY_TOOLS = {
    "browser_fill",
    "agent_browser_fill",
    "os_keyboard_type",
    "os_tools_os_keyboard_type",
    "os_replace_text",
    "os_tools_os_replace_text",
    "write_file",
    "sandbox_write_file",
}

NON_DELIVERY_DESTINATIONS = {
    "chat", "here", "short", "detail", "english", "brief", "words", "sentences",
    "bullet", "bullets", "point", "points", "mind", "advance", "future", "return",
    "fact", "facts", "summary", "response", "reply",
}


def extract_delivery_destination(query: str) -> Optional[str]:
    """Extracts external target surface from user query without hardcoding application names."""
    if not query:
        return None

    pattern = r"\b(?:paste|type|fill|save|write|put|enter|insert)\s+(?:it|this|that|the\s+text|the\s+summary|the\s+code|content|everything|data)?\s*(?:in|into|to)\s+([a-zA-Z0-9_\-\.\s]{2,30})"
    match = re.search(pattern, query, re.IGNORECASE)
    if not match:
        return None

    candidate = match.group(1).strip()
    tokens = candidate.split()
    if not tokens:
        return None

    first_token = tokens[0].lower().rstrip(".,;:")
    if first_token in NON_DELIVERY_DESTINATIONS:
        return None

    if tokens[0].lower() in ("the", "a", "an") and len(tokens) > 1:
        return f"{tokens[0]} {tokens[1]}".lower().rstrip(".,;:")

    return first_token


def check_unfulfilled_delivery(query: str, executed_tool_names: set) -> Optional[str]:
    """Verifies that an external delivery or desktop edit executes before allowing Final action."""
    clean = (query or "").lower()
    has_delivered = any(t in DELIVERY_TOOLS for t in executed_tool_names)

    # Enforce desktop edit completion when user asks to replace/edit text on screen.
    if not has_delivered and re.search(r"\b(replace|edit|rename|overwrite|change)\b", clean):
        if any(k in clean for k in ("screen", "cell", "spreadsheet", "excel", "candidate", "text", "name")):
            if "os_click_text" not in executed_tool_names:
                return (
                    "[System Directive: You have not replaced the target text yet. "
                    "Call os_replace_text(target='...', replacement='...') directly.]"
                )
            return (
                "[System Directive: You clicked the target, but did not type the replacement text yet. "
                "Call os_keyboard_type(text='...') and os_keyboard_press(keys=['enter']) before finishing.]"
            )

    dest = extract_delivery_destination(query)
    if not dest:
        return None
    if not has_delivered:
        return (
            f"[System Directive: The user requested delivery to '{dest}'. "
            "You retrieved content, but you have not delivered it yet. "
            "Identify the target surface and execute the delivery tool before emitting Final.]"
        )
    return None


def check_action_promises(text: str) -> bool:
    """Detects unexecuted future action promises in model output text."""
    if not text:
        return False
    lower = text.lower()
    return any(bool(re.search(pat, lower)) for pat in PROMISE_PATTERNS)


def check_clarify_interception(
    step_obj: Any,
    query: str,
    session: Any,
    history_parts: list,
    normalize_fn: Any,
) -> Optional[str]:
    """Returns a directive message if Clarify should be intercepted, or None to proceed."""
    clarify_text = f"{step_obj.question or ''} {step_obj.thought or ''}"
    has_trivial = bool(
        step_obj.choices and any(
            normalize_fn(c).lower() in ("ok", "yes", "proceed", "continue")
            for c in step_obj.choices
        )
    )
    if check_action_promises(clarify_text) or has_trivial:
        return "[System Directive: Do not emit Clarify to confirm planned actions. Execute the tool using action='Tool-exec'.]"

    has_ctx = bool(session and session.get_context_string() and len(session.get_context_string().strip()) > 40)
    has_obs = any(p.get("role") == "observation" and len(p.get("text", "")) > 40 for p in history_parts)
    is_deliv = bool(
        extract_delivery_destination(query)
        or any(p in query.lower() for p in ("paste", "type", "fill", "save", "this", "that", "it"))
    )
    if (has_ctx or has_obs) and is_deliv:
        return "[System Directive: Content is already available. Execute the delivery tool immediately.]"
    return None

