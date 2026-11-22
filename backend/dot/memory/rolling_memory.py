"""
Rolling memory state ledger for autonomous execution turns.
Maintains compact ASD-STE100 progress records under 500 tokens.
Complies with ASD-STE100 technical writing standards.
"""

from typing import List, Dict, Any, Optional


class RollingMemory:
    """Stores compact execution state across continuous agent turns."""

    def __init__(self, goal: str = ""):
        self.goal: str = goal
        self.hypotheses: List[str] = []
        self.completed_steps: List[Dict[str, Any]] = []
        self.known_errors: List[str] = []
        self.created_files: List[str] = []

    def set_goal(self, goal: str) -> None:
        """Sets the primary task goal."""
        self.goal = goal.strip()

    def add_step(self, action: str, outcome: str, exit_code: int = 0) -> None:
        """Records an executed action and its outcome."""
        clean_action = action.strip()[:100]
        clean_outcome = outcome.strip()[:160]
        self.completed_steps.append({
            "action": clean_action,
            "outcome": clean_outcome,
            "exit_code": exit_code
        })
        # Keep maximum 8 recent steps to prevent context bloat.
        if len(self.completed_steps) > 8:
            self.completed_steps.pop(0)

    def add_error(self, error: str) -> None:
        """Records an error message."""
        clean_error = error.strip()[:120]
        if clean_error not in self.known_errors:
            self.known_errors.append(clean_error)
            if len(self.known_errors) > 4:
                self.known_errors.pop(0)

    def register_file(self, filename: str) -> None:
        """Records a file path created in the workspace."""
        clean_name = filename.strip()
        if clean_name and clean_name not in self.created_files:
            self.created_files.append(clean_name)

    def render_context(self) -> str:
        """Renders the rolling state into structured ASD-STE100 text."""
        lines = []

        # Goal section
        lines.append("### Active Goal")
        if self.goal:
            lines.append(f"- {self.goal}")
        else:
            lines.append("- Complete the requested task.")

        # Created files
        if self.created_files:
            lines.append("\n### Workspace Files")
            files_str = ", ".join(self.created_files[:10])
            lines.append(f"- Available files: {files_str}.")

        # Completed steps
        lines.append("\n### Actions & Tool Outcomes")
        if self.completed_steps:
            for i, step in enumerate(self.completed_steps, 1):
                status = "Success" if step["exit_code"] == 0 else f"Failed (code {step['exit_code']})"
                lines.append(f"- Step {i}: {step['action']} -> {status}: {step['outcome']}.")
        else:
            lines.append("- No actions executed yet.")

        # Errors section
        if self.known_errors:
            lines.append("\n### Known Blockers & Errors")
            for err in self.known_errors:
                lines.append(f"- {err}.")

        return "\n".join(lines)

    def clear(self) -> None:
        """Clears all rolling memory records."""
        self.goal = ""
        self.hypotheses.clear()
        self.completed_steps.clear()
        self.known_errors.clear()
        self.created_files.clear()


_ROLLING_MEMORY_INSTANCE: Optional[RollingMemory] = None


def get_rolling_memory() -> RollingMemory:
    """Returns the singleton rolling memory instance."""
    global _ROLLING_MEMORY_INSTANCE
    if _ROLLING_MEMORY_INSTANCE is None:
        _ROLLING_MEMORY_INSTANCE = RollingMemory()
    return _ROLLING_MEMORY_INSTANCE

