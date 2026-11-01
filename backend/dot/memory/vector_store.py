import json
import os
import re
from dot.memory.client import get_collection

tools_collection = get_collection('mcp_tools')

CASUAL_PATTERNS = {
    "hi", "hello", "hey", "yoo", "sup", "howdy", "good morning", "good evening",
    "good afternoon", "how are you", "who are you", "what are you", "what can you do",
    "tell me a joke", "thanks", "thank you", "ok", "okay", "bye", "goodbye", "lol"
}


def is_casual_query(query: str) -> bool:
    """Detects whether a query is a greeting or casual chat requiring no tools."""
    clean = re.sub(r"[^\w\s]", "", query.lower()).strip()
    return clean in CASUAL_PATTERNS or len(clean.split()) <= 1 and clean in {"hi", "hello", "hey", "sup", "yo"}


def get_relevant_tools(query: str, service_hint=None, k=2, distance_threshold=1.40):
    """Retrieves relevant tools matching query and optional service hint."""
    selected_tool = []

    # If no query is provided, return all tools for the requested service
    BYPASS_SERVICES = {"browser", "native", "os_tools"}
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


def get_speculative_tools(query: str, k: int = 3, distance_threshold: float = 1.40) -> list[dict]:
    """Retrieves top-k relevant tools for Turn 0 prompt injection with threshold gating."""
    if not query or is_casual_query(query):
        return []
    return get_relevant_tools(query=query, service_hint=None, k=k, distance_threshold=distance_threshold)


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
