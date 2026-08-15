import json
import chromadb
import os

path = os.path.join(os.path.dirname(__file__), "storage", "chroma_db")
chroma_client = chromadb.PersistentClient(path=path)
collection = chroma_client.get_or_create_collection(name='mcp_tools')

def get_relevant_tools(query: str, distance_threshold=0.8, k=2, service_hint=None):
    print(f"query: {query}")
    results = collection.query(
        query_texts=[query],
        n_results=k,
        where={"service": service_hint} if service_hint else None
    )

    selected_tool = []
    
    if results and "distances" in results and results["distances"]:
        for doc, metadata, distance in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
            if distance <= distance_threshold:
                tool_schema = json.loads(metadata["inputSchema"])
                selected_tool.append({
                    "tool_name": metadata["toolName"],
                    "tool_service": metadata["service"],
                    "schema": tool_schema
                })
    if not selected_tool and results["distances"][0]:
        best_idx = results["distances"][0].index(min(results["distances"][0]))
        metadata = results["metadatas"][0][best_idx]
        tool_schema = json.loads(metadata["inputSchema"])
        selected_tool.append({
            "tool_name": metadata["toolName"],
            "tool_service": metadata["service"],
            "schema": tool_schema
        })

    return selected_tool