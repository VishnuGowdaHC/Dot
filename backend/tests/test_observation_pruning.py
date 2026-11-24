"""
Unit tests for ephemeral observation pruning and token optimization.
Follows ASD-STE100 guidelines.
"""

import unittest
from dot.core.utils import prune_obsolete_observations


class TestObservationPruning(unittest.TestCase):
    """Verifies that older screen inspections are compressed while preserving the latest active state."""

    def test_prune_replaces_older_dom_snapshots(self):
        """Verify older DOM snapshots are condensed and latest snapshot remains intact."""
        history = [
            {"role": "context", "text": "Task: Answer questions 1 through 5", "pinned": True},
            # Turn 1:
            {"role": "model", "text": '{"action": "Tool-exec", "payload": {"name": "browser_navigate"}}', "pinned": False},
            {
                "role": "observation",
                "text": "[Observation from browser_navigate]: Page: Python Quiz\n- Question 1: What is def?\n- option 1 [@e1]\n- option 2 [@e2]\n" + ("x" * 2000),
                "source_tool": "browser_navigate",
                "pinned": False,
            },
            # Turn 2:
            {"role": "model", "text": '{"action": "Tool-exec", "payload": {"name": "browser_click", "args": {"selector": "@e2"}}}', "pinned": False},
            {
                "role": "observation",
                "text": "[Observation from browser_click]: Clicked @e2 successfully.",
                "source_tool": "browser_click",
                "pinned": False,
            },
            # Turn 3:
            {"role": "model", "text": '{"action": "Tool-exec", "payload": {"name": "browser_snapshot"}}', "pinned": False},
            {
                "role": "observation",
                "text": "[Observation from browser_snapshot]: Page: Python Quiz - Question 2\n- Question 2: What is class?\n- option 1 [@e4]\n- option 2 [@e5]\n" + ("y" * 2000),
                "source_tool": "browser_snapshot",
                "pinned": False,
            },
        ]

        pruned = prune_obsolete_observations(history)
        self.assertEqual(len(pruned), len(history))

        # First observation (Turn 1 navigate) should be compressed to milestone summary
        obs1 = pruned[2]["text"]
        self.assertIn("compressed", obs1.lower())
        self.assertLess(len(obs1), 300)

        # Second observation (Turn 2 click) was small, should be preserved
        obs2 = pruned[4]["text"]
        self.assertIn("Clicked @e2", obs2)

        # Third observation (Turn 3 snapshot) is the latest active screen state and must remain fully intact!
        obs3 = pruned[6]["text"]
        self.assertIn("Question 2: What is class?", obs3)
        self.assertIn("y" * 1000, obs3)

    def test_prune_noop_when_only_one_observation(self):
        """Verify pruning leaves single observation untouched."""
        history = [
            {"role": "context", "text": "Task: Answer question", "pinned": True},
            {"role": "model", "text": '{"action": "Tool-exec"}', "pinned": False},
            {
                "role": "observation",
                "text": "[Observation from browser_snapshot]: Only one snapshot here.\n" + ("z" * 1000),
                "source_tool": "browser_snapshot",
                "pinned": False,
            },
        ]
        pruned = prune_obsolete_observations(history)
        self.assertEqual(pruned[2]["text"], history[2]["text"])

    def test_prune_preserves_extracted_text_across_multi_step(self):
        """Verify browser_extract_text is never compressed even when subsequent tools execute."""
        extracted_content = "Top Story: 2035 Came Early\nPoints: 519\n" + ("Story detail line.\n" * 50)
        history = [
            {"role": "context", "text": "Task: Extract and paste into Notepad", "pinned": True},
            # Turn 1:
            {"role": "model", "text": '{"action": "Tool-exec", "payload": {"name": "browser_extract_text"}}', "pinned": False},
            {
                "role": "observation",
                "text": f"[Observation from browser_extract_text]: {extracted_content}",
                "source_tool": "browser_extract_text",
                "pinned": False,
            },
            # Turn 2:
            {"role": "model", "text": '{"action": "Tool-exec", "payload": {"name": "os_manage_process", "args": {"action": "start", "process_name": "notepad.exe"}}}', "pinned": False},
            {
                "role": "observation",
                "text": "[Observation from os_manage_process]: Successfully launched notepad.exe.",
                "source_tool": "os_manage_process",
                "pinned": False,
            },
        ]
        pruned = prune_obsolete_observations(history)
        self.assertEqual(len(pruned), len(history))

        # Extracted content must remain fully intact for the next typing step
        obs1 = pruned[2]["text"]
        self.assertNotIn("compressed", obs1.lower())
        self.assertIn("Top Story: 2035 Came Early", obs1)
        self.assertEqual(obs1, history[2]["text"])

    def test_prune_preserves_web_search_results(self):
        """Verify search results are preserved when subsequent tools execute."""
        search_data = "Result 1: Andrew Ng biography\nResult 2: DeepLearning.AI\n" + ("snippet\n" * 30)
        history = [
            {"role": "context", "text": "Task: Search and paste", "pinned": True},
            # Turn 1:
            {"role": "model", "text": '{"action": "Tool-exec", "payload": {"name": "browser_search_web"}}', "pinned": False},
            {
                "role": "observation",
                "text": f"[Observation from browser_search_web]: {search_data}",
                "source_tool": "browser_search_web",
                "pinned": False,
            },
            # Turn 2:
            {"role": "model", "text": '{"action": "Tool-exec", "payload": {"name": "os_manage_process"}}', "pinned": False},
            {
                "role": "observation",
                "text": "[Observation from os_manage_process]: Launched application.",
                "source_tool": "os_manage_process",
                "pinned": False,
            },
        ]
        pruned = prune_obsolete_observations(history)
        obs1 = pruned[2]["text"]
        self.assertEqual(obs1, history[2]["text"])


if __name__ == "__main__":
    unittest.main()
