from fastapi import FastAPI
from pydantic import BaseModel
from src.core.intentClassifier import get_intent
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Input(BaseModel):
    text: str
@app.post("/intent")

async def intent(input: Input):
    print("user:", input.text)
    intent, score = get_intent(input.text)
    print("intent:", intent, "score:", score)
    return { "status": "OK"}