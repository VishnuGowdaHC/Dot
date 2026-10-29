"""
Unit tests verifying ASD-STE100 memory compaction and 80 percent threshold behavior.
"""

import os
import sys
import uuid
import unittest

# Ensure dum-e is on python import path.
dum_e_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if dum_e_dir not in sys.path:
    sys.path.insert(0, dum_e_dir)

from src.dot.memory.storage_paths import TRANSCRIPTS_DIR, SUMMARIES_DIR
from src.dot.memory.session import SessionStorage, get_model_context_size
from src.dot.memory.compactor import MemoryCompactor
from src.dot.memory.search import search_active_session
from src.dot.core.utils import async_compress_history


class TestMemoryCompaction(unittest.IsolatedAsyncioTestCase):
    """Tests the memory compaction pipeline under ASD-STE100 specifications."""

    async def test_threshold_calculation(self):
        """Verifies the dynamic 80 percent context calculation."""
        context_size = get_model_context_size()
        self.assertGreater(context_size, 0)

        session = SessionStorage(session_id="test_thresh_" + uuid.uuid4().hex[:6])
        expected_threshold = int(context_size * 0.80)
        self.assertEqual(session.compaction_threshold, expected_threshold)

    async def test_compactor_fallback_and_ste_rules(self):
        """Verifies ASD-STE100 formatting and sentence length constraints."""
        compactor = MemoryCompactor()
        sample_transcript = (
            "User: Launch Chrome and search for documentation.\n"
            "Dot: Executed browser tool and opened the documentation page.\n---\n"
            "User: Find API references for authentication.\n"
            "Dot: Found three endpoints for OAuth authentication.\n"
        )

        summary = await compactor.compact(sample_transcript)
        self.assertIn("### User Facts & Goals", summary)
        self.assertIn("### Actions & Tool Outcomes", summary)
        self.assertIn("### Current Progress & Decisions", summary)

        # Verify all lines comply with ASD-STE100 sentence length limits.
        for line in summary.split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                words = line.split()
                self.assertLessEqual(len(words), 25, f"Line exceeds 25 words: {line}")

    async def test_sliding_window_compaction(self):
        """Verifies verbatim retention of 2 turns and creation of .md snapshots."""
        # Use small context size (80 tokens) with 80% threshold (64 tokens).
        small_context = 80
        session_id = "test_compact_" + uuid.uuid4().hex[:8]
        session = SessionStorage(session_id=session_id, context_size=small_context)

        self.assertEqual(session.compaction_threshold, 64)

        # Add initial turn.
        session.add_turn("What is your name?", "My name is Dot.")
        # Add second turn.
        session.add_turn("What can you do?", "I can automate browser and desktop tasks.")
        # Add third turn.
        session.add_turn("Can you search files?", "Yes, I can search files on your operating system.")
        # Add fourth turn to exceed token budget.
        long_query = "Please read and analyze system architecture logs for issues."
        long_answer = "System architecture logs analyzed. All components are functioning normally."
        session.add_turn(long_query, long_answer)

        # Await compaction explicitly.
        await session.compact_if_needed()

        # Verify last 2 turns are kept verbatim in window.
        self.assertEqual(len(session.window), 2)
        last_turn_text = session.window[-1]["text"]
        self.assertIn(long_query, last_turn_text)

        # Verify transcript file exists in storage/transcripts.
        self.assertTrue(os.path.exists(session.filepath))

        # Verify pre-compaction snapshot was saved to storage/transcripts.
        snapshot_files = [f for f in os.listdir(TRANSCRIPTS_DIR) if f.startswith(f"{session_id}_pre_compact_")]
        self.assertGreaterEqual(len(snapshot_files), 1)

        # Verify summary was written to storage/summaries.
        self.assertTrue(os.path.exists(session.summary_filepath))
        self.assertIsNotNone(session.summary)

        # Verify get_context_string contains ASD-STE100 summary and recent turns.
        ctx_str = session.get_context_string()
        self.assertIn("ASD-STE100 Context Summary", ctx_str)
        self.assertIn(long_query, ctx_str)

        # Verify active session search works on transcript file.
        search_result = search_active_session("Dot", session_id)
        self.assertIn("Past Memory Retrieved", search_result)

    async def test_react_loop_async_compression(self):
        """Verifies async history compression for ReAct loop steps."""
        session = SessionStorage(session_id="test_react_" + uuid.uuid4().hex[:8], context_size=1000)

        # Create substantial observation data simulating browser/filesystem inspection.
        large_obs = "File entry: index.html size: 4096 bytes status: verified.\n" * 30

        history_parts = [
            {"role": "context", "text": "Base instructions and tools.", "pinned": True},
            {"role": "model", "text": "Step 1: check files.", "pinned": False},
            {"role": "observation", "text": f"[Observation from os_list_dir]: {large_obs}", "pinned": False},
            {"role": "model", "text": "Step 2: read config file.", "pinned": False},
            {"role": "observation", "text": f"[Observation from os_read_file]: {large_obs}", "pinned": False},
            {"role": "model", "text": "Step 3: verify service state.", "pinned": False},
            {"role": "observation", "text": "[Observation from os_status]: running.", "pinned": False},
        ]

        orig_tokens = session.count_tokens("\n".join(p["text"] for p in history_parts))
        self.assertGreater(orig_tokens, 300)

        # Compress with target budget lower than total.
        compressed = await async_compress_history(history_parts, session, target_tokens=150)

        # Pinned context must remain.
        self.assertTrue(any(p.get("pinned") for p in compressed))
        # Summary role must be injected.
        self.assertTrue(any(p.get("role") == "summary" for p in compressed))
        # Total tokens must be smaller than original.
        new_tokens = session.count_tokens("\n".join(p["text"] for p in compressed))
        self.assertLess(new_tokens, orig_tokens)


if __name__ == "__main__":
    unittest.main()
