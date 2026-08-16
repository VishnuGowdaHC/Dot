from src.dot.memory.collections.tools_collection import upsert_tools
from src.dot.memory.session_memory.search import search_active_session
from src.dot.memory.session_memory.search import search_past_sessions

NATIVE_TOOLS = {
    "search_active_session": search_active_session,
    "search_past_sessions": search_past_sessions,
    # "query_user_profile": query_user_profile,
    # "query_sqlite": query_sqlite,
}

NATIVE_TOOL_SCHEMAS = {
    "search_active_session": {
        "description": "Search the current session's evicted memory log for a keyword. Use this when the user references past information not in your immediate context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["keyword", "session_id"],
        },
    },
    "search_past_sessions": {
        "description": "Semantically search across PAST conversation sessions for topics discussed before. Use when the user references something from a previous session, not the current one.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "k": {"type": "integer"}},
            "required": ["query"],
        },
    },
    # add more native tool schemas here as you build them
}

def sync_native_tools():
    """Registers native (non-MCP) tools into the same tool registry
    used for MCP discovery, so get_relevant_tools finds both via the
    identical path. Reuses upsert_tools so ID scheme and document
    format always stay consistent with MCP-sourced tools."""
    native_tools = [
        {
            "service": "native",
            "toolName": tool_name,
            "description": spec["description"],
            "inputSchema": spec["inputSchema"],
        }
        for tool_name, spec in NATIVE_TOOL_SCHEMAS.items()
    ]
    upsert_tools(native_tools)
    print("native tools synced")