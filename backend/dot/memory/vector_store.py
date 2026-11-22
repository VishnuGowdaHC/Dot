import json
import os
import re
from typing import Optional
from dot.memory.client import get_collection

tools_collection = get_collection('mcp_tools')

CASUAL_PATTERNS = {
    "hi", "hello", "hey", "yoo", "sup", "howdy", "good morning", "good evening",
    "good afternoon", "how are you", "who are you", "what are you", "what can you do",
    "tell me a joke", "thanks", "thank you", "ok", "okay", "bye", "goodbye", "lol"
}

BYPASS_SERVICES = {"browser", "native", "os_tools", "sandbox"}


def is_casual_query(query: str) -> bool:
    """Detects whether a query is a greeting or casual chat requiring no tools."""
    clean = re.sub(r"[^\w\s]", "", query.lower()).strip()
    return clean in CASUAL_PATTERNS or len(clean.split()) <= 1 and clean in {"hi", "hello", "hey", "sup", "yo"}


def detect_service_hints(query: str) -> list[str]:
    """Detects matching service categories from query keywords."""
    clean = query.lower()
    hints = []

    # Browser automation and search keywords
    browser_keywords = [
        "search", "google", "bing", "look up", "find online", "research",
        "browse", "browser", "website", "webpage", "web", "site", "tab", "link",
        "url", "http://", "https://", "wikipedia", "youtube", "video", "article"
    ]
    if any(k in clean for k in browser_keywords):
        hints.append("browser")

    # OS tools and desktop automation keywords
    os_keywords = [
        "notepad", "calculator", "calc", "explorer", "paint", "word", "excel",
        "app", "application", "program", "desktop", "window", "monitor", "screen",
        "screenshot", "process", "task", "kill", "launch", "open app",
        "type", "typing", "paste", "keyboard", "hotkey", "press key", "mouse", "click"
    ]
    if any(k in clean for k in os_keywords):
        hints.append("os_tools")

    # GitHub API keywords
    github_keywords = [
        "github", "repo", "repository", "commit", "pull request", "pr ", "issue", "branch"
    ]
    if any(k in clean for k in github_keywords):
        hints.append("github")

    # Sandbox environment keywords
    sandbox_keywords = [
        "sandbox", "container", "isolated", "docker"
    ]
    if any(k in clean for k in sandbox_keywords):
        hints.append("sandbox")

    return hints


def detect_service_hint(query: str) -> Optional[str]:
    """Detects the primary service category from query keywords."""
    hints = detect_service_hints(query)
    return hints[0] if hints else None


def get_tool_by_name(tool_name: str) -> Optional[dict]:
    """Retrieves a specific tool entry directly from the collection."""
    candidates = [tool_name, f"os_tools_{tool_name}"]
    for candidate in candidates:
        try:
            results = tools_collection.get(where={"toolName": candidate})
            if results and results.get("metadatas"):
                meta = results["metadatas"][0]
                return {
                    "tool_name": meta["toolName"],
                    "tool_service": meta["service"],
                    "schema": json.loads(meta["inputSchema"]),
                    "description": meta.get("description", ""),
                    "distance": 0.0,
                }
        except Exception:
            continue
    return None


def get_relevant_tools(query: str, service_hint=None, k=2, distance_threshold=1.85):
    """Retrieves relevant tools matching query and optional service hint."""
    selected_tool = []

    # If no query is provided, return all tools for the requested service
    if service_hint in BYPASS_SERVICES and not query:
        results = tools_collection.get(
            where={"service": service_hint}
        )

        if results and results.get("metadatas"):
            for metadata in results["metadatas"]:
                tool_schema = json.loads(metadata["inputSchema"])
                selected_tool.append({
                    "tool_name": metadata["toolName"],
                    "tool_service": metadata["service"],
                    "schema": tool_schema,
                    "description": metadata.get("description", "")
                })

        return selected_tool

    if not query or is_casual_query(query):
        return []

    where_filter = {"service": service_hint} if service_hint else None
    results = tools_collection.query(
        query_texts=[query],
        n_results=k,
        where=where_filter
    )

    if results and "distances" in results and results["distances"]:
        for doc, metadata, distance in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
            if distance <= distance_threshold:
                tool_schema = json.loads(metadata["inputSchema"])
                selected_tool.append({
                    "tool_name": metadata["toolName"],
                    "tool_service": metadata["service"],
                    "schema": tool_schema,
                    "description": metadata.get("description", ""),
                    "distance": distance
                })

    return selected_tool


def format_compact_tool(tool: dict) -> str:
    """Formats a tool into a concise single-line signature for prompt context."""
    schema = tool.get("schema", {})
    props = schema.get("properties", {})
    required = schema.get("required", [])

    args_list = []
    for prop_name, prop_spec in props.items():
        prop_type = prop_spec.get("type", "any")
        if prop_name in required:
            args_list.append(f"{prop_name}: {prop_type}")
        else:
            args_list.append(f"{prop_name}: {prop_type} = null")

    args_str = ", ".join(args_list)
    desc = tool.get("description", "")
    if desc:
        first_line = desc.strip().split("\n")[0]
        return f"- {tool['tool_name']}({args_str}): {first_line}"
    return f"- {tool['tool_name']}({args_str})"


def get_speculative_tools(query: str, k: int = 3, distance_threshold: float = 1.85) -> list[dict]:
    """Retrieves top relevant tools for Turn 0 prompt injection with multi-service support."""
    if not query or is_casual_query(query):
        return []

    clean = query.lower()
    hints = detect_service_hints(query)
    tools: list[dict] = []
    seen: set[str] = set()

    def add_tool(t: Optional[dict]) -> None:
        if t and t["tool_name"] not in seen:
            tools.append(t)
            seen.add(t["tool_name"])

    # High-precision action keyword tool pinning.
    if any(keyword in clean for keyword in ["search", "google", "bing", "look up", "research"]):
        add_tool(get_tool_by_name("browser_search_web"))

    if any(keyword in clean for keyword in ["notepad", "calc", "calculator", "launch", "open app", "start program", "start process", "kill"]):
        add_tool(get_tool_by_name("os_manage_process"))

    if any(keyword in clean for keyword in ["type", "paste", "keyboard", "enter text"]):
        add_tool(get_tool_by_name("os_keyboard_type"))

    if any(keyword in clean for keyword in ["http://", "https://", "wikipedia", "url", "navigate", "website"]):
        add_tool(get_tool_by_name("browser_navigate"))

    # When multiple service domains match, retrieve vector candidates per service.
    if len(hints) > 1:
        k_per_hint = max(2, (k + 1) // len(hints))
        for hint in hints:
            service_tools = get_relevant_tools(query=query, service_hint=hint, k=k_per_hint, distance_threshold=distance_threshold)
            for st in service_tools:
                add_tool(st)
    elif len(hints) == 1:
        service_tools = get_relevant_tools(query=query, service_hint=hints[0], k=k, distance_threshold=distance_threshold)
        for st in service_tools:
            add_tool(st)
        if len(tools) < k:
            fallback = get_relevant_tools(query=query, service_hint=None, k=k, distance_threshold=distance_threshold)
            for ft in fallback:
                add_tool(ft)
                if len(tools) >= k:
                    break
    else:
        general_tools = get_relevant_tools(query=query, service_hint=None, k=k, distance_threshold=distance_threshold)
        for gt in general_tools:
            add_tool(gt)

    return tools[:5]


_available_services_cache = None
def get_all_services(force_refresh=False):
    global _available_services_cache
    if _available_services_cache is None or force_refresh:
        items = tools_collection.get()
        if items and items.get("metadatas"):
            _available_services_cache = {m["service"] for m in items["metadatas"]}
        else:
            _available_services_cache = set()

    return list(_available_services_cache)


def get_full_service_tools_text(service):
    results = get_relevant_tools("", service_hint=service)
    lines = [f"- {t['tool_name']}: {t['schema']}" for t in results]
    return "\n".join(lines)


if __name__ == "__main__":
    item = get_relevant_tools("os tools", service_hint="os_tools")
    print(item)
