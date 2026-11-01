import os
import sys
import warnings
import logging

# Suppress harmless upstream PyTorch and HuggingFace Hub startup warnings
warnings.filterwarnings("ignore", category=UserWarning, module="torch.ao.nn.quantized")
warnings.filterwarnings("ignore", message=".*unauthenticated requests to the HF Hub.*")
warnings.filterwarnings("ignore", message=".*quantized tensor creation functions.*")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
import asyncio
from fastapi.middleware.cors import CORSMiddleware
import threading
from contextlib import asynccontextmanager
import traceback
import json
import uuid

from src.dot.voiceModel.voiceListener import startVoiceListener
from src.dot.core.router import intentRouter
from src.dot.memory.session import SessionStorage
from src.dot.memory.collections.session_collection import embed_session_to_chroma
from src.dot.mcp_files.mcpClient import get_multi_server_client
from src.dot.mcp_files.registry import sync_registry


# Global application state shared across active WebSocket connections.
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
                # Send transcribed voice input to the client user interface.
                await ws.send_text(json.dumps({"type": "voice_input", "text": text}))
                # Route through intentRouter to execute tools or direct actions.
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
    # Store the main asyncio event loop for thread-safe operations.
    app_state["main_loop"] = asyncio.get_running_loop()

    # Start the background voice listener thread.
    print("Starting background voice listener...")
    threading.Thread(
        target=startVoiceListener,
        args=(handle_voice_transcription, handle_voice_status),
        daemon=True
    ).start()

    # Start the MCP client session once for the entire application lifecycle.
    multi_server_client = get_multi_server_client()
    async with multi_server_client as active_client:
        print("MCP servers initialized and ready globally.")
        app_state["active_mcp_client"] = active_client

        # Synchronize tools using the active client session to prevent duplicate process launches.
        print("Syncing tools to ChromaDB...")
        try:
            await sync_registry(active_client=active_client)
            print("All tools registered in ChromaDB successfully.")
        except Exception as reg_err:
            print(f"[Warning] Tool registration encountered an error: {reg_err}")
            traceback.print_exc()

        # The application runs while this context yields.
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


def _get_app_config_path() -> str:
    """Finds the absolute path of appConfig.json."""
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "appConfig.json"),
        os.path.join(os.path.dirname(__file__), "appConfig.json"),
        os.path.abspath("appConfig.json"),
        os.path.abspath("../appConfig.json"),
    ]
    return next((os.path.abspath(p) for p in candidates if os.path.exists(p)), os.path.abspath("../appConfig.json"))


def _read_app_config() -> dict:
    """Reads configuration settings from appConfig.json."""
    path = _get_app_config_path()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _write_app_config(cfg: dict) -> None:
    """Writes updated configuration settings to appConfig.json."""
    path = _get_app_config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)


def _update_github_token(token: str) -> None:
    """Updates the GitHub token in process memory and environment files."""
    os.environ["GITHUB_TOKEN"] = token
    candidate_paths = [
        os.path.join(os.path.dirname(__file__), ".env"),
        os.path.join(os.path.dirname(__file__), "src", "dot", ".env"),
    ]
    for env_path in candidate_paths:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(env_path)), exist_ok=True)
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(f'GITHUB_TOKEN="{token}"\n')
        except Exception:
            pass


@app.get("/api/settings")
async def get_settings():
    """Returns current active system and cloud settings."""
    cfg = _read_app_config()
    gh_token = os.environ.get("GITHUB_TOKEN") or cfg.get("github_token", "")
    return {
        "active_settings": cfg.get("active_settings", {}),
        "cloud": cfg.get("cloud", {}),
        "models": cfg.get("models", {}),
        "backends": cfg.get("backends", {}),
        "github_token": gh_token
    }


@app.post("/api/settings")
async def update_settings(request: Request):
    """Updates settings and reloads the inference clients."""
    payload = await request.json()
    cfg = _read_app_config()
    active = cfg.setdefault("active_settings", {})
    cloud = cfg.setdefault("cloud", {})

    if "backend" in payload:
        active["backend"] = payload["backend"]
    if "selected_tier" in payload:
        active["selected_tier"] = payload["selected_tier"]
    if "browser_headless" in payload:
        active["browser_headless"] = bool(payload["browser_headless"])
    if "cloud" in payload and isinstance(payload["cloud"], dict):
        for k, v in payload["cloud"].items():
            cloud[k] = v
    if "github_token" in payload:
        gh_token = str(payload["github_token"]).strip()
        cfg["github_token"] = gh_token
        _update_github_token(gh_token)

    _write_app_config(cfg)

    # Reload LLM clients dynamically.
    from src.dot.core.llm import reload_llm_clients
    reload_llm_clients()

    # Update active session context size if active.
    active_session = app_state.get("active_session")
    if active_session:
        tier = active.get("selected_tier", "4B")
        backend = active.get("backend", "cuda")
        if backend == "cloud":
            active_session.context_size = 16384
        else:
            model_info = cfg.get("models", {}).get(tier, {})
            active_session.context_size = model_info.get("context_size", 8192)

    # Broadcast updated settings if websocket is open.
    ws = app_state.get("active_websocket")
    if ws:
        try:
            await ws.send_text(json.dumps({
                "type": "settings_updated",
                "data": {
                    "active_settings": active,
                    "cloud": cloud,
                    "github_token": cfg.get("github_token", "")
                }
            }))
        except Exception:
            pass

    return {
        "status": "ok",
        "active_settings": active,
        "cloud": cloud,
        "github_token": cfg.get("github_token", "")
    }


@app.post("/api/browser/toggle")
async def toggle_browser_headless():
    """Toggles headless mode for browser automation."""
    cfg = _read_app_config()
    active = cfg.setdefault("active_settings", {})
    current = bool(active.get("browser_headless", False))
    active["browser_headless"] = not current
    _write_app_config(cfg)

    ws = app_state.get("active_websocket")
    if ws:
        try:
            await ws.send_text(json.dumps({
                "type": "browser_status",
                "data": {"browser_headless": active["browser_headless"]}
            }))
        except Exception:
            pass

    return {"status": "ok", "browser_headless": active["browser_headless"]}


@app.get("/api/mcp/servers")
async def get_mcp_servers():
    """Returns the list of configured MCP servers."""
    from src.dot.mcp_files.registry import load_server_config
    cfg = load_server_config()
    servers = list(cfg.get("mcpServers", {}).keys())
    return {"servers": servers}


@app.post("/api/mcp/sync")
async def mcp_sync_registry():
    """Synchronizes tools from all configured MCP servers."""
    active_client = app_state.get("active_mcp_client")
    try:
        await sync_registry(active_client=active_client)
        from src.dot.memory.vector_store import get_all_services
        services = get_all_services(force_refresh=True)
        return {"status": "ok", "services": services}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_session = SessionStorage(session_id=str(uuid.uuid4()))
    print(f"WebSocket client connected! Session: {active_session.session_id}")
    
    app_state["active_websocket"] = websocket
    app_state["active_session"] = active_session
    active_client = app_state.get("active_mcp_client")
    
    # Broadcast initial context token baseline including the system prompt
    from src.dot.core.prompts import get_system_prompt
    try:
        sys_text = f"<|think|> {get_system_prompt()}"
        sys_tokens = active_session.count_tokens(sys_text)
        hist_tokens = active_session.current_tokens
        total_tokens = sys_tokens + hist_tokens
        limit = active_session.context_size
        pct = round((total_tokens / limit) * 100, 1) if limit > 0 else 0
        await websocket.send_text(json.dumps({
            "type": "token_usage",
            "data": {
                "total_tokens": total_tokens,
                "context_limit": limit,
                "system_tokens": sys_tokens,
                "history_tokens": hist_tokens,
                "compaction_threshold": active_session.compaction_threshold,
                "percentage": pct
            }
        }))
    except Exception as e:
        print(f"[Initial Token Telemetry Warning]: {e}")

    # Broadcast initial browser headless status
    try:
        cfg = _read_app_config()
        is_headless = bool(cfg.get("active_settings", {}).get("browser_headless", False))
        await websocket.send_text(json.dumps({
            "type": "browser_status",
            "data": {"browser_headless": is_headless}
        }))
    except Exception:
        pass
    
    try:
        while True:
            text = await websocket.receive_text()
            try:
                data = await intentRouter(websocket, text, active_session, active_client)
                
                if data:
                    print(f"Received from dot: {data}")
                    await websocket.send_text(json.dumps({"type": "result", "data": data}))
                    print(f"Sent to frontend: {text}")

                # Broadcast updated token telemetry after turn execution
                try:
                    sys_text = f"<|think|> {get_system_prompt()}"
                    sys_tokens = active_session.count_tokens(sys_text)
                    hist_tokens = active_session.current_tokens
                    total_tokens = sys_tokens + hist_tokens
                    limit = active_session.context_size
                    pct = round((total_tokens / limit) * 100, 1) if limit > 0 else 0
                    await websocket.send_text(json.dumps({
                        "type": "token_usage",
                        "data": {
                            "total_tokens": total_tokens,
                            "context_limit": limit,
                            "system_tokens": sys_tokens,
                            "history_tokens": hist_tokens,
                            "compaction_threshold": active_session.compaction_threshold,
                            "percentage": pct
                        }
                    }))
                except Exception:
                    pass
                    
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
            print(f"[Server] Embedding session {active_session.session_id} to ChromaDB...")
            await asyncio.to_thread(embed_session_to_chroma, active_session.session_id, active_session.filepath)
            print("[Server] Session embedded successfully.")
        except Exception as embed_err:
            print(f"[Server Warning] Failed to embed session {active_session.session_id}: {embed_err}")