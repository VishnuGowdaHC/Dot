import json
from dot.memory.client import get_collection

collection = get_collection('mcp_tools')


def upsert_tools(all_tools: list):
    if not all_tools:
        print("no tools to upsert")
        return

    documents = []
    metadata = []
    ids = []

    for tool in all_tools:
        tool_name = tool["toolName"]
        canonical_name = tool_name if tool_name.startswith(f"{tool['service']}_") else f"{tool['service']}_{tool_name}"
        ids.append(canonical_name)
        documents.append(f"{canonical_name}: {tool.get('description', '')}")
        metadata.append({
            "service": tool["service"],
            "toolName": canonical_name,
            "inputSchema": json.dumps(tool["inputSchema"])
        })

    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadata
    )

    print("tools upserted")
