"""
Embeds session transcripts and ASD-STE100 summaries into ChromaDB vector storage.
"""

import os
import re
import time
from src.dot.memory.client import get_collection
from src.dot.memory.storage_paths import TRANSCRIPTS_DIR, SUMMARIES_DIR

# Retrieve the persistent ChromaDB collection for session history.
collection = get_collection("sessions_memory")


def chunk_session_from_md(filepath: str, turns_per_chunk: int = 4) -> list:
    """Reads session transcript and partitions it into turn chunks."""
    # Check if primary filepath exists or fallback to transcripts directory.
    target_path = filepath
    if not os.path.exists(target_path):
        session_id = os.path.splitext(os.path.basename(filepath))[0]
        alt_path = os.path.join(TRANSCRIPTS_DIR, f"{session_id}.md")
        if os.path.exists(alt_path):
            target_path = alt_path
        else:
            return []

    with open(target_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split turns using the separator line.
    raw_turns = [t.strip() for t in content.split("---") if t.strip()]
    # Remove header line from turn collection.
    clean_turns = [t for t in raw_turns if not t.startswith("# Session")]

    return [clean_turns[i:i + turns_per_chunk] for i in range(0, len(clean_turns), turns_per_chunk)]


def summarize_chunk(chunk_text: str) -> str:
    """Extracts concise indicators from a raw transcript chunk."""
    tool_calls = re.findall(r"\[(?:Found tool|Observation from):\s*(\w+)", chunk_text)
    observations = re.findall(r"\[Observation.*?\]:\s*(.{0,80})", chunk_text)
    parts = []
    if tool_calls:
        parts.append(f"Tools used: {', '.join(set(tool_calls))}.")
    if observations:
        parts.append(f"Retrieved {len(observations)} observations.")
    return " ".join(parts) or chunk_text[:150]


def embed_session_to_chroma(session_id: str, filepath: str):
    """Embeds chunked turns and ASD-STE100 summaries into ChromaDB."""
    chunks = chunk_session_from_md(filepath)
    ids, documents, metadatas = [], [], []

    # Embed turn chunks from transcript.
    for idx, chunk in enumerate(chunks):
        chunk_text = "\n".join(chunk)
        summary = summarize_chunk(chunk_text)

        ids.append(f"{session_id}_chunk_{idx}")
        documents.append(summary)
        metadatas.append({
            "session_id": session_id,
            "chunk_idx": idx,
            "type": "turn_chunk",
            "timestamp": time.time(),
        })

    # Check for dedicated ASD-STE100 summary file.
    summary_path = os.path.join(SUMMARIES_DIR, f"{session_id}_summary.md")
    if os.path.exists(summary_path):
        with open(summary_path, "r", encoding="utf-8") as f:
            summary_content = f.read().strip()
        if summary_content:
            ids.append(f"{session_id}_ste_summary")
            documents.append(summary_content)
            metadatas.append({
                "session_id": session_id,
                "type": "asd_ste_summary",
                "timestamp": time.time(),
            })

    if ids:
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
