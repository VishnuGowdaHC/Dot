from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import asyncio
from fastapi.middleware.cors import CORSMiddleware
import threading
from contextlib import asynccontextmanager
import traceback
import json
import uuid

from src.dot.voiceModel.voiceListener import startVoiceListener
from src.dot.core.router import intentRouter
from src.dot.memory.session_memory.manager import SessionStorage
from src.dot.memory.collections.session_collection import embed_session_to_chroma
from src.dot.mcp_files.mcpClient import get_multi_server_client
from src.dot.mcp_files.registry import sync_registry


# Global state to hold the MCP client so all sockets share it
app_state = {}
transcription_queue = asyncio.Queue()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Sync all MCP and native tools into ChromaDB vector store
    print("Syncing tools to ChromaDB...")
    try:
        await sync_registry()
        print("All tools registered in ChromaDB successfully!")
    except Exception as reg_err:
        print(f"[Warning] Tool registration encountered an error: {reg_err}")
        traceback.print_exc()

    # 2. Boot the background voice listener
    print("Starting background voice listener...")
    threading.Thread(target=startVoiceListener, daemon=True).start()
    
    # 3. Boot the MCP servers EXACTLY ONCE for the whole app
    multi_server_client = get_multi_server_client()
    async with multi_server_client as active_client:
        print("MCP Servers initialized and ready globally!")
        app_state["active_mcp_client"] = active_client
        
        # The app runs while this yields
        yield 
        
    print("Shutting down MCP servers...")

# Attach the lifespan to the app
app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def sendToWebsocket(text):
    # Requires main_loop to be defined or passed, but keeping your original logic
    loop = asyncio.get_event_loop()
    asyncio.run_coroutine_threadsafe(transcription_queue.put(text), loop)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_session = SessionStorage(session_id=str(uuid.uuid4()))
    print(f"WebSocket client connected! Session: {active_session.session_id}")
    
    # Fetch the globally running MCP client
    active_client = app_state.get("active_mcp_client")
    
    try:
        while True:
            text = await websocket.receive_text()
            try:
                data = await intentRouter(websocket, text, active_session, active_client)
                
                if data:
                    print(f"Received from dot: {data}")
                    await websocket.send_text(json.dumps({"type": "result", "data": data}))
                    print(f"Sent to frontend: {text}")
                    
            except Exception as router_err:
                print(f"[INTERNAL ROUTER ERROR]: {router_err}")
                traceback.print_exc() # Prints the exact line of code that failed!
                await websocket.send_text(json.dumps({"type": "error", "data": "Agent loop crashed. Check terminal."}))
                
    except WebSocketDisconnect:
        print("WebSocket disconnected normally by client.")
    except Exception as e:
        print(f"[WEBSOCKET CRASH]: {e}")
        traceback.print_exc()
    finally:
        try:
            print(f"Embedding session {active_session.session_id} to Chroma...")
            embed_session_to_chroma(active_session.session_id, active_session.filepath)
            print("Session embedded successfully.")
        except Exception as embed_err:
            print(f"Failed to embed session {active_session.session_id}: {embed_err}")