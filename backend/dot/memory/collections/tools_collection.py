import json
from dot.memory.client import get_collection

collection = get_collection('mcp_tools')


def clear_tools(service: str = None) -> None:
    """Removes stored tools from ChromaDB to purge obsolete entries."""
    try:
        if service:
            existing = collection.get(where={"service": service})
        else:
            existing = collection.get()
        if existing and existing.get("ids"):
            collection.delete(ids=existing["ids"])
    except Exception as e:
        print(f"[Tools Collection Warning] Failed to clear tools: {e}")


def upsert_tools(all_tools: list, clear_before: bool = False):
    if not all_tools:
        print("no tools to upsert")
        return

    if clear_before:
        # Determine unique services present in all_tools to clear their stale entries
        services_to_clear = {t["service"] for t in all_tools if "service" in t}
        for s in services_to_clear:
            clear_tools(s)

    documents = []
    metadata = []
    ids = []
    seen_ids = set()

    for tool in all_tools:
        tool_name = tool["toolName"]
        canonical_name = tool_name if tool_name.startswith(f"{tool['service']}_") else f"{tool['service']}_{tool_name}"
        if canonical_name in seen_ids:
            continue
        seen_ids.add(canonical_name)
        ids.append(canonical_name)
        documents.append(f"{canonical_name}: {tool.get('description', '')}")
        metadata.append({
            "service": tool["service"],
            "toolName": canonical_name,
            "description": tool.get("description", ""),
            "inputSchema": json.dumps(tool["inputSchema"])
        })

    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadata
    )

    print("tools upserted")
