from sentence_transformers import SentenceTransformer
import numpy as np


model = SentenceTransformer('all-MiniLM-L6-v2')

intents = [
    "open leetcode",
    "open youtube",
    "start leetcode",
    "chat with ai",
    "yo open yt"
]

intentVector = model.encode(intents)

def get_intent(text):
    vec = model.encode([text])[0]

    score = np.dot(intentVector, vec) / (np.linalg.norm(intentVector, axis=1)*np.linalg.norm(vec))

    idx = np.argmax(score)

    return intents[idx], score[idx]

