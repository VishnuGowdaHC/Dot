"""
Session memory module managing sliding window history and ASD-STE100 compaction.
"""

import os
import time
import json
import asyncio
from collections import deque
from typing import Optional, List, Dict, Any

from src.dot.memory.storage_paths import TRANSCRIPTS_DIR, SUMMARIES_DIR
from src.dot.memory.tokenizer import get_tokenizer, count_tokens
from src.dot.memory.compactor import MemoryCompactor

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_model_context_size() -> int:
    """Reads context size from appConfig.json with a safe fallback."""
    possible_paths = [
        os.path.join(_CURRENT_DIR, "..", "..", "..", "appConfig.json"),
        os.path.join(_CURRENT_DIR, "..", "..", "..", "..", "appConfig.json"),
        os.path.abspath("appConfig.json"),
        os.path.abspath("../appConfig.json"),
    ]
    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                return int(cfg.get("active_settings", {}).get("context_size", 8192))
            except Exception:
                pass
    return 8192


class SessionStorage:
    """Stores conversation turns and compacts context when the threshold is reached."""

    def __init__(self, session_id: str, context_size: Optional[int] = None):
        # Initialize session identifier and token limits.
        self.session_id = session_id
        self.context_size = context_size or get_model_context_size()
        # Trigger compaction at 80 percent of model context capacity.
        self.compaction_threshold = int(self.context_size * 0.80)

        # Configure file paths for transcripts and summaries.
        self.filepath = os.path.join(TRANSCRIPTS_DIR, f"{session_id}.md")
        self.summary_filepath = os.path.join(SUMMARIES_DIR, f"{session_id}_summary.md")

        # Initialize sliding window state.
        self.window: deque[Dict[str, Any]] = deque()
        self.summary: Optional[str] = None
        self.current_tokens = 0

        # Load shared tokenizer singleton and memory compactor.
        self.tokenizer = get_tokenizer()
        self.compactor = MemoryCompactor()

        # Create persistent session file if missing.
        self._ensure_file()

    def count_tokens(self, text: str) -> int:
        """Counts the tokens in the specified text string."""
        return count_tokens(text)

    def _ensure_file(self):
        """Initializes the session log file if it does not exist."""
        if not os.path.exists(self.filepath):
            with open(self.filepath, "w", encoding="utf-8") as f:
                f.write(f"# Session {self.session_id}\nStarted at: {time.ctime()}\n\n")

    def _append_turn(self, user_query: str, final_answer: str) -> Dict[str, Any]:
        """Appends a turn to disk and updates the in-memory window."""
        self._ensure_file()
        turn_text = f"User: {user_query}\nDot: {final_answer}\n"
        turn_tokens = self.count_tokens(turn_text)

        # Write turn to persistent transcript log.
        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(f"{turn_text}\n---\n")

        turn_entry = {"text": turn_text, "tokens": turn_tokens}
        self.window.append(turn_entry)
        self.current_tokens += turn_tokens
        return turn_entry

    def add_turn(self, user_query: str, final_answer: str):
        """Adds a turn to the session and starts compaction if needed."""
        self._append_turn(user_query, final_answer)

        # Check token threshold against the 80 percent limit.
        if self.current_tokens >= self.compaction_threshold:
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    return loop.create_task(self.compact_if_needed())
            except RuntimeError:
                pass
        return None

    async def compact_if_needed(self):
        """Compacts older turns into an ASD-STE100 summary if over threshold."""
        if self.current_tokens < self.compaction_threshold:
            return

        # Retain last 2 turns verbatim to preserve immediate conversational context.
        if len(self.window) <= 2:
            return

        # Snapshot full uncompressed context to markdown before compaction.
        self._snapshot_pre_compaction()

        # Pop last 2 turns from window to preserve them.
        recent_turns: List[Dict[str, Any]] = []
        recent_turns.append(self.window.pop())
        recent_turns.append(self.window.pop())
        recent_turns.reverse()

        # Collect older turns for summarization.
        older_turns = list(self.window)
        older_text = "\n---\n".join(t["text"] for t in older_turns)

        # Generate fresh ASD-STE100 summary via FastMCP sampling.
        new_summary = await self.compactor.compact(older_text, previous_summary=self.summary)
        self.summary = new_summary

        # Write updated summary to dedicated summary file.
        self._save_summary()

        # Rebuild sliding window with preserved recent turns.
        self.window.clear()
        for turn in recent_turns:
            self.window.append(turn)

        # Recalculate total tokens in active window.
        summary_tokens = self.count_tokens(self.summary) if self.summary else 0
        recent_tokens = sum(t["tokens"] for t in self.window)
        self.current_tokens = summary_tokens + recent_tokens

    def _snapshot_pre_compaction(self):
        """Saves uncompressed conversation state to disk before compaction."""
        timestamp = int(time.time())
        snapshot_filename = f"{self.session_id}_pre_compact_{timestamp}.md"
        snapshot_path = os.path.join(TRANSCRIPTS_DIR, snapshot_filename)

        all_text = "\n".join(t["text"] for t in self.window)
        content = (
            f"# Session Pre-Compaction Snapshot\n"
            f"Session ID: {self.session_id}\n"
            f"Timestamp: {time.ctime()}\n"
            f"Token Count: {self.current_tokens}\n"
            f"Threshold: {self.compaction_threshold}\n\n"
            f"## Active Context\n{all_text}\n"
        )

        with open(snapshot_path, "w", encoding="utf-8") as f:
            f.write(content)

    def _save_summary(self):
        """Persists the active ASD-STE100 summary to disk."""
        if not self.summary:
            return

        content = (
            f"# ASD-STE100 Session Summary\n"
            f"Session ID: {self.session_id}\n"
            f"Updated At: {time.ctime()}\n\n"
            f"{self.summary}\n"
        )

        with open(self.summary_filepath, "w", encoding="utf-8") as f:
            f.write(content)

    def get_context_string(self) -> str:
        """Returns the active context string including summary and recent turns."""
        parts = []

        # Prepend ASD-STE100 summary when present.
        if self.summary:
            parts.append(f"[ASD-STE100 Context Summary:\n{self.summary}\n]")

        # Append recent uncompressed turns.
        for turn in self.window:
            parts.append(turn["text"].strip())

        if not parts:
            return "No previous history."

        return "\n\n".join(parts)
