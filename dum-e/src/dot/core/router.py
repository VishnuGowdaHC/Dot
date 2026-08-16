from sentence_transformers import SentenceTransformer, util
from src.dot.automation.intentOpener import routeAppOpener
from src.dot.core.engine import reAct_loop
import numpy as np 
import uuid
from src.dot.core.llm import llm

model = SentenceTransformer('all-MiniLM-L6-v2')


automation_anchors = [
    "open the browser", 
    "open spotify", 
    "start notepad", 
    "go to google.com",
    "turn off the computer",
    "what time is it",
    "open website",
    "open app",
    "open",
    "start",
    "go to",
]

intentVector = model.encode(automation_anchors)

async def intentRouter(websocket, text, active_session):
    print(f"In getIntent function: {text}")
    vec = model.encode([text])[0]

    score = util.cos_sim(vec, intentVector)
    cScore = score.numpy()
    idx = np.argmax(cScore)
    bestScore = cScore[0][idx]
    
    print(bestScore)
    
    if (bestScore > 0.3) and (len(text.split()) < 6):
        return await routeAppOpener(text)
    else:
        return await reAct_loop(websocket, text, llm, session=active_session, max_steps=8)
         



    

