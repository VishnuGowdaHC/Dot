import asyncio
import numpy as np
from sentence_transformers import SentenceTransformer, util
from src.dot.core.intentOpener import routeAppOpener
from src.dot.core.engine import reAct_loop

# Intent Router: classifies commands into fast execution mode or ReAct agent loop.
model = SentenceTransformer('all-MiniLM-L6-v2')

# Focused semantic anchors for desktop application launching.
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
    "open vscode"
]

intentVector = model.encode(app_launch_anchors)

# Routing threshold: Application launch requests score 0.45 or higher.
ROUTING_THRESHOLD = 0.45

async def intentRouter(websocket, text: str, active_session, active_client):
    """Classifies user intent and routes to direct execution or ReAct loop."""
    print(f"[Intent Router] Evaluating input: '{text}'")

    # Run PyTorch embedding calculation in worker thread to prevent event loop blocking.
    vec = await asyncio.to_thread(lambda: model.encode([text])[0])

    score = util.cos_sim(vec, intentVector)
    bestScore = float(np.max(score.numpy()))
    print(f"[Intent Router] Fast execution match score: {bestScore:.4f}")

    # Direct Execution Mode for desktop applications.
    if bestScore >= ROUTING_THRESHOLD:
        print(f"[Fast Execution Mode] Routing to routeAppOpener: '{text}'")
        return await routeAppOpener(text)
    
    # ReAct Agent Loop for questions, research, and multi-step tasks.
    print(f"[ReAct Agent Mode] Routing to ReAct loop: '{text}'")
    return await reAct_loop(websocket, text, session=active_session, active_client=active_client, max_steps=8)

