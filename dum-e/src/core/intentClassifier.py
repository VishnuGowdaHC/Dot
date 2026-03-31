from sentence_transformers import SentenceTransformer, util
from src.core.intentOpener import routeAppOpener
import numpy as np 
from src.core.primaryLLM import routeToLLM


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

def intentRouter(text):
    print(f"In getIntent function: {text}")
    vec = model.encode([text])[0]

    score = util.cos_sim(vec, intentVector)
    cScore = score.numpy()
    idx = np.argmax(cScore)
    bestScore = cScore[0][idx]
    
    print(bestScore)
    if bestScore > 0.3 and len(text.split()) < 5:
        routeAppOpener(text)
    else:
        routeToLLM(text)



    

