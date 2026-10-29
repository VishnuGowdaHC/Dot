"""
Compatibility module forwarding session storage requests to the new memory architecture.
"""

from src.dot.memory.session import (
    SessionStorage,
    TRANSCRIPTS_DIR as SESSION_LOG_DIR,
    get_model_context_size,
)

__all__ = ["SessionStorage", "SESSION_LOG_DIR", "get_model_context_size"]
