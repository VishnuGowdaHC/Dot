import json
import os
import chromadb

path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "storage",
    "chroma_db"
)
chroma_client = chromadb.PersistentClient(path=path)
collection = chroma_client.get_or_create_collection(name='mcp_tools')

def upsert_tools(all_tools: list):
    if not all_tools:
        print("no tools to upsert")
        return

    documents = []
    metadata = []
    ids = []

    for tool in all_tools:
        ids.append(f"{tool['service']}_{tool['toolName']}")
        documents.append(f"{tool['toolName']}: {tool['description']}")
        metadata.append({
            "service": tool["service"],
            "toolName": tool["toolName"],
            "inputSchema": json.dumps(tool["inputSchema"])
        })

    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadata
    )

    print("tools upserted")