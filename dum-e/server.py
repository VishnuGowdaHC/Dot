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

def handle_voice_transcription(text: str):
    if not text:
        return
    print(f"[Voice Callback] Spoken command: '{text}'")
    ws = app_state.get("active_websocket")
    session = app_state.get("active_session")
    client = app_state.get("active_mcp_client")
    main_loop = app_state.get("main_loop")

    if ws and main_loop and main_loop.is_running():
        async def dispatch():
            try:
                # 1. Send the user's spoken words to the UI
                await ws.send_text(json.dumps({"type": "voice_input", "text": text}))
                # 2. Route through intentRouter (runs ReAct loop or fast app opener)
                data = await intentRouter(ws, text, session, client)
                if data:
                    print(f"Received from dot: {data}")
                    await ws.send_text(json.dumps({"type": "result", "data": data}))
            except Exception as err:
                print(f"[Voice Dispatch Error]: {err}")
                traceback.print_exc()

        asyncio.run_coroutine_threadsafe(dispatch(), main_loop)
    else:
        from src.dot.core.intentOpener import routeAppOpener
        try:
            asyncio.run(routeAppOpener(text))
        except Exception as err:
            print(f"[Voice Fallback Error]: {err}")

def handle_voice_status(status: str):
    ws = app_state.get("active_websocket")
    main_loop = app_state.get("main_loop")
    if ws and main_loop and main_loop.is_running():
        async def notify():
            try:
                await ws.send_text(json.dumps({"type": "voice_status", "status": status}))
            except Exception:
                pass
        asyncio.run_coroutine_threadsafe(notify(), main_loop)

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

    # 2. Store the main asyncio event loop for thread-safe dispatch
    app_state["main_loop"] = asyncio.get_running_loop()

    # 3. Boot the Hold-Q background voice listener
    print("Starting Hold-Q background voice listener...")
    threading.Thread(
        target=startVoiceListener,
        args=(handle_voice_transcription, handle_voice_status),
        daemon=True
    ).start()
    
    # 4. Boot the MCP servers EXACTLY ONCE for the whole app
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

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_session = SessionStorage(session_id=str(uuid.uuid4()))
    print(f"WebSocket client connected! Session: {active_session.session_id}")
    
    app_state["active_websocket"] = websocket
    app_state["active_session"] = active_session
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
        if app_state.get("active_websocket") == websocket:
            app_state["active_websocket"] = None
        try:
            print(f"Embedding session {active_session.session_id} to Chroma...")
            embed_session_to_chroma(active_session.session_id, active_session.filepath)
            print("Session embedded successfully.")
        except Exception as embed_err:
            print(f"Failed to embed session {active_session.session_id}: {embed_err}")