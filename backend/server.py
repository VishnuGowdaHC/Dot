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

import time
import json
import uuid
import socket
import subprocess
import asyncio
import logging
import warnings
import traceback
import threading
from pathlib import Path
from collections import deque
from typing import Optional, Any, Dict
from contextlib import asynccontextmanager

# Suppress harmless upstream PyTorch and HuggingFace Hub startup warnings.
warnings.filterwarnings("ignore", category=UserWarning, module="torch.ao.nn.quantized")
warnings.filterwarnings("ignore", message=".*unauthenticated requests to the HF Hub.*")
warnings.filterwarnings("ignore", message=".*quantized tensor creation functions.*")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
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
    get_cloud_api_key,
    update_cloud_api_key,
    is_browser_headless,
    set_browser_headless,
    get_allowed_workspace,
    set_allowed_workspace,
)
from dot.voice.listener import startVoiceListener
from dot.core.router import intentRouter
from dot.core.prompts import get_system_prompt
from dot.core.llm import reload_llm_clients
from dot.core.engine import resolve_clarification
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
_dispatch_lock = asyncio.Lock()
_active_turn_task: Optional[asyncio.Task] = None


async def execute_turn_safely(websocket, text: str, session, client):
    """Executes a user turn and cancels any active previous turn to prevent collisions."""
    global _active_turn_task
    current_task = asyncio.current_task()

    async with _dispatch_lock:
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
    main_loop = asyncio.get_running_loop()
    app_state["main_loop"] = main_loop

    if sys.platform == "win32" and isinstance(main_loop, asyncio.SelectorEventLoop):
        print("[Warning] SelectorEventLoop detected on Windows. Start uvicorn with '--loop asyncio:ProactorEventLoop' for Playwright subprocess support.")

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

    print("Stopping Docker sandbox if running...")
    try:
        await stop_sandbox()
    except Exception as sb_err:
        print(f"[Warning] Sandbox teardown failed: {sb_err}")
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
    cloud_cfg = dict(cfg.get("cloud", {}))
    if not cloud_cfg.get("api_key"):
        cloud_cfg["api_key"] = get_cloud_api_key()
    return {
        "active_settings": cfg.get("active_settings", {}),
        "cloud": cloud_cfg,
        "models": cfg.get("models", {}),
        "backends": cfg.get("backends", {}),
        "github_token": gh_token,
        "allowed_workspace": get_allowed_workspace(),
        "allowed_processes": cfg.get("allowed_processes", []),
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
    if "browser_profile_mode" in payload and payload["browser_profile_mode"]:
        active["browser_profile_mode"] = str(payload["browser_profile_mode"]).strip()
    if "browser_profile_name" in payload and payload["browser_profile_name"]:
        active["browser_profile_name"] = str(payload["browser_profile_name"]).strip()
    if "allowed_processes" in payload and isinstance(payload["allowed_processes"], list):
        cfg["allowed_processes"] = sorted({
            str(p).strip().lower() for p in payload["allowed_processes"] if str(p).strip()
        })
    if "cloud" in payload and isinstance(payload["cloud"], dict):
        for k, v in payload["cloud"].items():
            cloud[k] = v
    if "cloud_provider" in payload and payload["cloud_provider"]:
        cloud["provider"] = str(payload["cloud_provider"]).strip()
    if "cloud_base_url" in payload and payload["cloud_base_url"]:
        cloud["base_url"] = str(payload["cloud_base_url"]).strip()
    if "cloud_model" in payload and payload["cloud_model"]:
        cloud["model"] = str(payload["cloud_model"]).strip()
    if "cloud_api_key" in payload and payload["cloud_api_key"]:
        cloud["api_key"] = str(payload["cloud_api_key"]).strip()
        update_cloud_api_key(str(payload["cloud_api_key"]).strip())
    elif "cloud" in payload and isinstance(payload["cloud"], dict) and payload["cloud"].get("api_key"):
        update_cloud_api_key(str(payload["cloud"]["api_key"]).strip())
    if "github_token" in payload:
        gh_token = str(payload["github_token"]).strip()
        update_github_token(gh_token)
    if "allowed_workspace" in payload:
        set_allowed_workspace(str(payload["allowed_workspace"]).strip())

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
                    "allowed_workspace": get_allowed_workspace(),
                }
            }))
        except Exception:
            pass

    return {
        "status": "ok",
        "active_settings": active,
        "cloud": cloud,
        "github_token": get_github_token(),
        "allowed_workspace": get_allowed_workspace(),
    }


def check_engine_port_open(port: int = 11434, host: str = "127.0.0.1") -> bool:
    """Checks if the local engine port is accepting connections."""
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except (ConnectionRefusedError, socket.timeout, OSError):
        return False


def get_engine_command_str(cfg: dict, tier: str = "4B", port: int = 11434) -> str:
    """Assembles the display command string for llama-server."""
    model_info = cfg.get("models", {}).get(tier, {})
    model_fn = model_info.get("filename", "gemma-4-E4B_q4_0-it.gguf")
    mmproj_fn = model_info.get("mmproj", "gemma-4-E4B-it-mmproj.gguf")
    context_size = model_info.get("context_size", 8192)
    return (
        f"bin\\llama-server.exe -m {model_fn} --mmproj {mmproj_fn} --port {port} "
        f"-c {context_size} -np 1 -fa on -ctk q8_0 -ctv q8_0 -ngl 99 --temp 0.0 --alias dot-engine"
    )


def _read_tail_lines(log_path: Path, max_lines: int = 35) -> list[str]:
    """Reads the last max_lines non-empty or raw lines from a log file."""
    if not log_path.exists():
        return []
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        return [line.rstrip() for line in deque(f, maxlen=max_lines)]


def extract_engine_diagnostics(log_path: Path) -> str:
    """Extracts diagnostic error summary from the engine log file.
    Complies with ASD-STE100 rules.
    """
    if not log_path.exists():
        return "No log file found."
    try:
        lines = [line.strip() for line in _read_tail_lines(log_path, max_lines=50) if line.strip()]
        if not lines:
            return "Engine log is empty."
        for line in reversed(lines[-25:]):
            lower = line.lower()
            if "out of memory" in lower or "cuda error" in lower:
                return "GPU out of memory. Reduce context size or GPU layers."
            if "failed to load model" in lower or "cannot open" in lower:
                return "Failed to load model file. Verify the model file exists."
            if "address already in use" in lower or "wsaeaddrinuse" in lower:
                return "Port is already in use by another application."
            if "cuda" in lower and "error" in lower:
                return f"CUDA driver error: {line[:80]}"
        return lines[-1][:120]
    except Exception as e:
        return f"Failed to read engine diagnostics: {e}"


@app.get("/api/engine/status")
async def get_engine_status():
    """Returns granular runtime status, model metadata, and health telemetry.
    Complies with ASD-STE100 rules.
    """
    import httpx
    cfg = load_config()
    active = cfg.get("active_settings", {})
    tier = active.get("selected_tier", "4B")
    port = int(active.get("port", 11434))
    model_info = cfg.get("models", {}).get(tier, {})
    model_fn = model_info.get("filename", "")
    context_size = model_info.get("context_size", 8192)

    proc = app_state.get("engine_process")
    port_open = await asyncio.to_thread(check_engine_port_open, port)

    state = "stopped"
    is_healthy = False
    detail = "Engine is stopped."
    error_msg = None
    last_log = ""

    engine_log = Path(__file__).resolve().parent.parent / "logs" / "engine.log"
    if engine_log.exists():
        try:
            tail = await asyncio.to_thread(_read_tail_lines, engine_log, 10)
            non_empty = [line.strip() for line in tail if line.strip()]
            if non_empty:
                last_log = non_empty[-1]
        except Exception:
            pass

    if port_open:
        try:
            async with httpx.AsyncClient(timeout=0.4) as client:
                res = await client.get(f"http://127.0.0.1:{port}/health")
                if res.status_code == 200:
                    state = "ready"
                    is_healthy = True
                    detail = f"Model loaded and ready for inference on port {port}."
                elif res.status_code == 503:
                    state = "loading"
                    detail = "Loading model weights into memory..."
                else:
                    state = "starting"
                    detail = f"Server starting on port {port} (HTTP {res.status_code})."
        except Exception:
            state = "starting"
            detail = f"Port {port} open. Initializing HTTP endpoints..."
    elif proc is not None:
        if proc.poll() is None:
            if last_log and any(k in last_log.lower() for k in ("loading", "load_model", "gguf", "weights")):
                state = "loading"
                detail = "Loading model weights into GPU memory..."
            else:
                state = "starting"
                detail = f"Starting engine process (PID {proc.pid})..."
        else:
            state = "error"
            exit_code = proc.returncode
            error_reason = extract_engine_diagnostics(engine_log)
            error_msg = f"Exit code {exit_code}: {error_reason}"
            detail = f"Engine process crashed. {error_reason}"
    else:
        state = "stopped"
        detail = "Local inference engine is stopped."

    return {
        "state": state,
        "running": port_open or (proc is not None and proc.poll() is None),
        "healthy": is_healthy,
        "port": port,
        "tier": tier,
        "model": model_fn,
        "context_size": context_size,
        "detail": detail,
        "last_log": last_log[:150] if last_log else "",
        "error": error_msg,
        "command": get_engine_command_str(cfg, tier, port),
        "pid": proc.pid if (proc is not None and proc.poll() is None) else None,
    }


@app.get("/api/engine/logs")
async def get_engine_logs(lines: int = 35):
    """Returns the most recent log lines from the engine log file.
    Complies with ASD-STE100 rules.
    """
    engine_log = Path(__file__).resolve().parent.parent / "logs" / "engine.log"
    if not engine_log.exists():
        return {"lines": []}
    try:
        recent = await asyncio.to_thread(_read_tail_lines, engine_log, lines)
        return {"lines": recent}
    except Exception as e:
        return {"lines": [f"Failed to read engine log: {e}"]}


@app.post("/api/engine/start")
async def start_engine_endpoint(request: Request = None):
    """Starts the local llama-server in the background if not already running.
    Complies with ASD-STE100 rules.
    """
    cfg = load_config()
    active = cfg.get("active_settings", {})
    tier = active.get("selected_tier", "4B")

    # Allow overriding tier from request body
    if request:
        try:
            body = await request.json()
            if body and body.get("tier"):
                tier = str(body["tier"]).strip()
        except Exception:
            pass

    port = int(active.get("port", 11434))

    if await asyncio.to_thread(check_engine_port_open, port):
        return {"status": "ok", "message": f"Engine is already running on port {port}."}

    bin_dir = Path(__file__).resolve().parent.parent / "bin"
    server_exe = bin_dir / "llama-server.exe"
    if not server_exe.exists():
        return {"status": "error", "message": "llama-server.exe was not found in the bin directory."}

    model_info = cfg.get("models", {}).get(tier, {})
    model_fn = model_info.get("filename", "")
    if not model_fn:
        return {"status": "error", "message": f"No model file configured for tier '{tier}'."}

    model_path = bin_dir / model_fn
    if not model_path.exists():
        return {
            "status": "error",
            "message": f"Model file '{model_fn}' was not found in the bin directory. Verify the file exists."
        }

    mmproj_fn = model_info.get("mmproj", "")
    mmproj_path = bin_dir / mmproj_fn if mmproj_fn else None
    context_size = model_info.get("context_size", 8192)

    cmd = [
        str(server_exe),
        "-m", str(model_path),
        "--port", str(port),
        "-c", str(context_size),
        "-np", "1",
        "-fa", "on",
        "-ctk", "q8_0",
        "-ctv", "q8_0",
        "-ngl", "99",
        "-b", "2048",
        "-ub", "512",
        "--temp", "0.0",
        "--alias", "dot-engine",
    ]

    if mmproj_path and mmproj_path.exists():
        cmd.extend(["--mmproj", str(mmproj_path)])

    log_file = None
    try:
        prev_log = app_state.get("engine_log_file")
        if prev_log:
            try:
                prev_log.close()
            except Exception:
                pass
            app_state["engine_log_file"] = None

        logs_dir = Path(__file__).resolve().parent.parent / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        engine_log = logs_dir / "engine.log"

        log_file = open(engine_log, "a", encoding="utf-8", errors="replace")
        log_file.write(f"\n--- Engine Started at {time.strftime('%Y-%m-%d %H:%M:%S')} (Tier: {tier}, Port: {port}) ---\n")
        log_file.write(f"Command: {' '.join(cmd)}\n")
        log_file.flush()

        engine_env = os.environ.copy()
        engine_env["GGML_CUDA_DISABLE_GRAPHS"] = "1"

        proc = subprocess.Popen(
            cmd,
            cwd=str(bin_dir),
            env=engine_env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        )
        app_state["engine_process"] = proc
        app_state["engine_log_file"] = log_file
        app_state["engine_start_time"] = time.time()
        return {"status": "starting", "message": f"Starting engine on port {port} with {model_fn}..."}
    except Exception as e:
        if log_file:
            try:
                log_file.close()
            except Exception:
                pass
        return {"status": "error", "message": str(e)}


@app.post("/api/engine/stop")
async def stop_engine_endpoint():
    """Terminates the local engine process and cleans up file handles.
    Complies with ASD-STE100 rules.
    """
    proc = app_state.get("engine_process")
    log_file = app_state.get("engine_log_file")
    if log_file:
        try:
            log_file.close()
        except Exception:
            pass
        app_state["engine_log_file"] = None

    stopped = False
    if proc and proc.poll() is None:
        try:
            await asyncio.to_thread(
                subprocess.run,
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            stopped = True
        except Exception:
            pass
        app_state["engine_process"] = None

    cfg = load_config()
    port = int(cfg.get("active_settings", {}).get("port", 11434))
    if await asyncio.to_thread(check_engine_port_open, port):
        try:
            ps_cmd = [
                "powershell", "-NoProfile", "-Command",
                f"(Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue).OwningProcess",
            ]
            res = await asyncio.to_thread(subprocess.run, ps_cmd, capture_output=True, text=True)
            for line in res.stdout.strip().splitlines():
                pid = line.strip()
                if pid and pid.isdigit() and int(pid) > 0:
                    await asyncio.to_thread(
                        subprocess.run,
                        ["taskkill", "/F", "/T", "/PID", pid],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                    stopped = True
        except Exception:
            pass

    msg = "Engine process stopped." if stopped else "No active managed engine process."
    return {"status": "ok", "message": msg}


@app.get("/api/update/check")
async def check_update_endpoint():
    """Checks GitHub Releases for a newer Dot version."""
    from dot.core.updater import check_for_updates
    return await check_for_updates()


@app.get("/api/update/status")
async def get_update_status_endpoint():
    """Returns live download and installation progress for the active update."""
    from dot.core.updater import get_update_progress
    return get_update_progress()


@app.post("/api/update/install")
async def install_update_endpoint(request: Request):
    """Starts update download, verification, and installation in the background."""
    from dot.core.updater import download_and_install_update, get_update_progress
    payload = await request.json()
    download_url = str(payload.get("download_url", "")).strip()
    sha256_url = payload.get("sha256_url")
    expected_size = int(payload.get("asset_size") or 0)

    current = get_update_progress()
    if current.get("stage") in ("downloading", "verifying", "launching"):
        return {"status": "started", "progress": current}

    async def _broadcast_progress(snap: dict) -> None:
        ws = app_state.get("active_websocket")
        if ws:
            try:
                await ws.send_text(json.dumps({"type": "update_progress", "data": snap}))
            except Exception:
                pass

    async def _run_update() -> None:
        result = await download_and_install_update(
            download_url,
            sha256_url,
            expected_size=expected_size,
            on_progress=_broadcast_progress,
        )
        if result.get("status") == "installing":
            try:
                await stop_engine()
            except Exception:
                pass
            await asyncio.sleep(1.5)
            os._exit(0)

    asyncio.create_task(_run_update())
    return {"status": "started"}


@app.post("/api/logs/open")
async def open_logs_folder_endpoint():
    """Opens the Dot logs directory in Windows Explorer."""
    from dot.config.paths import LOGS_DIR
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        await asyncio.to_thread(os.startfile, str(LOGS_DIR))
    return {"status": "ok", "path": str(LOGS_DIR)}


@app.post("/api/cloud/test")
async def test_cloud_connection(request: Request):
    """Validates the cloud API credentials and returns connection status."""
    import time
    from openai import AsyncOpenAI
    payload = await request.json()
    provider = str(payload.get("provider", "openai")).lower()
    base_url = str(payload.get("base_url", "")).strip()
    api_key = str(payload.get("api_key", "")).strip()
    model = str(payload.get("model", "")).strip()

    if not api_key:
        return {"success": False, "error": "API key is required."}

    if provider == "gemini" and not base_url:
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
    elif not base_url:
        base_url = "https://api.openai.com/v1"

    if not model:
        model = "gemini-2.5-flash" if provider == "gemini" else "gpt-4o-mini"

    start_time = time.time()
    test_client = None
    try:
        test_client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=10.0)
        resp = await test_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
        latency_ms = int((time.time() - start_time) * 1000)
        reply = resp.choices[0].message.content or ""
        return {
            "success": True,
            "provider": provider,
            "model": model,
            "latency_ms": latency_ms,
            "reply": reply.strip(),
        }
    except Exception as err:
        err_msg = str(err)
        if "401" in err_msg or "invalid_api_key" in err_msg or "API_KEY_INVALID" in err_msg:
            clean_err = "Invalid API key. Verify your credentials."
        elif "quota" in err_msg.lower() or "429" in err_msg:
            clean_err = "API rate limit or quota exceeded."
        elif "connection" in err_msg.lower():
            clean_err = "Network connection failed. Verify Base URL."
        else:
            clean_err = f"Connection failed: {err_msg[:80]}"
        return {"success": False, "error": clean_err}
    finally:
        if test_client is not None:
            try:
                await test_client.close()
            except Exception:
                pass


@app.post("/api/chat/clear")
async def clear_chat_session():
    """Resets the active conversation session and rolling memory."""
    active_session = app_state.get("active_session")
    if active_session:
        active_session.history = []
        active_session.executed_signatures = set()

    try:
        from dot.memory.rolling_memory import get_rolling_memory
        rolling_mem = get_rolling_memory()
        rolling_mem.clear()
    except Exception:
        pass

    ws = app_state.get("active_websocket")
    if ws:
        try:
            await ws.send_text(json.dumps({"type": "chat_cleared"}))
        except Exception:
            pass

    return {"status": "ok", "message": "Conversation history cleared."}


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


@app.get("/api/browser/profiles")
async def get_browser_profiles():
    """Lists available local Chrome profiles via agent-browser."""
    from dot.config.paths import MCP_BIN_DIR
    import subprocess
    import re

    exe_path = MCP_BIN_DIR / "agent-browser.exe"
    if not exe_path.exists():
        return {"profiles": []}

    def _list_profiles() -> list[dict]:
        try:
            proc = subprocess.run(
                [str(exe_path), "profiles"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            items = []
            for line in (proc.stdout or "").splitlines():
                m = re.match(r"^\s{2,}(.+?)\s{2,}\((.+?)\)\s*$", line)
                if m:
                    items.append({"id": m.group(1).strip(), "label": m.group(2).strip()})
            return items
        except Exception:
            return []

    profiles = await asyncio.to_thread(_list_profiles)
    return {"profiles": profiles}


@app.post("/api/browser/open-login")
async def open_browser_for_login():
    """Launches clean Chrome with the persistent Dot profile on CDP port 9222 for sign-in."""
    from dot.config.paths import ROOT_DIR
    from dot.automation.browser import ensure_clean_chrome_cdp

    profile_dir = ROOT_DIR / "data" / "browser_profile"
    ok = await asyncio.to_thread(ensure_clean_chrome_cdp, 9222, profile_dir)
    if not ok:
        return JSONResponse(status_code=500, content={"status": "error", "message": "Google Chrome executable not found or port 9222 failed to open."})
    return {"status": "ok", "cdp_port": 9222}


@app.post("/api/browser/verify")
async def verify_browser_path():
    """Verifies browser executable availability and opens a test page."""
    from dot.config.paths import MCP_BIN_DIR
    from dot.automation.browser import find_chrome_executable, navigate
    from dot.mcp.client import execute_mcp_tool

    agent_exe = MCP_BIN_DIR / "agent-browser.exe"
    chrome_exe = find_chrome_executable()
    mcp_client = app_state.get("mcp_client")

    try:
        if mcp_client is not None:
            res = await execute_mcp_tool(mcp_client, "browser", "browser_navigate", {"url": "https://example.com"})
        else:
            res = await navigate("https://example.com")
        ok = not (isinstance(res, dict) and res.get("success") is False)
        return {
            "status": "ok" if ok else "error",
            "agent_browser_found": agent_exe.exists(),
            "agent_browser_path": str(agent_exe),
            "chrome_found": bool(chrome_exe),
            "chrome_path": chrome_exe or "",
            "detail": (res.get("error") or res.get("detail") or "Browser opened https://example.com.") if isinstance(res, dict) else str(res),
        }
    except Exception as err:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "agent_browser_found": agent_exe.exists(),
                "chrome_found": bool(chrome_exe),
                "detail": str(err),
            },
        )


@app.get("/api/apps/installed")
async def get_installed_apps():
    """Returns installed Windows applications and allowed process whitelist."""
    from dot.automation.app_opener import list_installed_apps
    apps = await asyncio.to_thread(list_installed_apps)
    cfg = load_config()
    allowed = [str(p).strip().lower() for p in cfg.get("allowed_processes", []) if str(p).strip()]
    return {"installed": apps, "allowed": allowed}


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

    # Broadcast initial settings and active model information.
    try:
        cfg = load_config()
        active = cfg.get("active_settings", {})
        cloud = cfg.get("cloud", {})
        await websocket.send_text(json.dumps({
            "type": "settings_updated",
            "data": {
                "active_settings": active,
                "cloud": cloud,
                "github_token": get_github_token(),
                "allowed_workspace": get_allowed_workspace(),
            }
        }))
    except Exception as e:
        print(f"[Initial Settings Broadcast Warning]: {e}")

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
                    elif msg_type == "clarification_response":
                        clarify_id = parsed_msg.get("id") or parsed_msg.get("clarification_id")
                        answer = parsed_msg.get("answer", "")
                        resolved = resolve_clarification(str(clarify_id), str(answer))
                        await websocket.send_text(json.dumps({
                            "type": "clarification_resolved",
                            "data": {"id": clarify_id, "resolved": resolved}
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
                try:
                    await websocket.send_text(json.dumps({"type": "error", "data": "Agent loop crashed. Check terminal."}))
                except Exception:
                    pass

    except WebSocketDisconnect:
        print("WebSocket disconnected normally by client.")
    except Exception as e:
        print(f"[WEBSOCKET CRASH]: {e}")
        traceback.print_exc()
    finally:
        if app_state.get("active_websocket") == websocket:
            app_state["active_websocket"] = None
            app_state["active_session"] = None
        try:
            print(f"[Server] Embedding session {active_session.session_id} to ChromaDB...")
            await asyncio.to_thread(embed_session_to_chroma, active_session.session_id, active_session.filepath)
            print("[Server] Session embedded successfully.")
        except Exception as embed_err:
            print(f"[Server Warning] Failed to embed session {active_session.session_id}: {embed_err}")

