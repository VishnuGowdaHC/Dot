"""
Unit tests for the RollingMemory state ledger.
Complies with ASD-STE100 technical writing standards.
"""

import sys
from pathlib import Path

# Add backend directory to module search path.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import unittest
from dot.memory.rolling_memory import RollingMemory


class TestRollingMemory(unittest.TestCase):
    """Test suite for the rolling memory state ledger."""

    def test_goal_setting(self):
        """Verifies goal setting and updating."""
        mem = RollingMemory(goal="Initial goal")
        self.assertEqual(mem.goal, "Initial goal")
        mem.set_goal("Updated goal")
        self.assertEqual(mem.goal, "Updated goal")

    def test_step_addition_and_capping(self):
        """Verifies step addition and retention cap of eight items."""
        mem = RollingMemory(goal="Test capping")
        for i in range(12):
            mem.add_step(f"Action {i}", f"Outcome {i}", exit_code=0)

        self.assertEqual(len(mem.completed_steps), 8)
        self.assertEqual(mem.completed_steps[0]["action"], "Action 4")
        self.assertEqual(mem.completed_steps[-1]["action"], "Action 11")

    def test_error_recording(self):
        """Verifies error registration and deduplication."""
        mem = RollingMemory(goal="Test errors")
        mem.add_error("Network timeout")
        mem.add_error("Network timeout")
        mem.add_error("File not found")

        self.assertEqual(len(mem.known_errors), 2)
        self.assertIn("Network timeout", mem.known_errors)

    def test_file_registration(self):
        """Verifies registered file tracking."""
        mem = RollingMemory(goal="Test files")
        mem.register_file("app.py")
        mem.register_file("app.py")
        mem.register_file("test.py")

        self.assertEqual(len(mem.created_files), 2)
        self.assertIn("app.py", mem.created_files)

    def test_render_context(self):
        """Verifies ASD-STE100 formatted context string output."""
        mem = RollingMemory(goal="Build a script")
        mem.register_file("script.py")
        mem.add_step("Write script.py", "File written", exit_code=0)
        mem.add_error("Import warning")

        ctx = mem.render_context()
        self.assertIn("### Active Goal", ctx)
        self.assertIn("Build a script", ctx)
        self.assertIn("### Workspace Files", ctx)
        self.assertIn("script.py", ctx)
        self.assertIn("### Actions & Tool Outcomes", ctx)
        self.assertIn("Step 1: Write script.py -> Success: File written", ctx)
        self.assertIn("### Known Blockers & Errors", ctx)
        self.assertIn("Import warning", ctx)


if __name__ == "__main__":
    unittest.main()

