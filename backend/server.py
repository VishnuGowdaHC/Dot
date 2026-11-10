"""
FastAPI application server and WebSocket communication bridge for Dot.
"""

import os
import sys

# Configure standard streams for UTF-8 with error replacement to prevent cp1252 encode crashes
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import json
import uuid
import asyncio
import logging
import warnings
import traceback
import threading
from pathlib import Path
from typing import Optional, Any, Dict
from contextlib import asynccontextmanager

# Suppress harmless upstream PyTorch and HuggingFace Hub startup warnings.
warnings.filterwarnings("ignore", category=UserWarning, module="torch.ao.nn.quantized")
warnings.filterwarnings("ignore", message=".*unauthenticated requests to the HF Hub.*")
warnings.filterwarnings("ignore", message=".*quantized tensor creation functions.*")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware

# Ensure backend root is on python module path.
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from dot.config.settings import (
    load_config,
    save_config,
    get_github_token,
    update_github_token,
    is_browser_headless,
    set_browser_headless,
)
from dot.voice.listener import startVoiceListener
from dot.core.router import intentRouter
from dot.core.prompts import get_system_prompt
from dot.core.llm import reload_llm_clients
from dot.automation.app_opener import routeAppOpener
from dot.memory.session import SessionStorage
from dot.memory.collections.session_collection import embed_session_to_chroma
from dot.memory.vector_store import get_all_services
from dot.mcp.client import get_multi_server_client
from dot.mcp.registry import sync_registry, load_server_config
from dot.sandbox.manager import (
    is_docker_available,
    is_sandbox_running,
    is_sandbox_paused,
    start_sandbox,
    stop_sandbox,
    pause_sandbox,
    unpause_sandbox,
)
from dot.sandbox.executor import exec_in_sandbox
from dot.sandbox.intervention import get_intervention_manager

# Global state dictionary shared across active WebSocket connections.
app_state = {}

_turn_lock = asyncio.Lock()
_active_turn_task: Optional[asyncio.Task] = None


async def execute_turn_safely(websocket, text: str, session, client):
    """Executes a user turn and cancels any active previous turn to prevent collisions."""
    global _active_turn_task
    current_task = asyncio.current_task()

    if _active_turn_task and not _active_turn_task.done() and _active_turn_task != current_task:
        print(f"[Turn Dispatcher] Cancelling previous turn for new input: '{text}'")
        _active_turn_task.cancel()
        try:
            await _active_turn_task
        except (asyncio.CancelledError, Exception):
            pass

    _active_turn_task = current_task
    async with _turn_lock:
        return await intentRouter(websocket, text, session, client)


def handle_voice_transcription(text: str) -> None:
    """Dispatches transcribed voice commands to the active session or app opener."""
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
                # Route through execute_turn_safely to prevent parallel collisions.
                data = await execute_turn_safely(ws, text, session, client)
                if data:
                    print(f"Received from dot: {data}")
            except Exception as err:
                print(f"[Voice Dispatch Error]: {err}")
                traceback.print_exc()

        asyncio.run_coroutine_threadsafe(dispatch(), main_loop)
    else:
        try:
            asyncio.run(routeAppOpener(text))
        except Exception as err:
            print(f"[Voice Fallback Error]: {err}")


def handle_voice_status(status: str) -> None:
    """Notifies the active WebSocket client of voice recognition state changes."""
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
    """Manages application lifecycle including voice thread and global MCP client."""
    # Store the main asyncio event loop for thread-safe operations.
    app_state["main_loop"] = asyncio.get_running_loop()

    # Start the background voice listener thread.
    print("Starting background voice listener...")
    threading.Thread(
        target=startVoiceListener,
        args=(handle_voice_transcription, handle_voice_status),
        daemon=True,
    ).start()

    # Start the MCP client session once for the entire application lifecycle.
    multi_server_client = get_multi_server_client()
    async with multi_server_client as active_client:
        print("MCP servers initialized and ready globally.")
        app_state["active_mcp_client"] = active_client

        # Synchronize tools in background without blocking port availability.
        async def sync_tools_background():
            print("Syncing tools to ChromaDB...")
            try:
                await sync_registry(active_client=active_client)
                print("All tools registered in ChromaDB successfully.")
            except Exception as reg_err:
                print(f"[Warning] Tool registration encountered an error: {reg_err}")
                traceback.print_exc()

        asyncio.create_task(sync_tools_background())

        # The application runs while this context yields.
        yield

    print("Shutting down MCP servers...")


# Initialize the FastAPI application with the lifespan context manager.
app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/settings")
async def get_settings():
    """Returns current active system and cloud settings."""
    cfg = load_config()
    gh_token = get_github_token()
    return {
        "active_settings": cfg.get("active_settings", {}),
        "cloud": cfg.get("cloud", {}),
        "models": cfg.get("models", {}),
        "backends": cfg.get("backends", {}),
        "github_token": gh_token,
    }


@app.post("/api/settings")
async def update_settings(request: Request):
    """Updates settings and reloads the inference clients."""
    payload = await request.json()
    cfg = load_config()
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
        update_github_token(gh_token)

    save_config(cfg)

    # Reload LLM clients dynamically.
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
                    "github_token": get_github_token(),
                }
            }))
        except Exception:
            pass

    return {
        "status": "ok",
        "active_settings": active,
        "cloud": cloud,
        "github_token": get_github_token(),
    }


@app.post("/api/browser/toggle")
async def toggle_browser_headless():
    """Toggles headless mode for browser automation."""
    current = is_browser_headless()
    new_state = not current
    set_browser_headless(new_state)

    ws = app_state.get("active_websocket")
    if ws:
        try:
            await ws.send_text(json.dumps({
                "type": "browser_status",
                "data": {"browser_headless": new_state}
            }))
        except Exception:
            pass

    return {"status": "ok", "browser_headless": new_state}


@app.get("/api/mcp/servers")
async def get_mcp_servers():
    """Returns the list of configured MCP servers."""
    cfg = load_server_config()
    servers = list(cfg.get("mcpServers", {}).keys())
    return {"servers": servers}


@app.post("/api/mcp/sync")
async def mcp_sync_registry():
    """Synchronizes tools from all configured MCP servers."""
    active_client = app_state.get("active_mcp_client")
    try:
        await sync_registry(active_client=active_client)
        services = get_all_services(force_refresh=True)
        return {"status": "ok", "services": services}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/sandbox/status")
async def get_sandbox_status():
    """Returns sandbox container and Docker status."""
    docker_ok = await is_docker_available()
    running = await is_sandbox_running() if docker_ok else False
    paused = await is_sandbox_paused() if running else False
    return {
        "docker_available": docker_ok,
        "running": running,
        "paused": paused,
    }


@app.post("/api/sandbox/start")
async def api_start_sandbox():
    """Starts the Docker sandbox container."""
    success = await start_sandbox()
    return {"status": "ok" if success else "error"}


@app.post("/api/sandbox/stop")
async def api_stop_sandbox():
    """Stops the Docker sandbox container."""
    success = await stop_sandbox()
    return {"status": "ok" if success else "error"}


@app.post("/api/sandbox/exec")
async def api_exec_sandbox(request: Request):
    """Executes a command inside the sandbox."""
    payload = await request.json()
    command = payload.get("command", "")
    code, output = await exec_in_sandbox(command)
    return {"exit_code": code, "output": output}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Handles bidirectional communication with the frontend client."""
    await websocket.accept()
    active_session = SessionStorage(session_id=str(uuid.uuid4()))
    print(f"WebSocket client connected. Session: {active_session.session_id}")

    app_state["active_websocket"] = websocket
    app_state["active_session"] = active_session
    active_client = app_state.get("active_mcp_client")

    # Broadcast initial context token baseline including the system prompt.
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
                "percentage": pct,
            }
        }))
    except Exception as e:
        print(f"[Initial Token Telemetry Warning]: {e}")

    # Broadcast initial browser headless status.
    try:
        headless = is_browser_headless()
        await websocket.send_text(json.dumps({
            "type": "browser_status",
            "data": {"browser_headless": headless}
        }))
    except Exception:
        pass

    try:
        while True:
            text = await websocket.receive_text()
            try:
                # Handle structured JSON control messages from UI
                parsed_msg = None
                if text.strip().startswith("{"):
                    try:
                        parsed_msg = json.loads(text)
                    except Exception:
                        parsed_msg = None

                if parsed_msg and isinstance(parsed_msg, dict) and "type" in parsed_msg:
                    msg_type = parsed_msg.get("type")
                    if msg_type == "intervention_approve":
                        feedback = parsed_msg.get("feedback")
                        get_intervention_manager().submit_resolution(feedback)
                        await websocket.send_text(json.dumps({"type": "intervention_resolved"}))
                        continue
                    elif msg_type == "intervention_cli_exec":
                        cli_cmd = parsed_msg.get("command", "")
                        code, out = await exec_in_sandbox(cli_cmd)
                        await websocket.send_text(json.dumps({
                            "type": "cli_output",
                            "data": {"command": cli_cmd, "exit_code": code, "output": out}
                        }))
                        continue
                    elif msg_type == "sandbox_status":
                        running = await is_sandbox_running()
                        docker_ok = await is_docker_available()
                        paused = await is_sandbox_paused() if running else False
                        await websocket.send_text(json.dumps({
                            "type": "sandbox_status",
                            "data": {"docker_available": docker_ok, "running": running, "paused": paused}
                        }))
                        continue

                # Execute turn through execute_turn_safely to prevent parallel collisions.
                data = await execute_turn_safely(websocket, text, active_session, active_client)
                if data:
                    print(f"Processed input: {text}")

                # Broadcast updated token telemetry after turn execution.
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
                            "percentage": pct,
                        }
                    }))
                except Exception:
                    pass

            except Exception as router_err:
                print(f"[INTERNAL ROUTER ERROR]: {router_err}")
                traceback.print_exc()
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

