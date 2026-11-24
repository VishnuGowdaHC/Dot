"""
Intent classifier and execution router.
Routes inputs between fast native execution and the autonomous ReAct loop.
"""

import asyncio
import re
from typing import Any, Optional
import numpy as np
from sentence_transformers import SentenceTransformer, util

from dot.automation.app_opener import routeAppOpener
from dot.core.context import stream_response
from dot.core.engine import reAct_loop
from dot.memory.vector_store import get_speculative_tools
from dot.memory.rolling_memory import get_rolling_memory

# Intent Router: classifies commands into fast execution mode or ReAct agent loop.
_model = None
_intent_vector = None


def _get_intent_model():
    """Loads SentenceTransformer and encodes anchors lazily on first use."""
    global _model, _intent_vector
    if _model is None:
        try:
            _model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
        except Exception:
            _model = SentenceTransformer("all-MiniLM-L6-v2")
    if _intent_vector is None:
        _intent_vector = _model.encode(app_launch_anchors)
    return _model, _intent_vector

AFFIRMATION_WORDS = {
    "ok", "okay", "yes", "sure", "proceed", "go ahead", "do it",
    "continue", "yep", "yeah", "alright", "all right", "yes please",
}


def is_affirmation_query(text: str) -> bool:
    """Detects whether user query is an affirmative confirmation phrase.

    Complies with ASD-STE100 rules.
    """
    clean = re.sub(r"[^\w\s]", "", text.strip().lower())
    return clean in AFFIRMATION_WORDS


def resolve_continuation_query(text: str, rolling_mem: Any) -> str:
    """Expands an affirmative response into active goal instructions when goal is pending.

    Complies with ASD-STE100 rules.
    """
    if is_affirmation_query(text) and rolling_mem and getattr(rolling_mem, "goal", ""):
        return f"Proceed and complete the active goal: {rolling_mem.goal}"
    return text

# Semantic anchors for fast application launching and media playback.
app_launch_anchors = [
    "open app",
    "open application",
    "start program",
    "launch app",
    "launch application",
    "open software",
    "open spotify",
    "open browser",
    "start notepad",
    "open chrome",
    "open calculator",
    "open steam",
    "open vscode",
    "play song",
    "play music",
    "play video",
    "play song on youtube",
    "play video on youtube",
    "play on yt",
    "listen to music",
    "watch video on youtube",
]

# Routing threshold: Application launch or media requests score 0.45 or higher.
ROUTING_THRESHOLD = 0.45


def _score_intent(text: str) -> float:
    """Encodes text and computes max cosine similarity against launch anchors."""
    mdl, vecs = _get_intent_model()
    vec = mdl.encode([text])[0]
    score = util.cos_sim(vec, vecs)
    return float(np.max(score.numpy()))


async def intentRouter(websocket, text: str, active_session, active_client):
    """Classifies user intent and routes to direct execution or ReAct loop."""
    print(f"[Intent Router] Evaluating input: '{text}'")

    rolling_mem = get_rolling_memory()
    effective_query = resolve_continuation_query(text, rolling_mem)
    if effective_query != text:
        print(f"[Intent Router] Affirmation detected. Continuing active goal: '{effective_query}'")

    # Run PyTorch embedding calculation in worker thread to prevent event loop blocking.
    best_score = await asyncio.to_thread(_score_intent, text)
    print(f"[Intent Router] Fast execution match score: {best_score:.4f}")

    # Direct execution mode applies only to short commands (under 6 words).
    # Complex questions and conversational queries must route to the ReAct loop.
    words = text.strip().split()
    lower_text = text.lower()
    is_conversational = any(
        lower_text.startswith(prefix) for prefix in [
            "how", "why", "what", "can you", "could you", "please explain", "help"
        ]
    ) or any(
        keyword in lower_text for keyword in ["github", "pr", "pull request", "issue", "commit", "branch"]
    )

    if effective_query == text and best_score >= ROUTING_THRESHOLD and len(words) <= 5 and not is_conversational:
        print(f"[Fast Execution Mode] Routing to routeAppOpener: '{text}'")
        res = await routeAppOpener(text)
        if res:
            if websocket:
                await stream_response(websocket, res)
            return res

    # Pre-retrieve speculative tools in worker thread for ReAct loop (<15ms).
    speculative_tools = await asyncio.to_thread(get_speculative_tools, effective_query, 3)

    # ReAct Agent Loop for questions, research, and multi-step tasks.
    print(f"[ReAct Agent Mode] Routing to ReAct loop with {len(speculative_tools)} speculative tools: '{effective_query}'")
    return await reAct_loop(
        websocket,
        effective_query,
        session=active_session,
        active_client=active_client,
        max_steps=10,
        speculative_tools=speculative_tools,
    )

