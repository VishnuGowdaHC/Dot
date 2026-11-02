"""
Unified development environment runner for Dot.
Starts the local inference engine, Python backend, and Neutralino frontend.
"""

import os
import sys
import json
import time
import socket
import signal
import atexit
import shutil
import argparse
import subprocess
import threading
from typing import List, Optional

# Root directory paths.
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT_DIR, "appConfig.json")
BIN_DIR = os.path.join(ROOT_DIR, "bin")
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")

# ANSI color codes for multiplexed console output.
COLOR_ENGINE = "\033[36m"    # Cyan
COLOR_BACKEND = "\033[32m"   # Green
COLOR_FRONTEND = "\033[35m"  # Magenta
COLOR_SYSTEM = "\033[33m"    # Yellow
COLOR_RESET = "\033[0m"

# Track managed child processes for cleanup.
managed_processes: List[subprocess.Popen] = []
is_cleaning_up = False


def is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    """Verify if a network port accepts connections."""
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except (ConnectionRefusedError, socket.timeout, OSError):
        return False


def wait_for_port(port: int, timeout: float = 60.0, host: str = "127.0.0.1") -> bool:
    """Wait until the specified network port is ready."""
    start = time.time()
    while time.time() - start < timeout:
        if is_port_open(port, host):
            return True
        time.sleep(0.5)
    return False


def stop_process_tree(pid: int):
    """Terminate the process and all child processes."""
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except Exception:
        pass


def cleanup():
    """Stop all running child processes cleanly."""
    global is_cleaning_up
    if is_cleaning_up:
        return
    is_cleaning_up = True

    active_procs = [p for p in managed_processes if p and p.poll() is None]
    if not active_procs:
        return

    print(f"\n{COLOR_SYSTEM}[SYSTEM]{COLOR_RESET} Stopping all services...", flush=True)
    for proc in active_procs:
        stop_process_tree(proc.pid)
    print(f"{COLOR_SYSTEM}[SYSTEM]{COLOR_RESET} All services stopped.", flush=True)


atexit.register(cleanup)


def signal_handler(sig, frame):
    """Handle interrupt signals and trigger cleanup."""
    cleanup()
    sys.exit(0)


try:
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
except Exception:
    pass


def stream_output(proc: subprocess.Popen, prefix: str, color: str):
    """Stream process output line by line with a colored prefix."""
    try:
        for line in iter(proc.stdout.readline, ""):
            if not line:
                break
            text = line.rstrip()
            if text:
                print(f"{color}{prefix}{COLOR_RESET} {text}", flush=True)
    except Exception:
        pass


def find_python_exe() -> str:
    """Find the Python executable in the virtual environment."""
    venv_python = os.path.join(ROOT_DIR, ".venv", "Scripts", "python.exe")
    if os.path.exists(venv_python):
        return venv_python
    return sys.executable


def load_config() -> dict:
    """Load configuration from appConfig.json."""
    if not os.path.exists(CONFIG_PATH):
        print(f"{COLOR_SYSTEM}[SYSTEM]{COLOR_RESET} appConfig.json not found. Run setup.py first.")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def free_port_if_occupied(port: int):
    """Find and terminate any process that occupies the specified port."""
    if not is_port_open(port):
        return
    print(f"{COLOR_SYSTEM}[SYSTEM]{COLOR_RESET} Port {port} is occupied. Clearing port...", flush=True)
    try:
        cmd = f'powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue).OwningProcess"'
        res = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        pids = [p.strip() for p in res.stdout.split() if p.strip().isdigit()]
        for pid_str in pids:
            pid = int(pid_str)
            if pid > 0:
                stop_process_tree(pid)
        time.sleep(1.0)
    except Exception as err:
        print(f"{COLOR_SYSTEM}[SYSTEM]{COLOR_RESET} Warning: could not clear port {port}: {err}")


def build_engine_cmd(config: dict, tier_override: Optional[str], backend_override: Optional[str], port_override: Optional[int]) -> List[str]:
    """Assemble the command line arguments for llama-server."""
    active_settings = config.get("active_settings", {})
    backend = backend_override or active_settings.get("backend", "cuda")
    tier = tier_override or active_settings.get("selected_tier", "4B")
    port = port_override or active_settings.get("port", 11434)
    gpu_layers = active_settings.get("gpu_layers", 99)

    server_exe = os.path.join(BIN_DIR, "llama-server.exe")
    if not os.path.exists(server_exe):
        print(f"{COLOR_SYSTEM}[SYSTEM]{COLOR_RESET} llama-server.exe not found in bin directory.")
        sys.exit(1)

    model_info = config.get("models", {}).get(tier, {})
    model_fn = model_info.get("filename", "")
    mmproj_fn = model_info.get("mmproj", "")
    context_size = model_info.get("context_size", 8192)

    model_path = os.path.join(BIN_DIR, model_fn)
    if not os.path.exists(model_path):
        print(f"{COLOR_SYSTEM}[SYSTEM]{COLOR_RESET} Model file '{model_fn}' not found in bin directory.")
        sys.exit(1)

    gpu_args = ["-ngl", str(gpu_layers)] if backend == "cuda" else []
    return [
        server_exe,
        "-m", model_fn,
        "--mmproj", mmproj_fn,
        "--port", str(port),
        "-c", str(context_size),
        "-fa", "on",
        "-ctk", "q8_0",
        "-ctv", "q8_0",
        "-b", "512",
        "-ub", "256",
        "--temp", "0.0",
        "--alias", "dot-engine"
    ] + gpu_args


def main():
    """Parse options and run the development environment."""
    # Enable ANSI escape sequence processing in Windows console.
    os.system("")

    parser = argparse.ArgumentParser(description="Dot Development Environment Runner")
    parser.add_argument("--no-engine", action="store_true", help="Do not start the local inference engine")
    parser.add_argument("--no-ui", action="store_true", help="Do not start the Neutralino desktop UI")
    parser.add_argument("--backend-only", action="store_true", help="Run only the Python backend orchestrator")
    parser.add_argument("--frontend-only", action="store_true", help="Run only the Neutralino frontend")
    parser.add_argument("--no-reload", action="store_true", help="Disable Uvicorn auto-reload")
    parser.add_argument("--port", type=int, default=3000, help="Backend server port (default: 3000)")
    parser.add_argument("--engine-port", type=int, default=None, help="Inference engine port (default: from config)")
    parser.add_argument("--tier", type=str, default=None, help="Model tier override (2B, 4B, 12B)")
    parser.add_argument("--backend", type=str, default=None, help="Inference backend override (cuda, cpu, cloud)")
    args = parser.parse_args()

    config = load_config()

    print("=" * 60)
    print("  Dot Development Environment")
    print("=" * 60)

    should_start_engine = not (args.no_engine or args.backend_only or args.frontend_only)
    should_start_backend = not args.frontend_only
    should_start_frontend = not (args.no_ui or args.backend_only)

    active_settings = config.get("active_settings", {})
    backend_mode = args.backend or active_settings.get("backend", "cuda")
    if backend_mode == "cloud":
        should_start_engine = False

    engine_port = args.engine_port or active_settings.get("port", 11434)
    backend_port = args.port

    # 1. Start Inference Engine if required.
    if should_start_engine:
        if is_port_open(engine_port):
            print(f"{COLOR_ENGINE}[ENGINE]{COLOR_RESET} Port {engine_port} is already active. Reusing running engine.")
        else:
            engine_cmd = build_engine_cmd(config, args.tier, args.backend, engine_port)
            print(f"{COLOR_ENGINE}[ENGINE]{COLOR_RESET} Starting inference engine on port {engine_port}...")
            eng_proc = subprocess.Popen(
                engine_cmd,
                cwd=BIN_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace"
            )
            managed_processes.append(eng_proc)
            t_eng = threading.Thread(
                target=stream_output,
                args=(eng_proc, "[ENGINE]", COLOR_ENGINE),
                daemon=True
            )
            t_eng.start()

            print(f"{COLOR_ENGINE}[ENGINE]{COLOR_RESET} Waiting for engine to initialize...")
            if not wait_for_port(engine_port, timeout=60.0):
                print(f"{COLOR_SYSTEM}[SYSTEM]{COLOR_RESET} Error: Engine failed to start on port {engine_port}.")
                cleanup()
                sys.exit(1)
            print(f"{COLOR_ENGINE}[ENGINE]{COLOR_RESET} Engine is ready.")

    # 2. Start Python Backend Orchestrator.
    if should_start_backend:
        free_port_if_occupied(backend_port)
        py_exe = find_python_exe()
        backend_cmd = [py_exe, "-u", "-m", "uvicorn", "server:app", "--port", str(backend_port)]
        if not args.no_reload:
            backend_cmd.extend(["--reload", "--reload-exclude", "*storage*", "--reload-exclude", "*transcripts*"])

        print(f"{COLOR_BACKEND}[BACKEND]{COLOR_RESET} Starting backend server on port {backend_port}...")
        backend_env = os.environ.copy()
        backend_env["PYTHONIOENCODING"] = "utf-8"
        backend_env["PYTHONUTF8"] = "1"
        back_proc = subprocess.Popen(
            backend_cmd,
            cwd=BACKEND_DIR,
            env=backend_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace"
        )
        managed_processes.append(back_proc)
        t_back = threading.Thread(
            target=stream_output,
            args=(back_proc, "[BACKEND]", COLOR_BACKEND),
            daemon=True
        )
        t_back.start()

        if not wait_for_port(backend_port, timeout=90.0):
            print(f"{COLOR_SYSTEM}[SYSTEM]{COLOR_RESET} Error: Backend failed to start on port {backend_port}.")
            cleanup()
            sys.exit(1)
        print(f"{COLOR_BACKEND}[BACKEND]{COLOR_RESET} Backend is ready.")

    # 3. Start Frontend UI in full dev HMR mode.
    front_proc = None
    if should_start_frontend:
        npx_bin = shutil.which("npx.cmd") or shutil.which("npx") or "npx"
        frontend_cmd = [npx_bin, "@neutralinojs/neu", "run"]

        print(f"{COLOR_FRONTEND}[FRONTEND]{COLOR_RESET} Starting Neutralino with Vite HMR...")
        front_proc = subprocess.Popen(
            frontend_cmd,
            cwd=FRONTEND_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace"
        )
        managed_processes.append(front_proc)
        t_front = threading.Thread(
            target=stream_output,
            args=(front_proc, "[FRONTEND]", COLOR_FRONTEND),
            daemon=True
        )
        t_front.start()

    print(f"{COLOR_SYSTEM}[SYSTEM]{COLOR_RESET} All services initialized. Press Ctrl+C to stop.")

    # Keep process active until frontend terminates or user presses Ctrl+C.
    try:
        if front_proc is not None:
            front_proc.wait()
        else:
            while True:
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
