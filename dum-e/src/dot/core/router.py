import asyncio
import numpy as np
from sentence_transformers import SentenceTransformer, util
from src.dot.core.intentOpener import routeAppOpener
from src.dot.core.engine import reAct_loop
from src.dot.memory.vector_store import get_speculative_tools

# Intent Router: classifies commands into fast execution mode or ReAct agent loop.
model = SentenceTransformer('all-MiniLM-L6-v2')

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
    "watch video on youtube"
]

intentVector = model.encode(app_launch_anchors)

# Routing threshold: Application launch or media requests score 0.45 or higher.
ROUTING_THRESHOLD = 0.45

async def intentRouter(websocket, text: str, active_session, active_client):
    """Classifies user intent and routes to direct execution or ReAct loop."""
    print(f"[Intent Router] Evaluating input: '{text}'")

    # Run PyTorch embedding calculation in worker thread to prevent event loop blocking.
    vec = await asyncio.to_thread(lambda: model.encode([text])[0])

    score = util.cos_sim(vec, intentVector)
    bestScore = float(np.max(score.numpy()))
    print(f"[Intent Router] Fast execution match score: {bestScore:.4f}")

    # Direct Execution Mode for desktop applications and media.
    if bestScore >= ROUTING_THRESHOLD:
        print(f"[Fast Execution Mode] Routing to routeAppOpener: '{text}'")
        return await routeAppOpener(text)
    
    # Pre-retrieve speculative tools in worker thread for ReAct loop (<15ms).
    speculative_tools = await asyncio.to_thread(get_speculative_tools, text, 3)

    # ReAct Agent Loop for questions, research, and multi-step tasks.
    print(f"[ReAct Agent Mode] Routing to ReAct loop with {len(speculative_tools)} speculative tools: '{text}'")
    return await reAct_loop(
        websocket,
        text,
        session=active_session,
        active_client=active_client,
        max_steps=8,
        speculative_tools=speculative_tools
    )

