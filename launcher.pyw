import os
import sys
import json
import time
import socket
import atexit
import signal
import subprocess
import ctypes
import tkinter as tk
from tkinter import messagebox

# Determine app root
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

CONFIG_PATH = os.path.join(BASE_DIR, "appConfig.json")
ENGINE_LOG = os.path.join(LOGS_DIR, "engine.log")
BACKEND_LOG = os.path.join(LOGS_DIR, "backend.log")

running_processes = []


def cleanup():
    """Cleanly terminate all spawned server processes on exit."""
    for p in running_processes:
        try:
            if p and p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=2)
                except Exception:
                    p.kill()
        except Exception:
            pass


atexit.register(cleanup)
try:
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
except Exception:
    pass


def acquire_single_instance_lock(name="Dot_SingleInstance_Mutex"):
    """Acquires a named mutex to ensure only one instance runs."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    mutex = kernel32.CreateMutexW(None, False, name)
    last_error = kernel32.GetLastError()
    if last_error == 183:  # ERROR_ALREADY_EXISTS
        return None
    return mutex


def find_python_exe():
    """Finds the bundled Python runtime or local virtual environment."""
    candidates = [
        os.path.join(BASE_DIR, "runtime", "python.exe"),
        os.path.join(BASE_DIR, "runtime", "pythonw.exe"),
        os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe"),
        os.path.join(BASE_DIR, ".venv", "Scripts", "pythonw.exe"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return sys.executable


def wait_for_port(port, timeout=60):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except (ConnectionRefusedError, socket.timeout, OSError):
            time.sleep(1)
    return False


def show_error(title, message):
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(title, message)
    root.destroy()


def main():
    mutex = acquire_single_instance_lock()
    if not mutex:
        show_error("Dot - Already Running", "Dot is already running on this system.")
        return

    if not os.path.exists(CONFIG_PATH):
        py_exe = find_python_exe()
        subprocess.run([py_exe, os.path.join(BASE_DIR, "setup.py")], cwd=BASE_DIR)
        if not os.path.exists(CONFIG_PATH):
            return

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    active_settings = config.get("active_settings", {})
    backend = active_settings.get("backend", "cuda")
    tier = active_settings.get("selected_tier", "4B")
    port = active_settings.get("port", 11434)
    gpu_layers = active_settings.get("gpu_layers", 99)

    no_window_flag = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    # 1. Start Inference Engine (if local backend)
    if backend != "cloud":
        bin_dir = os.path.join(BASE_DIR, "bin")
        server_exe = os.path.join(bin_dir, "llama-server.exe")

        if not os.path.exists(server_exe):
            show_error(
                "Dot - Missing Engine",
                f"Inference engine binary not found in:\n{server_exe}\n\nPlease run setup.py first."
            )
            return

        model_info = config.get("models", {}).get(tier, {})
        model_fn = model_info.get("filename", "")
        mmproj_fn = model_info.get("mmproj", "")
        context_size = model_info.get("context_size", 8192)

        model_path = os.path.join(bin_dir, model_fn)
        if not os.path.exists(model_path):
            show_error(
                "Dot - Missing Model",
                f"Model file '{model_fn}' was not found in bin/.\n\nPlease run setup.py to download or import it."
            )
            return

        gpu_args = ["-ngl", str(gpu_layers)] if backend == "cuda" else []
        engine_cmd = [
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

        with open(ENGINE_LOG, "w", encoding="utf-8") as eng_log_file:
            eng_proc = subprocess.Popen(
                engine_cmd,
                cwd=bin_dir,
                stdout=eng_log_file,
                stderr=subprocess.STDOUT,
                creationflags=no_window_flag
            )
            running_processes.append(eng_proc)

        # Wait for inference engine to become ready
        if not wait_for_port(port, timeout=60):
            show_error(
                "Dot - Inference Engine Error",
                f"Local engine failed to initialize within 60 seconds on port {port}.\n\nCheck logs at:\n{ENGINE_LOG}"
            )
            cleanup()
            return

    # 2. Start Python Orchestrator Backend
    py_exe = find_python_exe()
    backend_dir = os.path.join(BASE_DIR, "backend")
    frontend_dir = os.path.join(BASE_DIR, "frontend")
    backend_cmd = [py_exe, "-m", "uvicorn", "server:app", "--port", "3000"]

    with open(BACKEND_LOG, "w", encoding="utf-8") as back_log_file:
        back_proc = subprocess.Popen(
            backend_cmd,
            cwd=backend_dir,
            stdout=back_log_file,
            stderr=subprocess.STDOUT,
            creationflags=no_window_flag
        )
        running_processes.append(back_proc)

    # Wait for orchestrator on port 3000
    if not wait_for_port(3000, timeout=60):
        show_error(
            "Dot - Orchestrator Error",
            f"Dot backend server failed to start on port 3000 within 60 seconds.\n\nCheck logs at:\n{BACKEND_LOG}"
        )
        cleanup()
        return

    # 3. Launch Frontend UI (Native Neutralino desktop app)
    neu_candidates = [
        os.path.join(frontend_dir, "Dot-win_x64.exe"),
        os.path.join(frontend_dir, "bin", "Dot-win_x64.exe"),
        os.path.join(frontend_dir, "out", "Dot", "Dot-win_x64.exe"),
        os.path.join(frontend_dir, "bin", "neutralino-win_x64.exe"),
    ]

    frontend_cmd = None
    frontend_cwd = frontend_dir
    for cand in neu_candidates:
        if os.path.exists(cand):
            frontend_cmd = [cand]
            frontend_cwd = os.path.dirname(cand)
            # Ensure resources.neu exists in the executable's directory
            res_path = os.path.join(frontend_cwd, "resources.neu")
            if not os.path.exists(res_path):
                alt_res = os.path.join(frontend_dir, "out", "Dot", "resources.neu")
                if os.path.exists(alt_res):
                    import shutil
                    try:
                        shutil.copy2(alt_res, res_path)
                    except Exception:
                        pass
            break

    if not frontend_cmd:
        frontend_cmd = ["cmd", "/c", "npx", "@neutralinojs/neu", "run"]
        frontend_cwd = frontend_dir

    front_proc = subprocess.Popen(
        frontend_cmd,
        cwd=frontend_cwd,
        creationflags=no_window_flag
    )
    running_processes.append(front_proc)

    # Wait until frontend window is closed by user, then exit and cleanup
    try:
        front_proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
