from sentence_transformers import SentenceTransformer, util
from src.core.intentRouter import routeIntent
import numpy as np 


model = SentenceTransformer('all-MiniLM-L6-v2')

automation_anchors = [
    "open the browser", 
    "launch spotify", 
    "start notepad", 
    "go to google.com",
    "turn off the computer",
    "what time is it",
    "open website",
    "open app",
    "lauch"
]

intentVector = model.encode(automation_anchors)

def getIntent(text):
    print(f"In getIntent function: {text}")
    vec = model.encode([text])[0]

    score = util.cos_sim(vec, intentVector)
    cScore = score.numpy()
    idx = np.argmax(cScore)
    bestScore = cScore[0][idx]
    print(bestScore)
    if bestScore > 0.3:
        routeIntent(text)
    else:
        print("Routing to LLM")



    

