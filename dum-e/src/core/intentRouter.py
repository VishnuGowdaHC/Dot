from src.core.intentClassifier import get_intent
from src.core.automationEngine import openWeb

intents = [
    "open leetcode",
    "open youtube",
    "start leetcode",
    "open chatgpt",
    "chat with ai",
    "yo open yt"
]

def routeIntent(text):
    intent, score = get_intent(text)
    print(intent, score)
    for i in range(len(intents)):
        if (intents[i] == intent) & (score > 0.5):
            if intent == "open youtube" :
                openWeb("youtube")
            elif intent == "open leetcode" :
                openWeb("leetcode")
            elif intent == "open chatgpt":
                openWeb("chatgpt")
            
