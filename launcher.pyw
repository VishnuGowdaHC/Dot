"""
Dot Application Launcher and Service Diagnostics Supervisor.
Manages the lifecycle of local inference, backend, and desktop UI.
Complies with ASD-STE100 technical writing standards.
"""

import os
import sys
import json
import time
import socket
import atexit
import signal
import subprocess
import shutil
import ctypes
import threading
import tkinter as tk
from tkinter import messagebox

# Determine application root directory
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
open_log_writers = []
is_cleaning_up = False


def kill_process_tree(pid):
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


def kill_orphaned_servers():
    """Kill lingering background server processes holding ports 3000 or 11434."""
    try:
        no_win = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        res = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            creationflags=no_win,
        )
        for line in res.stdout.splitlines():
            line_str = line.strip()
            if (":3000" in line_str or ":11434" in line_str) and "LISTENING" in line_str:
                parts = line_str.split()
                pid = parts[-1]
                if pid.isdigit() and int(pid) != os.getpid():
                    kill_process_tree(int(pid))
    except Exception:
        pass


def cleanup():
    """Cleanly terminate all spawned server processes on exit."""
    global is_cleaning_up
    if is_cleaning_up:
        return
    is_cleaning_up = True

    for p in running_processes:
        try:
            if p and p.poll() is None:
                kill_process_tree(p.pid)
        except Exception:
            pass

    for w in open_log_writers:
        try:
            w.flush()
            w.close()
        except Exception:
            pass


atexit.register(cleanup)
try:
    signal.signal(signal.SIGINT, lambda s, f: (cleanup(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda s, f: (cleanup(), sys.exit(0)))
except Exception:
    pass


def acquire_single_instance_lock(name="Dot_SingleInstance_Mutex"):
    """Acquire a named mutex to ensure only one instance runs."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    mutex = kernel32.CreateMutexW(None, False, name)
    last_error = kernel32.GetLastError()
    if last_error == 183:  # ERROR_ALREADY_EXISTS
        return None
    return mutex


def focus_existing_window():
    """Bring the active Dot window to the foreground."""
    try:
        user32 = ctypes.WinDLL("user32")
        hwnd = user32.FindWindowW(None, "Dot")
        if hwnd:
            SW_RESTORE = 9
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            return True
    except Exception:
        pass
    return False


def find_python_exe():
    """Find the bundled Python runtime or local virtual environment."""
    candidates = [
        os.path.join(BASE_DIR, "runtime", "python.exe"),
        os.path.join(BASE_DIR, "runtime", "pythonw.exe"),
        os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe"),
        os.path.join(BASE_DIR, ".venv", "Scripts", "pythonw.exe"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c

    for cmd in ["python.exe", "python", "py.exe"]:
        p = shutil.which(cmd)
        if p and not p.lower().endswith("dot.exe"):
            return p

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    system_candidates = [
        os.path.join(local_app_data, "Programs", "Python", "Python312", "python.exe"),
        os.path.join(local_app_data, "Programs", "Python", "Python311", "python.exe"),
        "C:\\Python312\\python.exe",
        "C:\\Python311\\python.exe",
    ]
    for sc in system_candidates:
        if os.path.exists(sc):
            return sc

    if not getattr(sys, "frozen", False) and not sys.executable.lower().endswith("dot.exe"):
        return sys.executable

    return None


def is_port_open(port, host="127.0.0.1"):
    """Check if a network port accepts connections."""
    for test_host in [host, "localhost", "::1"]:
        try:
            with socket.create_connection((test_host, port), timeout=1.0):
                return True
        except (ConnectionRefusedError, socket.timeout, OSError):
            pass
    return False


def check_essentials(config):
    """Verify that all required files and configurations exist."""
    active_settings = config.get("active_settings", {})
    backend = active_settings.get("backend", "cuda")

    if backend == "cloud":
        cloud_cfg = config.get("cloud", {})
        api_key = cloud_cfg.get("api_key", "").strip()
        has_env_key = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("GEMINI_API_KEY"))
        return bool(api_key or has_env_key)

    bin_dir = os.path.join(BASE_DIR, "bin")
    server_exe = os.path.join(bin_dir, "llama-server.exe")
    if not os.path.exists(server_exe):
        return False

    tier = active_settings.get("selected_tier", "4B")
    model_info = config.get("models", {}).get(tier, {})
    model_fn = model_info.get("filename", "")
    if not model_fn:
        return False

    model_path = os.path.join(bin_dir, model_fn)
    if not os.path.exists(model_path):
        return False

    return True


def enable_dark_title_bar(window):
    """Enable Windows 10/11 native dark mode on Tkinter title bar."""
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(2)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
    except Exception:
        pass


def read_last_log_lines(file_path, num_lines=35):
    """Read the last N lines from a log file safely."""
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            return [line.rstrip() for line in lines[-num_lines:] if line.strip()]
    except Exception:
        try:
            with open(file_path, "rb") as f:
                content = f.read().decode("utf-8", errors="replace")
                lines = content.splitlines()
                return [line.rstrip() for line in lines[-num_lines:] if line.strip()]
        except Exception:
            return []


def parse_error_diagnostics(log_path, service_name, port, config):
    """Parse log file to identify the failure cause and provide recovery commands."""
    lines = read_last_log_lines(log_path, 40)
    full_text = "\n".join(lines).lower()

    active_settings = config.get("active_settings", {})
    tier = active_settings.get("selected_tier", "4B")
    backend = active_settings.get("backend", "cuda")
    model_info = config.get("models", {}).get(tier, {})
    model_fn = model_info.get("filename", "model.gguf")

    # 1. CUDA Out of Memory Detection
    if "out of memory" in full_text or "cudamalloc" in full_text or "failed to allocate buffer" in full_text:
        summary = "CUDA Out of Memory: GPU VRAM is full."
        advice = "Reduce GPU offload layers or change hardware backend to CPU/Cloud."
        manual_cmd = f"bin\\llama-server.exe -m {model_fn} --port {port} -ngl 0"
        return summary, advice, manual_cmd, lines

    # 2. Port Collision Detection
    if "address already in use" in full_text or "wsaeaddrinuse" in full_text or "10048" in full_text:
        summary = f"Port Conflict: Port {port} is already in use by another application."
        advice = f"Stop the process using port {port} or configure a different port."
        manual_cmd = f"netstat -ano | findstr :{port}"
        return summary, advice, manual_cmd, lines

    # 3. Model File Corrupted or Missing
    if "gguf_init_from_file: failed" in full_text or "cannot open file" in full_text:
        summary = f"Model File Error: Could not read '{model_fn}'."
        advice = "Verify model file in bin folder or download again through setup wizard."
        manual_cmd = "runtime\\python.exe setup.py"
        return summary, advice, manual_cmd, lines

    # 4. Python Module / Dependency Error
    if "modulenotfounderror" in full_text or "importerror" in full_text:
        summary = "Dependency Error: Required Python library failed to load."
        advice = "Install missing dependencies into the Python runtime."
        manual_cmd = "runtime\\python.exe -m pip install -r requirements.txt"
        return summary, advice, manual_cmd, lines

    # 5. ChromaDB Lock Error
    if "database is locked" in full_text or "sqlite3.operationalerror" in full_text:
        summary = "Database Lock: ChromaDB memory storage is locked by another instance."
        advice = "Close any existing Dot background processes before retrying."
        manual_cmd = "taskkill /F /IM python.exe"
        return summary, advice, manual_cmd, lines

    # Generic Fallback
    summary = f"{service_name} failed to respond on port {port}."
    advice = "Inspect the log lines below to identify the problem."
    if service_name == "Inference Engine":
        manual_cmd = f"bin\\llama-server.exe -m {model_fn} --port {port}"
    else:
        manual_cmd = f"runtime\\python.exe -m uvicorn server:app --host 127.0.0.1 --port {port}"

    return summary, advice, manual_cmd, lines


class StartupSupervisor:
    """Manages the startup telemetry window and handles service errors."""

    def __init__(self, root, config, py_exe):
        self.root = root
        self.config = config
        self.py_exe = py_exe

        self.root.title("Dot Assistant")
        self.root.geometry("540x390")
        self.root.resizable(False, False)
        self.root.configure(bg="#101012")

        self.center_window(540, 390)
        enable_dark_title_bar(self.root)

        self.is_expanded = False
        self.has_failed = False
        self.current_step = 0

        self.eng_proc = None
        self.back_proc = None
        self.front_proc = None
        self.eng_log_writer = None
        self.back_log_writer = None

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.build_ui()
        self.root.after(100, self.start_startup_flow)

    def on_close(self):
        """Handle supervisor window close button."""
        cleanup()
        try:
            self.root.destroy()
        except Exception:
            pass

    def center_window(self, width, height):
        """Center the window on the primary screen."""
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - width) // 2
        y = (sh - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def build_ui(self):
        """Construct the monochrome startup interface."""
        self.main_frame = tk.Frame(self.root, bg="#101012", padx=24, pady=20)
        self.main_frame.pack(fill="both", expand=True)

        # Header Area
        header_frame = tk.Frame(self.main_frame, bg="#101012")
        header_frame.pack(fill="x", pady=(0, 16))

        title_row = tk.Frame(header_frame, bg="#101012")
        title_row.pack(fill="x")

        self.dot_indicator = tk.Label(
            title_row, text="●", font=("Segoe UI", 12), fg="#ffffff", bg="#101012"
        )
        self.dot_indicator.pack(side="left", padx=(0, 8))

        self.lbl_title = tk.Label(
            title_row,
            text="Dot Assistant",
            font=("Segoe UI", 13, "bold"),
            fg="#ffffff",
            bg="#101012",
        )
        self.lbl_title.pack(side="left")

        self.lbl_version = tk.Label(
            title_row, text="v1.0.7", font=("Consolas", 10), fg="#71717a", bg="#101012"
        )
        self.lbl_version.pack(side="right")

        self.lbl_subtitle = tk.Label(
            header_frame,
            text="Starting local services...",
            font=("Segoe UI", 9),
            fg="#a1a1aa",
            bg="#101012",
            anchor="w",
        )
        self.lbl_subtitle.pack(fill="x", pady=(2, 0))

        # Checklist Area
        self.steps_frame = tk.Frame(
            self.main_frame, bg="#141416", bd=1, relief="solid", highlightbackground="#27272a"
        )
        self.steps_frame.pack(fill="x", pady=(0, 14))

        self.step_labels = []
        step_names = [
            "Environment & Hardware Verification",
            "Local Inference Engine (llama-server)",
            "Backend Orchestrator (FastAPI)",
            "Tool Registry & Memory Store",
        ]

        active_settings = self.config.get("active_settings", {})
        backend = active_settings.get("backend", "cuda").upper()
        tier = active_settings.get("selected_tier", "4B")
        if active_settings.get("backend") == "cloud":
            step_names[1] = "Cloud API Endpoint Verification"

        for i, name in enumerate(step_names):
            row = tk.Frame(self.steps_frame, bg="#141416", padx=12, pady=6)
            row.pack(fill="x")

            status_icon = tk.Label(
                row, text="○", font=("Consolas", 10, "bold"), fg="#71717a", bg="#141416", width=2
            )
            status_icon.pack(side="left", padx=(0, 8))

            name_lbl = tk.Label(
                row, text=name, font=("Segoe UI", 9), fg="#a1a1aa", bg="#141416"
            )
            name_lbl.pack(side="left")

            detail_lbl = tk.Label(
                row, text="", font=("Consolas", 8), fg="#71717a", bg="#141416"
            )
            detail_lbl.pack(side="right")

            self.step_labels.append({"icon": status_icon, "name": name_lbl, "detail": detail_lbl})

        # Progress Bar Area
        self.canvas_progress = tk.Canvas(
            self.main_frame, height=4, bg="#27272a", highlightthickness=0
        )
        self.canvas_progress.pack(fill="x", pady=(0, 12))
        self.progress_bar = self.canvas_progress.create_rectangle(0, 0, 0, 4, fill="#ffffff", width=0)

        # Telemetry Ticker
        telemetry_frame = tk.Frame(self.main_frame, bg="#101012")
        telemetry_frame.pack(fill="x", pady=(0, 10))

        self.lbl_ticker = tk.Label(
            telemetry_frame,
            text="Initializing supervisor...",
            font=("Consolas", 8),
            fg="#71717a",
            bg="#101012",
            anchor="w",
        )
        self.lbl_ticker.pack(side="left", fill="x", expand=True)

        self.btn_toggle_log = tk.Button(
            telemetry_frame,
            text="View Logs ▼",
            font=("Segoe UI", 8),
            fg="#a1a1aa",
            bg="#18181b",
            activebackground="#27272a",
            activeforeground="#ffffff",
            bd=0,
            padx=8,
            pady=2,
            cursor="hand2",
            command=self.toggle_log_drawer,
        )
        self.btn_toggle_log.pack(side="right")

        # Hidden Log Drawer Container
        self.log_container = tk.Frame(self.main_frame, bg="#0d0d0f", bd=1, relief="solid")
        self.log_text = tk.Text(
            self.log_container,
            height=8,
            font=("Consolas", 8),
            fg="#a1a1aa",
            bg="#0d0d0f",
            bd=0,
            padx=8,
            pady=8,
            wrap="none",
        )
        self.log_text.pack(fill="both", expand=True)

    def set_progress(self, percent):
        """Update the custom progress bar."""
        self.root.update_idletasks()
        cw = self.canvas_progress.winfo_width()
        bar_w = int(cw * (percent / 100.0))
        self.canvas_progress.coords(self.progress_bar, 0, 0, bar_w, 4)

    def update_step(self, step_idx, status, detail=""):
        """Update step icon and color in the checklist."""
        if step_idx < len(self.step_labels):
            item = self.step_labels[step_idx]
            if status == "running":
                item["icon"].configure(text="●", fg="#ffffff")
                item["name"].configure(fg="#ffffff")
            elif status == "done":
                item["icon"].configure(text="✔", fg="#ffffff")
                item["name"].configure(fg="#d4d4d8")
            elif status == "error":
                item["icon"].configure(text="✖", fg="#ef4444")
                item["name"].configure(fg="#ef4444")
            if detail:
                item["detail"].configure(text=detail)

    def set_ticker(self, text):
        """Update the bottom single-line telemetry status."""
        self.lbl_ticker.configure(text=text)

    def toggle_log_drawer(self):
        """Expand or collapse the live log viewer."""
        if not self.is_expanded:
            self.root.geometry("540x550")
            self.log_container.pack(fill="both", expand=True, pady=(4, 0))
            self.btn_toggle_log.configure(text="Hide Logs ▲")
            self.is_expanded = True
        else:
            self.log_container.pack_forget()
            self.root.geometry("540x390")
            self.btn_toggle_log.configure(text="View Logs ▼")
            self.is_expanded = False

    def append_log_line(self, line):
        """Append line to the log text widget."""
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")

    def start_startup_flow(self):
        """Execute the startup sequence in a background worker."""
        threading.Thread(target=self.run_startup, daemon=True).start()

    def run_startup(self):
        """Background thread executing the service startup sequence."""
        # Clean any orphaned processes from previous aborted launches
        kill_orphaned_servers()

        active_settings = self.config.get("active_settings", {})
        backend = active_settings.get("backend", "cuda")
        tier = active_settings.get("selected_tier", "4B")
        port = active_settings.get("port", 11434)
        gpu_layers = active_settings.get("gpu_layers", 99)

        # ----------------------------------------------------
        # Step 1: Environment & Hardware Verification
        # ----------------------------------------------------
        self.root.after(0, lambda: self.update_step(0, "running", f"{backend.upper()} / {tier}"))
        self.root.after(0, lambda: self.set_ticker("Checking system configuration..."))
        self.root.after(0, lambda: self.set_progress(15))
        time.sleep(0.3)

        if not check_essentials(self.config):
            self.root.after(
                0,
                lambda: self.show_failure_screen(
                    "Configuration Error",
                    "Required model files or engine binaries are missing.",
                    "Execute setup.py to configure and download model files.",
                    f"{self.py_exe} setup.py",
                    [f"Configuration check failed for tier '{tier}'."],
                ),
            )
            return

        self.root.after(0, lambda: self.update_step(0, "done", "OK"))
        self.root.after(0, lambda: self.set_progress(25))

        # ----------------------------------------------------
        # Step 2: Local Inference Engine (llama-server)
        # ----------------------------------------------------
        no_window_flag = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        if backend != "cloud":
            self.root.after(0, lambda: self.update_step(1, "running", f"Port {port}"))
            self.root.after(0, lambda: self.set_ticker("Starting llama-server inference engine..."))

            bin_dir = os.path.join(BASE_DIR, "bin")
            server_exe = os.path.join(bin_dir, "llama-server.exe")
            model_info = self.config.get("models", {}).get(tier, {})
            model_fn = model_info.get("filename", "")
            mmproj_fn = model_info.get("mmproj", "")
            context_size = model_info.get("context_size", 8192)

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
                "--alias", "dot-engine",
            ] + gpu_args

            self.eng_log_writer = open(ENGINE_LOG, "w", encoding="utf-8", errors="replace", buffering=1)
            open_log_writers.append(self.eng_log_writer)

            self.eng_proc = subprocess.Popen(
                engine_cmd,
                cwd=bin_dir,
                stdout=self.eng_log_writer,
                stderr=subprocess.STDOUT,
                creationflags=no_window_flag,
            )
            running_processes.append(self.eng_proc)

            # Telemetry loop with zero-wait failure detection
            start_t = time.time()
            engine_ready = False
            last_pos = 0

            while time.time() - start_t < 90:
                # 1. Instant crash detection
                if self.eng_proc.poll() is not None:
                    summary, advice, cmd_hint, lines = parse_error_diagnostics(
                        ENGINE_LOG, "Inference Engine", port, self.config
                    )
                    self.root.after(
                        0,
                        lambda: self.show_failure_screen(
                            "Inference Engine Failed", summary, advice, cmd_hint, lines
                        ),
                    )
                    return

                # 2. Tail log for live user feedback
                if os.path.exists(ENGINE_LOG):
                    try:
                        with open(ENGINE_LOG, "r", encoding="utf-8", errors="replace") as f:
                            f.seek(last_pos)
                            new_data = f.read()
                            last_pos = f.tell()
                            for line in new_data.splitlines():
                                line_clean = line.strip()
                                if line_clean:
                                    self.root.after(0, lambda l=line_clean: self.append_log_line(l))
                                    if "loading model" in line_clean.lower():
                                        self.root.after(
                                            0,
                                            lambda: self.set_ticker(
                                                f"Loading weights for {model_fn}..."
                                            ),
                                        )
                                    elif "model loaded" in line_clean.lower():
                                        self.root.after(
                                            0,
                                            lambda: self.set_ticker(
                                                "Model loaded into memory. Initializing network..."
                                            ),
                                        )
                    except Exception:
                        pass

                # 3. Check port readiness
                if is_port_open(port):
                    engine_ready = True
                    break

                pct = min(25 + int((time.time() - start_t) * 0.4), 55)
                self.root.after(0, lambda p=pct: self.set_progress(p))
                time.sleep(0.3)

            if not engine_ready:
                summary, advice, cmd_hint, lines = parse_error_diagnostics(
                    ENGINE_LOG, "Inference Engine", port, self.config
                )
                self.root.after(
                    0,
                    lambda: self.show_failure_screen(
                        "Inference Engine Timeout",
                        f"Server did not respond on port {port} within 90 seconds.",
                        advice,
                        cmd_hint,
                        lines,
                    ),
                )
                return

            self.root.after(0, lambda: self.update_step(1, "done", "Active"))
            self.root.after(0, lambda: self.set_progress(60))
        else:
            self.root.after(0, lambda: self.update_step(1, "done", "Cloud Connected"))
            self.root.after(0, lambda: self.set_progress(60))

        # ----------------------------------------------------
        # Step 3: Python Orchestrator Backend
        # ----------------------------------------------------
        self.root.after(0, lambda: self.update_step(2, "running", "Port 3000"))
        self.root.after(0, lambda: self.set_ticker("Starting FastAPI backend server on port 3000..."))

        backend_dir = os.path.join(BASE_DIR, "backend")
        backend_cmd = [
            self.py_exe,
            "-u",
            "-m",
            "uvicorn",
            "server:app",
            "--host",
            "127.0.0.1",
            "--port",
            "3000",
        ]
        backend_env = dict(os.environ)
        backend_env["PYTHONUNBUFFERED"] = "1"
        backend_env["PYTHONIOENCODING"] = "utf-8"
        backend_env["PYTHONUTF8"] = "1"

        self.back_log_writer = open(BACKEND_LOG, "w", encoding="utf-8", errors="replace", buffering=1)
        open_log_writers.append(self.back_log_writer)

        self.back_proc = subprocess.Popen(
            backend_cmd,
            cwd=backend_dir,
            stdout=self.back_log_writer,
            stderr=subprocess.STDOUT,
            creationflags=no_window_flag,
            env=backend_env,
        )
        running_processes.append(self.back_proc)

        # Telemetry loop for backend
        start_t = time.time()
        backend_ready = False
        last_pos = 0

        while time.time() - start_t < 90:
            # 1. Instant crash detection
            if self.back_proc.poll() is not None:
                if self.back_log_writer:
                    self.back_log_writer.flush()
                summary, advice, cmd_hint, lines = parse_error_diagnostics(
                    BACKEND_LOG, "Backend Server", 3000, self.config
                )
                self.root.after(
                    0,
                    lambda: self.show_failure_screen(
                        "Backend Server Failed", summary, advice, cmd_hint, lines
                    ),
                )
                return

            # 2. Tail backend log in real-time
            if os.path.exists(BACKEND_LOG):
                try:
                    with open(BACKEND_LOG, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(last_pos)
                        new_data = f.read()
                        last_pos = f.tell()
                        for line in new_data.splitlines():
                            line_clean = line.strip()
                            if line_clean:
                                self.root.after(0, lambda l=line_clean: self.append_log_line(l))
                                if "started server process" in line_clean.lower():
                                    self.root.after(
                                        0,
                                        lambda: self.set_ticker(
                                            "Backend process started. Loading tool registry..."
                                        ),
                                    )
                                elif "syncing tools" in line_clean.lower():
                                    self.root.after(
                                        0,
                                        lambda: self.set_ticker(
                                            "Syncing tool definitions to ChromaDB..."
                                        ),
                                    )
                                elif "uvicorn running on" in line_clean.lower():
                                    self.root.after(
                                        0,
                                        lambda: self.set_ticker(
                                            "Backend running on port 3000. Ready."
                                        ),
                                    )
                except Exception:
                    pass

            # 3. Check port 3000 readiness
            if is_port_open(3000):
                backend_ready = True
                break

            pct = min(60 + int((time.time() - start_t) * 0.45), 88)
            self.root.after(0, lambda p=pct: self.set_progress(p))
            time.sleep(0.3)

        if not backend_ready:
            if self.back_log_writer:
                self.back_log_writer.flush()
            summary, advice, cmd_hint, lines = parse_error_diagnostics(
                BACKEND_LOG, "Backend Server", 3000, self.config
            )
            self.root.after(
                0,
                lambda: self.show_failure_screen(
                    "Backend Server Timeout",
                    "Backend failed to bind to port 3000 within 90 seconds.",
                    advice,
                    cmd_hint,
                    lines,
                ),
            )
            return

        self.root.after(0, lambda: self.update_step(2, "done", "Active"))
        self.root.after(0, lambda: self.update_step(3, "done", "Synchronized"))
        self.root.after(0, lambda: self.set_progress(100))

        # ----------------------------------------------------
        # Step 4: Launch Neutralino UI and Smooth Handoff
        # ----------------------------------------------------
        self.root.after(0, lambda: self.set_ticker("All systems ready. Launching Dot..."))
        time.sleep(0.4)

        frontend_dir = os.path.join(BASE_DIR, "frontend")
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
                res_path = os.path.join(frontend_cwd, "resources.neu")
                alt_res = os.path.join(frontend_dir, "out", "Dot", "resources.neu")
                if os.path.exists(alt_res):
                    if not os.path.exists(res_path) or os.path.getsize(alt_res) != os.path.getsize(res_path):
                        try:
                            shutil.copy2(alt_res, res_path)
                        except Exception:
                            pass
                break

        if not frontend_cmd:
            frontend_cmd = ["cmd", "/c", "npx", "@neutralinojs/neu", "run"]
            frontend_cwd = frontend_dir

        self.front_proc = subprocess.Popen(frontend_cmd, cwd=frontend_cwd)
        running_processes.append(self.front_proc)

        # Hide supervisor window smoothly while keeping mainloop alive
        self.root.after(400, self.root.withdraw)

        # Wait until frontend is closed by user, then cleanup
        try:
            self.front_proc.wait()
        except KeyboardInterrupt:
            pass
        finally:
            cleanup()
            try:
                self.root.after(0, self.root.destroy)
            except Exception:
                pass

    def show_failure_screen(self, title, summary, advice, manual_cmd, log_lines):
        """Transform window into the Diagnostic Error Screen."""
        self.has_failed = True
        self.root.geometry("580x560")
        self.center_window(580, 560)

        # Clear main frame
        for widget in self.main_frame.winfo_children():
            widget.destroy()

        # Action Buttons Row (PACKED TO BOTTOM FIRST to guarantee visibility)
        actions_row = tk.Frame(self.main_frame, bg="#101012")
        actions_row.pack(side="bottom", fill="x", pady=(10, 0))

        def open_setup():
            cleanup()
            self.root.destroy()
            subprocess.Popen([self.py_exe, os.path.join(BASE_DIR, "setup.py")], cwd=BASE_DIR)

        def open_log_file():
            target_log = ENGINE_LOG if "engine" in title.lower() else BACKEND_LOG
            if os.path.exists(target_log):
                os.startfile(target_log)

        def retry():
            cleanup()
            self.root.destroy()
            python_bin = find_python_exe()
            if python_bin:
                subprocess.Popen([python_bin, os.path.join(BASE_DIR, "launcher.pyw")], cwd=BASE_DIR)

        btn_setup = tk.Button(
            actions_row,
            text="Open Setup Wizard",
            font=("Segoe UI", 9, "bold"),
            fg="#ffffff",
            bg="#27272a",
            activebackground="#3f3f46",
            activeforeground="#ffffff",
            bd=0,
            padx=14,
            pady=6,
            cursor="hand2",
            command=open_setup,
        )
        btn_setup.pack(side="left", padx=(0, 8))

        btn_log = tk.Button(
            actions_row,
            text="Open Log File",
            font=("Segoe UI", 9),
            fg="#d4d4d8",
            bg="#18181b",
            activebackground="#27272a",
            activeforeground="#ffffff",
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            command=open_log_file,
        )
        btn_log.pack(side="left", padx=(0, 8))

        btn_retry = tk.Button(
            actions_row,
            text="Retry Startup",
            font=("Segoe UI", 9),
            fg="#d4d4d8",
            bg="#18181b",
            activebackground="#27272a",
            activeforeground="#ffffff",
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            command=retry,
        )
        btn_retry.pack(side="left")

        btn_exit = tk.Button(
            actions_row,
            text="Exit",
            font=("Segoe UI", 9),
            fg="#71717a",
            bg="#101012",
            activebackground="#18181b",
            activeforeground="#ffffff",
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            command=lambda: (cleanup(), self.root.destroy()),
        )
        btn_exit.pack(side="right")

        # Error Banner at Top
        err_header = tk.Frame(self.main_frame, bg="#101012")
        err_header.pack(fill="x", pady=(0, 10))

        title_row = tk.Frame(err_header, bg="#101012")
        title_row.pack(fill="x")

        tk.Label(title_row, text="✖", font=("Segoe UI", 12, "bold"), fg="#ef4444", bg="#101012").pack(
            side="left", padx=(0, 8)
        )
        tk.Label(
            title_row, text=title, font=("Segoe UI", 13, "bold"), fg="#ffffff", bg="#101012"
        ).pack(side="left")

        # Diagnostic Explanation Box
        info_box = tk.Frame(
            self.main_frame, bg="#1c1917", bd=1, relief="solid", highlightbackground="#7f1d1d", padx=12, pady=8
        )
        info_box.pack(fill="x", pady=(0, 10))

        tk.Label(
            info_box,
            text=summary,
            font=("Segoe UI", 9, "bold"),
            fg="#f87171",
            bg="#1c1917",
            anchor="w",
            wraplength=530,
            justify="left",
        ).pack(fill="x")

        tk.Label(
            info_box,
            text=advice,
            font=("Segoe UI", 8),
            fg="#d6d3d1",
            bg="#1c1917",
            anchor="w",
            wraplength=530,
            justify="left",
        ).pack(fill="x", pady=(3, 0))

        # Manual Sync Command Row
        cmd_box = tk.Frame(self.main_frame, bg="#141416", bd=1, relief="solid", highlightbackground="#27272a", padx=10, pady=6)
        cmd_box.pack(fill="x", pady=(0, 10))

        tk.Label(
            cmd_box,
            text="Manual Sync / Recovery Command:",
            font=("Segoe UI", 8, "bold"),
            fg="#a1a1aa",
            bg="#141416",
            anchor="w",
        ).pack(fill="x")

        cmd_entry_row = tk.Frame(cmd_box, bg="#141416")
        cmd_entry_row.pack(fill="x", pady=(3, 0))

        cmd_entry = tk.Entry(
            cmd_entry_row,
            font=("Consolas", 8),
            fg="#ffffff",
            bg="#09090b",
            bd=1,
            relief="solid",
        )
        cmd_entry.insert(0, manual_cmd)
        cmd_entry.configure(state="readonly")
        cmd_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def copy_cmd():
            self.root.clipboard_clear()
            self.root.clipboard_append(manual_cmd)
            btn_copy.configure(text="Copied!")
            self.root.after(1200, lambda: btn_copy.configure(text="Copy"))

        btn_copy = tk.Button(
            cmd_entry_row,
            text="Copy",
            font=("Segoe UI", 8),
            fg="#ffffff",
            bg="#27272a",
            activebackground="#3f3f46",
            activeforeground="#ffffff",
            bd=0,
            padx=10,
            pady=2,
            cursor="hand2",
            command=copy_cmd,
        )
        btn_copy.pack(side="right")

        # Terminal Error Logs (takes remaining space)
        tk.Label(
            self.main_frame,
            text="Error Log Traceback:",
            font=("Segoe UI", 8, "bold"),
            fg="#71717a",
            bg="#101012",
            anchor="w",
        ).pack(fill="x", pady=(0, 2))

        err_text_frame = tk.Frame(self.main_frame, bg="#0d0d0f", bd=1, relief="solid")
        err_text_frame.pack(fill="both", expand=True, pady=(0, 4))

        err_text = tk.Text(
            err_text_frame,
            font=("Consolas", 8),
            fg="#ef4444",
            bg="#0d0d0f",
            bd=0,
            padx=8,
            pady=6,
            wrap="none",
        )
        err_text.pack(fill="both", expand=True)

        # If log_lines is empty, fallback to reading file directly
        lines_to_show = log_lines if log_lines else read_last_log_lines(BACKEND_LOG if "backend" in title.lower() else ENGINE_LOG, 40)
        if not lines_to_show:
            lines_to_show = ["No traceback recorded in log file yet.", f"Log file path: {BACKEND_LOG if 'backend' in title.lower() else ENGINE_LOG}"]

        for line in lines_to_show:
            err_text.insert("end", line + "\n")
        err_text.see("end")


def main():
    """Main launcher entry point."""
    mutex = acquire_single_instance_lock()
    if not mutex:
        focus_existing_window()
        return

    py_exe = find_python_exe()
    if not py_exe:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Dot - Setup Required",
            "Python runtime was not found.\n\n"
            "Please run 'start_setup.bat' or download the installer from GitHub Releases.",
        )
        root.destroy()
        return

    config = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}

    # Launch setup wizard if configuration or essentials are missing
    if not config or not check_essentials(config):
        subprocess.run([py_exe, os.path.join(BASE_DIR, "setup.py")], cwd=BASE_DIR)
        if not os.path.exists(CONFIG_PATH):
            return
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            return
        if not check_essentials(config):
            return

    # Start the Tkinter Startup & Health Supervisor window
    root = tk.Tk()
    StartupSupervisor(root, config, py_exe)
    root.mainloop()


if __name__ == "__main__":
    main()
