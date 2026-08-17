TOOL_DEPENDENCIES = {
    "browser_browser_click": ["browser_browser_snapshot"],
    "browser_browser_fill": ["browser_browser_snapshot"],
}


def _has_tool_result(tool_name: str, history_parts: list) -> bool:
    return any(h.get("source_tool") == tool_name for h in history_parts)


def _missing_dependencies(tool_name: str, history_parts: list) -> list:
    required = TOOL_DEPENDENCIES.get(tool_name, [])
    return [req for req in required if not _has_tool_result(req, history_parts)]


def check_guardrails(step_obj, history_parts: list, pending_plan=None) -> str | None:
    """
    Single entry point for all pre-execution validation, keyed by action.
    Returns an error string describing the violation, or None if the
    step is clear to proceed. Callers pass this string to record_error().
    """
    action = step_obj.action

    if action == 'Tool':
        if history_parts and history_parts[-1].get("role") == "tool_found":
            return ("You already found a matching tool in the previous step. "
                    "Do NOT search again — use action='Tool-exec' with the "
                    "tool_name/tool_args from the schema shown, or action='Plan' "
                    "if multiple steps are needed.")
        if not step_obj.get_tool:
            return ("action='Tool' requires get_tool to be set to a search phrase. "
                    "Do not fill tool_name/tool_args yet — that comes after Tool-exec.")
        return None

    if action == 'Tool-exec':
        missing = _missing_dependencies(step_obj.tool_name, history_parts)
        if missing:
            return f"You must call {', '.join(missing)} before {step_obj.tool_name}. Do not guess element roles/names."
        return None

    if action == 'Plan':
        has_tool_lookup = any(h.get("role") == "tool_found" for h in history_parts)
        if not has_tool_lookup:
            return "Do not guess tool names. You MUST use action='Tool' first to search for available tools before creating a Plan."
        if not step_obj.plan_steps:
            return "action='Plan' requires plan_steps to be a non-empty list of concrete tool calls."

        plan_missing = []
        satisfied_within_plan = set()
        for planned_step in step_obj.plan_steps:
            missing = [
                req for req in TOOL_DEPENDENCIES.get(planned_step.tool_name, [])
                if not _has_tool_result(req, history_parts) and req not in satisfied_within_plan
            ]
            if missing:
                plan_missing.append(f"{planned_step.tool_name} needs {', '.join(missing)}")
            satisfied_within_plan.add(planned_step.tool_name)
        if plan_missing:
            corrected_steps = [{"tool_service": "browser", "tool_name": "browser_browser_snapshot", "tool_args": {}}]
            corrected_steps += [
                {"tool_service": s.tool_service, "tool_name": s.tool_name, "tool_args": s.tool_args}
                for s in step_obj.plan_steps
            ]
            return (f"Plan rejected — missing prerequisites: {'; '.join(plan_missing)}. "
                    f"Resubmit this exact corrected plan_steps: {json.dumps(corrected_steps)}")
        return None

    if action == 'Auto-tool':
        if not pending_plan:
            return "Auto-tool called with no plan formed. Emit a 'Plan' action first."
        return None

    return None  # Final and anything else: no guardrails to check