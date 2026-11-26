"""
Agent step parser and JSON validation utilities.
"""

import json
import re
from typing import Literal, Optional, Any, Dict, List
from pydantic import BaseModel, field_validator, model_validator


def normalize_choice_text(choice: Any) -> str:
    """Normalizes a choice item into a clean string."""
    if choice is None:
        return ""
    if isinstance(choice, str):
        return choice.strip()
    if isinstance(choice, dict):
        for key in ("text", "label", "choice", "value", "title", "name"):
            val = choice.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
        for val in choice.values():
            if val is not None and str(val).strip():
                return str(val).strip()
        return ""
    return str(choice).strip()


class AgentStep(BaseModel):
    """Represents a single ReAct step produced by the language model."""
    thought: str
    action: Literal["Tool", "Tool-exec", "Clarify", "Final"]
    tool_service: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    question: Optional[str] = None
    choices: Optional[List[str]] = None
    final_answer: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def remap_legacy_keys(cls, values: Any) -> Any:
        """Normalizes legacy tool naming formats into the standard payload dictionary."""
        if isinstance(values, dict):
            # Clarify action validation
            action = values.get("action")
            if action == "Clarify":
                if not values.get("question") and values.get("thought"):
                    values["question"] = values.get("thought")

            # Normalize choices list to clean strings
            raw_choices = values.get("choices")
            if raw_choices is not None:
                if isinstance(raw_choices, (list, tuple, set)):
                    cleaned = [normalize_choice_text(c) for c in raw_choices]
                    values["choices"] = [c for c in cleaned if c]
                elif isinstance(raw_choices, (str, dict)):
                    cleaned = normalize_choice_text(raw_choices)
                    values["choices"] = [cleaned] if cleaned else []
                else:
                    values["choices"] = []

            if not values.get("payload"):
                payload = {}

                if action == "Tool":
                    if values.get("get_tool"):
                        payload["query"] = values.pop("get_tool")
                    elif values.get("tool_name"):
                        payload["query"] = values.pop("tool_name")
                    if values.get("service"):
                        payload["service"] = values.pop("service")
                elif action == "Tool-exec":
                    if values.get("tool_name"):
                        payload["name"] = values.pop("tool_name")
                    if values.get("tool_args"):
                        args = values.pop("tool_args")
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except Exception:
                                args = {}
                        payload["args"] = args if isinstance(args, dict) else {}

                if payload:
                    values["payload"] = payload

            if action == "Tool-exec" and isinstance(values.get("payload"), dict):
                p = dict(values["payload"])
                if "name" not in p and "tool_name" in p:
                    p["name"] = p.pop("tool_name")
                if "args" not in p:
                    for alt in ("arguments", "params"):
                        if alt in p and isinstance(p[alt], dict):
                            p["args"] = p.pop(alt)
                            break
                extra_keys = [k for k in list(p.keys()) if k not in ("name", "args")]
                if extra_keys:
                    args_dict = dict(p.get("args")) if isinstance(p.get("args"), dict) else {}
                    for k in extra_keys:
                        args_dict[k] = p.pop(k)
                    p["args"] = args_dict
                values["payload"] = p
        return values

    @property
    def get_tool(self) -> Optional[str]:
        """Returns the search query when action is Tool."""
        return self.payload.get("query") if self.payload and self.action == "Tool" else None

    @property
    def drill_service(self) -> Optional[str]:
        """Returns the target service name for drill-down when action is Tool."""
        if not self.action == "Tool":
            return None
        if self.payload and self.payload.get("service"):
            return self.payload.get("service")
        return self.tool_service

    @property
    def tool_name(self) -> Optional[str]:
        """Returns the target tool name when action is Tool-exec."""
        return self.payload.get("name") if self.payload and self.action == "Tool-exec" else None

    @property
    def tool_args(self) -> Dict[str, Any]:
        """Returns the target tool arguments when action is Tool-exec."""
        return self.payload.get("args", {}) if self.payload and self.action == "Tool-exec" else {}

    @field_validator("payload", mode="before")
    @classmethod
    def parse_payload(cls, val: Any) -> Dict[str, Any]:
        """Parses raw string payloads into dictionaries."""
        if isinstance(val, str):
            try:
                return json.loads(val)
            except Exception:
                return {}
        return val or {}


def heal_truncated_json(text: str) -> str:
    """Heal truncated JSON text by closing open strings, brackets, and braces."""
    in_string = False
    escape = False
    stack = []

    for char in text:
        if escape:
            escape = False
            continue
        if char == '\\' and in_string:
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if not in_string:
            if char in ('{', '['):
                stack.append('}' if char == '{' else ']')
            elif char in ('}', ']'):
                if stack and stack[-1] == char:
                    stack.pop()

    healed = text
    if in_string:
        healed += '"'
    while stack:
        healed += stack.pop()
    return healed


def extract_json(raw: str) -> Optional[str]:
    """Extracts and heals a valid JSON string from model text."""
    # Match complete markdown fenced code blocks.
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    if match:
        return heal_truncated_json(match.group(1).strip())

    # Match incomplete markdown fenced code blocks where output was cut off.
    incomplete_match = re.search(r"```(?:json)?\s*(\{.*)", raw, re.DOTALL)
    if incomplete_match:
        return heal_truncated_json(incomplete_match.group(1).strip())

    stripped = raw.strip()
    if stripped.startswith("{"):
        return heal_truncated_json(stripped)

    # Locate the first opening brace if text contains leading commentary.
    brace_idx = raw.find("{")
    if brace_idx != -1:
        return heal_truncated_json(raw[brace_idx:].strip())

    return None


def parse_agent_step(extracted_json: str) -> AgentStep:
    """Parses JSON text into an AgentStep instance and normalizes actions."""
    step = AgentStep.model_validate_json(extracted_json)

    # Correct action if the model placed a tool name inside a Tool action payload
    if step.action == "Tool" and step.payload and step.payload.get("name"):
        step.action = "Tool-exec"

    return step

