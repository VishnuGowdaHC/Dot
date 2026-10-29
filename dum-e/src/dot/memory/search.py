"""
Memory search module for active session transcripts and past vector sessions.
"""

import os
from src.dot.memory.client import get_collection
from src.dot.memory.storage_paths import TRANSCRIPTS_DIR

# Initialize ChromaDB session collection instance.
session_collection = get_collection("sessions_memory")

# Fallback directory for older legacy session files.
LEGACY_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session_memory", "session_logs")


def _find_session_file(session_id: str) -> str:
    """Finds the transcript file in standard storage or legacy directories."""
    primary_path = os.path.join(TRANSCRIPTS_DIR, f"{session_id}.md")
    if os.path.exists(primary_path):
        return primary_path
    legacy_path = os.path.join(LEGACY_LOG_DIR, f"{session_id}.md")
    if os.path.exists(legacy_path):
        return legacy_path
    return primary_path


def search_active_session(keyword: str, session_id: str) -> str:
    """Searches the current session transcript file for a keyword."""
    filepath = _find_session_file(session_id)

    if not os.path.exists(filepath):
        return f"Session log {session_id} does not exist yet."

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if not content.strip():
        return "Session log is currently empty."

    # Perform case-insensitive search across transcript text.
    index = content.lower().find(keyword.lower())
    if index == -1:
        return f"No matches found for '{keyword}'."

    # Slice context surrounding the keyword match.
    start = max(0, index - 300)
    end = min(len(content), index + 300)
    chunk = content[start:end]
    return f"--- Past Memory Retrieved ---\n...{chunk}..."


def search_past_sessions(query: str, k: int = 3) -> str:
    """Queries vector storage for relevant conversation turns across past sessions."""
    results = session_collection.query(query_texts=[query], n_results=k)
    if not results or not results.get("documents") or not results["documents"][0]:
        return "No relevant past sessions found."

    lines = []
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        lines.append(f"[Session {meta['session_id']}, chunk {meta['chunk_idx']}]: {doc}")
    return "\n".join(lines)
