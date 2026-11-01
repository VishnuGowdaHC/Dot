"""
Agent step parser and JSON validation utilities.
"""

import json
import re
from typing import Literal, Optional, Any, Dict
from pydantic import BaseModel, field_validator, model_validator


class AgentStep(BaseModel):
    """Represents a single ReAct step produced by the language model."""
    thought: str
    action: Literal["Tool", "Tool-exec", "Final"] = None
    tool_service: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    final_answer: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def remap_legacy_keys(cls, values: Any) -> Any:
        """Normalizes legacy tool naming formats into the standard payload dictionary."""
        if isinstance(values, dict) and not values.get("payload"):
            payload = {}
            action = values.get("action")

            if action == "Tool":
                if values.get("get_tool"):
                    payload["query"] = values.pop("get_tool")
                elif values.get("tool_name"):
                    payload["query"] = values.pop("tool_name")
            else:
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
        return values

    @property
    def get_tool(self) -> Optional[str]:
        """Returns the search query when action is Tool."""
        return self.payload.get("query") if self.payload and self.action == "Tool" else None

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


def extract_json(raw: str) -> Optional[str]:
    """Extracts a valid JSON string from raw model text."""
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    if match:
        return match.group(1).strip()

    stripped = raw.strip()
    if stripped.startswith("{"):
        # Auto-heal missing closing braces if model generation truncated
        if not stripped.endswith("}"):
            stripped += "}"
        return stripped
    return None


def parse_agent_step(extracted_json: str) -> AgentStep:
    """Parses JSON text into an AgentStep instance and normalizes actions."""
    step = AgentStep.model_validate_json(extracted_json)

    # Correct action if the model placed a tool name inside a Tool action payload
    if step.action == "Tool" and step.payload and step.payload.get("name"):
        step.action = "Tool-exec"

    return step

