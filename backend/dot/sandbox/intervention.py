"""
Human intervention coordinator for the Dot sandbox.
Manages agent pause states, user approvals, and CLI command injection.
Complies with ASD-STE100 technical writing standards.
"""

import json
import asyncio
from typing import Optional, Any

from dot.sandbox.manager import pause_sandbox, unpause_sandbox


class InterventionManager:
    """Coordinates agent pause states and human-in-the-loop actions."""

    def __init__(self):
        self.is_paused = False
        self.pause_reason: Optional[str] = None
        self.suggested_command: Optional[str] = None
        self._resume_event = asyncio.Event()
        self._user_feedback: Optional[str] = None
        self._lock: Optional[asyncio.Lock] = None
        self._lock_loop: Optional[asyncio.AbstractEventLoop] = None

    def _get_lock(self) -> asyncio.Lock:
        """Returns an asyncio lock bound to the active event loop."""
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock_loop is not loop:
            self._lock = asyncio.Lock()
            self._lock_loop = loop
        return self._lock

    async def request_intervention(
        self,
        reason: str,
        command: Optional[str] = None,
        websocket: Optional[Any] = None,
    ) -> str:
        """Pauses the autonomous execution loop and waits for user resolution."""
        async with self._get_lock():
            self.is_paused = True
            self.pause_reason = reason
            self.suggested_command = command
            self._resume_event.clear()
            self._user_feedback = None

            # Freeze container processes during human intervention.
            await pause_sandbox()

            # Notify the active WebSocket client.
            if websocket:
                try:
                    payload = json.dumps({
                        "type": "intervention_required",
                        "data": {
                            "reason": reason,
                            "suggested_command": command,
                        },
                    })
                    await websocket.send_text(payload)
                except Exception as err:
                    print(f"[Intervention Error] WebSocket dispatch failed: {err}")

            print(f"[Intervention Required] Reason: '{reason}'. Waiting for human resolution...")

            try:
                # Wait asynchronously until user submits approval or manual changes.
                await self._resume_event.wait()
            finally:
                # Always unfreeze container processes and clear pause state.
                await unpause_sandbox()
                self.is_paused = False
                self.pause_reason = None
                self.suggested_command = None

            return self._user_feedback or "Action approved by user."

    def submit_resolution(self, feedback: Optional[str] = None) -> None:
        """Resumes the autonomous execution loop with optional user feedback."""
        self._user_feedback = feedback
        self._resume_event.set()


_INTERVENTION_INSTANCE: Optional[InterventionManager] = None


def get_intervention_manager() -> InterventionManager:
    """Returns the singleton InterventionManager instance."""
    global _INTERVENTION_INSTANCE
    if _INTERVENTION_INSTANCE is None:
        _INTERVENTION_INSTANCE = InterventionManager()
    return _INTERVENTION_INSTANCE
