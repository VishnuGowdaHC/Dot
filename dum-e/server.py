from fastapi import FastAPI, WebSocket
import asyncio
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import threading
from src.core.voiceModel.voiceListener import startVoiceListener
from src.core.intentClassifier import intentRouter


app = FastAPI()

transcription_queue = asyncio.Queue()
main_loop = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Input(BaseModel):
    text: str

def sendToWebsocket(text):
    asyncio.run_coroutine_threadsafe(transcription_queue.put(text), main_loop)

@app.router.on_event("startup")
async def start_voice():
    global main_loop
    main_loop = asyncio.get_running_loop()
    
    print("Starting background voice listener...")
    thread = threading.Thread(target=startVoiceListener, daemon=True).start()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("WebSocket client connected!")
    try:
        while True:
            
            text = await transcription_queue.get()
            
            await websocket.send_text(f'{{"type": "transcription", "text": "{text}"}}')
            print(f"Sent to frontend: {text}")
            
    except Exception as e:
        print(f"WebSocket disconnected: {e}")


@app.post("/intent")

async def intent(input: Input):
    intentRouter(input.text)
    return { "status": "OK"}