"""
Compatibility search module delegating to the unified memory search implementation.
"""

from src.dot.memory.search import search_active_session, search_past_sessions

__all__ = ["search_active_session", "search_past_sessions"]
