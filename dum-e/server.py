from fastapi import FastAPI
from pydantic import BaseModel
from src.core.intentRouter import routeIntent
from fastapi.middleware.cors import CORSMiddleware
import threading
from src.core.voiceModel.voiceListener import startVoiceListener


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
    isListening: bool

@app.router.on_event("startup")
def start_voice():
    thread = threading.Thread(target=startVoiceListener, daemon=True).start()


@app.post("/intent")

async def intent(input: Input):
    routeIntent(input.text)
    return { "status": "OK"}