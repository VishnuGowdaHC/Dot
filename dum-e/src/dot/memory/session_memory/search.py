import os
import mmap
import time
import json
import chromadb

path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "storage",
    "chroma_db"
)
chroma_client = chromadb.PersistentClient(path=path)
session_collection = chroma_client.get_or_create_collection(name='sessions_memory')

def search_active_session(keyword: str, session_id: str) -> str:
    """
    Searches the current session's evicted .md memory log for a keyword. 
    Use this when the user references past information not in your immediate context.
    """
    filepath = os.path.join(os.path.dirname(__file__), "memory", "session_logs", f"{session_id}.md")
    
    if not os.path.exists(filepath):
        return f"Session log {session_id} does not exist yet."

    keyword_bytes = keyword.lower().encode('utf-8')
    
    with open(filepath, "r") as f:
        # Prevent mmap from crashing on empty files
        if os.fstat(f.fileno()).st_size == 0:
            return "Session log is currently empty."
            
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            index = mm.find(keyword_bytes)
            
            if index == -1:
                return f"No matches found for '{keyword}'."
                
            # Slice 300 bytes of context around the match
            start = max(0, index - 300)
            end = min(mm.size(), index + 300)
            
            chunk = mm[start:end].decode('utf-8', errors='ignore')
            return f"--- Past Memory Retrieved ---\n...{chunk}..."

def search_past_sessions(query: str, k: int = 3) -> str:
    results = session_collection.query(query_texts=[query], n_results=k)
    if not results or not results.get("documents") or not results["documents"][0]:
        return "No relevant past sessions found."

    lines = []
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        lines.append(f"[Session {meta['session_id']}, chunk {meta['chunk_idx']}]: {doc}")
    return "\n".join(lines)