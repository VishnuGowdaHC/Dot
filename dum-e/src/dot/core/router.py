from sentence_transformers import SentenceTransformer, util
from src.dot.core.intentOpener import routeAppOpener
from src.dot.core.engine import reAct_loop
import numpy as np 
from src.dot.core.llm import llm

# Fast Intent Router: classifies commands into fast execution mode vs ReAct agent loop
model = SentenceTransformer('all-MiniLM-L6-v2')

# Focused semantic anchors for desktop application launching
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

# Threshold: Real app launch requests score 0.46 - 1.0; greetings/questions score 0.10 - 0.20
ROUTING_THRESHOLD = 0.45

async def intentRouter(websocket, text, active_session, active_client):
    print(f"In getIntent function: {text}")
    vec = model.encode([text])[0]

    score = util.cos_sim(vec, intentVector)
    bestScore = float(np.max(score.numpy()))
    print(f"Fast execution match score: {bestScore:.4f}")

    # Fast Execution Mode for direct app launching
    if bestScore >= ROUTING_THRESHOLD:
        print(f"[Fast Execution Mode] Routing to routeAppOpener: '{text}'")
        return await routeAppOpener(text)
    else:
        # Full ReAct Agent Loop for questions, greetings, research, web, and complex tasks
        print(f"[ReAct Agent Mode] Routing to LLM: '{text}'")
        return await reAct_loop(websocket, text, llm, session=active_session, active_client=active_client, max_steps=8)
