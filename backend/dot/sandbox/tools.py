"""
Sandbox execution tools and schema definitions for the ReAct loop.
Complies with ASD-STE100 technical writing standards.
"""

import asyncio
from typing import Dict, Any, Optional

from dot.sandbox.executor import exec_in_sandbox
from dot.sandbox.browser import sandboxed_navigate_and_extract, sandboxed_search_web, sandboxed_screenshot
from dot.sandbox.intervention import get_intervention_manager


async def tool_sandbox_exec(command: str) -> str:
    """Executes a shell command inside the isolated Docker sandbox."""
    code, output = await exec_in_sandbox(command)
    clean_output = output.strip() or "(No output)"
    if code != 0:
        return f"Command exited with error code {code}:\n{clean_output}"
    return clean_output


async def tool_sandbox_browser_navigate(url: str) -> str:
    """Navigates to a webpage in the sandbox browser and extracts text."""
    return await sandboxed_navigate_and_extract(url)


async def tool_sandbox_browser_search(query: str) -> str:
    """Performs a web search in the sandbox browser and returns snippets."""
    return await sandboxed_search_web(query)


async def tool_sandbox_screenshot(url: str, output_name: str = "screenshot.png") -> str:
    """Captures a screenshot of a URL in the sandboxed browser and saves to /workspace."""
    return await sandboxed_screenshot(url, output_name)


async def tool_request_human_intervention(reason: str, command: str = "") -> str:
    """Pauses execution and requests confirmation or manual CLI input from user."""
    mgr = get_intervention_manager()
    return await mgr.request_intervention(reason=reason, command=command)


SANDBOX_TOOLS = {
    "sandbox_exec": tool_sandbox_exec,
    "sandbox_browser_navigate": tool_sandbox_browser_navigate,
    "sandbox_browser_search": tool_sandbox_browser_search,
    "sandbox_screenshot": tool_sandbox_screenshot,
    "request_human_intervention": tool_request_human_intervention,
    "sandbox_request_human_intervention": tool_request_human_intervention,
}

SANDBOX_TOOL_SCHEMAS = {
    "sandbox_exec": {
        "description": "Execute a bash shell command inside the lightweight isolated Docker sandbox. Use this to run scripts, git commands, npm, or tests safely.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command string to execute in /workspace"}
            },
            "required": ["command"]
        }
    },
    "sandbox_browser_navigate": {
        "description": "Navigate to a URL using the sandboxed headless browser (0 MB VRAM) and extract readable body text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The full HTTP/HTTPS URL"}
            },
            "required": ["url"]
        }
    },
    "sandbox_browser_search": {
        "description": "Search the web using the isolated sandboxed browser and extract search results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword or question"}
            },
            "required": ["query"]
        }
    },
    "sandbox_screenshot": {
        "description": "Capture a full-page screenshot of a URL in the sandboxed browser. Saves the PNG to /workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The full HTTP/HTTPS URL to capture"},
                "output_name": {"type": "string", "description": "Output filename (default: screenshot.png)"}
            },
            "required": ["url"]
        }
    },
    "request_human_intervention": {
        "description": "Pause execution to ask the user for confirmation, authentication, or manual CLI input in the sandbox.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Explanation of why user intervention is required"},
                "command": {"type": "string", "description": "Optional suggested command for the user to verify"}
            },
            "required": ["reason"]
        }
    }
}

