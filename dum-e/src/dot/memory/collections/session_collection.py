import os
import re
import time
import chromadb

path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "storage",
    "chroma_db"
)
chroma_client = chromadb.PersistentClient(path=path)
collection = chroma_client.get_or_create_collection(name='sessions_memory')

def chunk_session_from_md(filepath, turns_per_chunk=4):
    """Reads the full session .md log and groups it into fixed-size
    chunks by turn, using the 'User: ... \\nDot: ...' / '---' separator
    your SessionStorage.add_turn already writes."""
    if not os.path.exists(filepath):
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # split on the '---' separator add_turn writes after every turn
    raw_turns = [t.strip() for t in content.split("---") if t.strip()]
    # drop the header line ("# Session ... \nStarted at: ...") if present
    raw_turns = [t for t in raw_turns if not t.startswith("# Session")]

    return [raw_turns[i:i+turns_per_chunk] for i in range(0, len(raw_turns), turns_per_chunk)]

def summarize_chunk(chunk_text: str) -> str:
    tool_calls = re.findall(r"\[Found tool: (\w+)", chunk_text)
    observations = re.findall(r"\[Observation: (.{0,80})", chunk_text)
    parts = []
    if tool_calls:
        parts.append(f"tools used: {', '.join(tool_calls)}")
    if observations:
        parts.append(f"{len(observations)} observation(s) retrieved, details discarded")
    return "; ".join(parts) or chunk_text[:150]  # fall back to raw excerpt, not a generic label

def embed_session_to_chroma(session_id: str, filepath: str):
    chunks = chunk_session_from_md(filepath)
    ids, documents, metadatas = [], [], []

    for idx, chunk in enumerate(chunks):
        chunk_text = "\n".join(chunk)
        summary = summarize_chunk(chunk_text)

        ids.append(f"{session_id}_{idx}")
        documents.append(summary)
        metadatas.append({
            "session_id": session_id,
            "chunk_idx": idx,
            "timestamp": time.time(),
        })

    if ids:
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)