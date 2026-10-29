from src.dot.memory.collections.tools_collection import upsert_tools
from src.dot.memory.search import search_active_session
from src.dot.memory.search import search_past_sessions


NATIVE_TOOLS = {
    "search_active_session": search_active_session,
    "search_past_sessions": search_past_sessions,
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
}

def sync_native_tools():
    """Registers native tools into the ChromaDB tool catalog.
    
    Uses upsert_tools to keep the identifier scheme consistent.
    """
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