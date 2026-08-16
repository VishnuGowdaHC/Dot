import os
import time
from collections import deque
from transformers import AutoTokenizer

current_dir = os.path.dirname(os.path.abspath(__file__))
SESSION_LOG_DIR = os.path.join(current_dir, "session_logs")

os.makedirs(SESSION_LOG_DIR, exist_ok=True)
tokenizer_path = os.path.join(current_dir, "..", "tokenizer_files")

class SessionStorage:
    def __init__(self, session_id: str, max_tokens: int = 4000):
        self.session_id = session_id
        self.max_tokens = max_tokens
        self.filepath = os.path.join(SESSION_LOG_DIR, f"{session_id}.md")
        self.window = deque()
        self.current_tokens = 0
        
        # Use Gemma's fast tokenizer for accurate counting
        self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_path)
        
        # Initialize the .md file
        if not os.path.exists(self.filepath):
            with open(self.filepath, "w", encoding="utf-8") as f:
                f.write(f"# Session {self.session_id}\nStarted at: {time.ctime()}\n\n")

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text))

    def add_turn(self, user_query: str, final_answer: str):
        """Adds a turn to the sliding window AND persists it immediately."""
        turn_text = f"User: {user_query}\nDot: {final_answer}\n"
        turn_tokens = self.count_tokens(turn_text)

        # Persist immediately — never lose a turn to a crash or short session
        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(f"{turn_text}\n---\n")

        self.window.append({"text": turn_text, "tokens": turn_tokens})
        self.current_tokens += turn_tokens

        self._evict_if_needed()


    def _evict_if_needed(self):
        """Drops oldest turns from the in-memory window once over budget.
        No write here — add_turn already persisted everything to disk."""
        while self.window and self.current_tokens > self.max_tokens:
            evicted_turn = self.window.popleft()
            self.current_tokens -= evicted_turn["tokens"]

    def get_context_string(self) -> str:
        """Returns history as a single string."""
        if not self.window:
            return "No previous history."
        return "\n".join([turn["text"] for turn in self.window])