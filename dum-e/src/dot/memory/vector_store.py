import json
import chromadb
import os

path = os.path.join(os.path.dirname(__file__), "storage", "chroma_db")
chroma_client = chromadb.PersistentClient(path=path)
tools_collection = chroma_client.get_or_create_collection(name='mcp_tools')

def get_relevant_tools(query: str, service_hint=None, k=2, distance_threshold=0.8,  ):
    print(f"query: {query}")
    selected_tool = []

    BYPASS_SERVICES = {"browser", "native"}
    if service_hint in BYPASS_SERVICES:
        results = tools_collection.get(
            where={"service": service_hint}
        )

        if results and results.get("metadatas"):
            for metadata in results["metadatas"]:
                tool_schema = json.loads(metadata["inputSchema"])
                selected_tool.append({
                    "tool_name": metadata["toolName"],
                    "tool_service": metadata["service"],
                    "schema": tool_schema
                })

        return selected_tool

    results = tools_collection.query(
        query_texts=[query],
        n_results=k,
        where={"service": service_hint} if service_hint else None
    )
    
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

_available_services_cache = None
def get_all_services(force_refresh=False):
    global _available_services_cache
    if _available_services_cache is None or force_refresh:
        items = tools_collection.get()

        _available_services_cache = {m["service"] for m in items["metadatas"]}
    
    return list(_available_services_cache)

def get_full_service_tools_text(service):
    results = get_relevant_tools("", service_hint=service)  # your existing bypass returns everything
    lines = [f"- {t['tool_name']}: {t['schema']}" for t in results]
    return "\n".join(lines)

if __name__ == "__main__":
    item = get_all_services(force_refresh=True)
    print(item)

