import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
import zipfile
from tkinter import filedialog

# ==========================================
# 1. IMMEDIATE LOGGING & EXCEPTION HOOKS
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "appConfig.json")
LOG_FILE = os.path.join(BASE_DIR, "error.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.ERROR,
    format="[%(asctime)s] %(levelname)s [%(filename)s:%(lineno)d] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)


def log_error(msg, exc_info=True):
    logging.error(msg, exc_info=exc_info)


def global_exception_handler(exc_type, exc_value, exc_traceback):
    logging.error("Unhandled main thread exception", exc_info=(exc_type, exc_value, exc_traceback))
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


def thread_exception_handler(args):
    logging.error("Unhandled worker thread exception", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))


sys.excepthook = global_exception_handler
threading.excepthook = thread_exception_handler

# Safe import of third-party libraries with error logging
try:
    import customtkinter as ctk
    import psutil
    import requests
except ImportError as err:
    log_error(f"Missing required setup dependency: {err}", exc_info=True)
    print(f"\n[ERROR] Setup initialization failed: {err}")
    print(f"Please run 'start_setup.bat' to install dependencies automatically.")
    print(f"Log written to: {LOG_FILE}\n")
    sys.exit(1)

# ==========================================
# 2. THEME & PROVIDER CONSTANTS
# ==========================================
COLOR_BG = "#000000"
COLOR_PANEL = "#141414"
COLOR_PANEL_ALT = "#1a0d0d"
COLOR_ACCENT = "#dc2626"
COLOR_ACCENT_HOVER = "#991b1b"
COLOR_ACCENT_MUTED = "#7f1d1d"
COLOR_TEXT = "#f5f5f5"
COLOR_TEXT_MUTED = "#a3a3a3"
COLOR_BACK_BTN = "#2a2a2a"
COLOR_BACK_BTN_HOVER = "#3a3a3a"
COLOR_ERROR = "#e5332a"
COLOR_ERROR_HOVER = "#b91c1c"
COLOR_SUCCESS = "#22c55e"
COLOR_SUCCESS_HOVER = "#16a34a"

CLOUD_PROVIDERS = {
    "openai": {"label": "OpenAI", "base_url": "https://api.openai.com/v1", "default_model": "gpt-4o-mini"},
    "gemini": {"label": "Google Gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "default_model": "gemini-3.7-flash"},
    "custom": {"label": "Custom / Other (OpenAI-compatible)", "base_url": "", "default_model": ""}
}


def get_python_exe():
    venv_py = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
    return venv_py if os.path.exists(venv_py) else sys.executable


# ==========================================
# 3. MAIN INSTALLER APPLICATION
# ==========================================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


class DotInstaller(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Dot Setup & Rig Analyzer")
        self.geometry("620x750")
        self.resizable(False, False)
        self.configure(fg_color=COLOR_BG)

        self.config = self.load_configuration()
        self.ram_gb, self.vram_gb, self.cuda_version, self.has_cuda = self.probe_hardware()

        # State Variables bound directly to inputs (auto-persisted across navigation)
        self.backend_var = ctk.StringVar(value="cuda" if self.has_cuda else "cpu")
        self.tier_var = ctk.StringVar(value=self.get_recommended_tier())
        self.user_name_var = ctk.StringVar(value=self.config.get("active_settings", {}).get("user_name", "User"))
        self.layers_var = ctk.IntVar(value=self.config.get("active_settings", {}).get("gpu_layers", 99))

        # Discover existing GitHub Token from .env if present
        existing_gh_token = ""
        for ep in [os.path.join(BASE_DIR, "dum-e", "src", "dot", ".env"), os.path.join(BASE_DIR, "dum-e", ".env"), os.path.join(BASE_DIR, ".env")]:
            if os.path.exists(ep):
                try:
                    with open(ep, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip().startswith("GITHUB_TOKEN="):
                                existing_gh_token = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                                break
                    if existing_gh_token:
                        break
                except Exception:
                    pass
        self.github_token_var = ctk.StringVar(value=existing_gh_token)

        cloud_cfg = self.config.get("cloud", {})
        provider_key = cloud_cfg.get("provider", "openai")
        self.provider_var = ctk.StringVar(value=CLOUD_PROVIDERS.get(provider_key, CLOUD_PROVIDERS["openai"])["label"])
        self.base_url_var = ctk.StringVar(value=cloud_cfg.get("base_url", CLOUD_PROVIDERS["openai"]["base_url"]))
        self.model_var = ctk.StringVar(value=cloud_cfg.get("model", CLOUD_PROVIDERS["openai"]["default_model"]))
        self.api_key_var = ctk.StringVar(value=cloud_cfg.get("api_key", ""))

        self.container = ctk.CTkFrame(self, corner_radius=12, fg_color=COLOR_PANEL)
        self.container.pack(fill="both", expand=True, padx=20, pady=20)

        self.show_rig_analysis()

    # ----------------------------------------------------
    # CONFIG & HARDWARE PROBING
    # ----------------------------------------------------
    def load_configuration(self):
        try:
            if not os.path.exists(CONFIG_FILE):
                raise FileNotFoundError(f"Configuration file not found: {CONFIG_FILE}")
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if "cloud" not in cfg:
                cfg["cloud"] = {"provider": "openai", "base_url": CLOUD_PROVIDERS["openai"]["base_url"], "model": CLOUD_PROVIDERS["openai"]["default_model"], "api_key": ""}
            if "allowed_processes" not in cfg:
                cfg["allowed_processes"] = [
                    "chrome.exe", "msedge.exe", "firefox.exe", "code.exe",
                    "discord.exe", "spotify.exe", "notepad.exe", "cmd.exe",
                    "powershell.exe", "wt.exe", "calc.exe", "explorer.exe"
                ]
            return cfg
        except Exception as e:
            log_error(f"Failed to load appConfig.json: {e}")
            self.after(100, lambda: self.show_fatal_error_screen(f"Could not load appConfig.json: {e}"))
            return {}

    def probe_hardware(self):
        ram = 8.0
        try:
            ram = round(psutil.virtual_memory().total / (1024**3), 1)
        except Exception as e:
            log_error(f"RAM probing warning: {e}")

        vram, cuda_ver, has_cuda = 0.0, 0.0, False
        try:
            vram_out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                encoding="utf-8", stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            vram = round(int(vram_out.strip().split("\n")[0]) / 1024, 1)
            has_cuda = True

            full_out = subprocess.check_output(["nvidia-smi"], encoding="utf-8", stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            match = re.search(r"CUDA\s+(?:UMD\s+)?Version:\s*(\d+(?:\.\d+)?)", full_out, re.IGNORECASE)
            cuda_ver = float(match.group(1)) if match else 11.0
        except Exception:
            has_cuda = False

        return ram, vram, cuda_ver, has_cuda

    def get_recommended_tier(self):
        if self.vram_gb >= 12 or self.ram_gb >= 32:
            return "12B"
        elif self.vram_gb >= 6 or self.ram_gb >= 16:
            return "4B"
        return "2B"

    # ----------------------------------------------------
    # UI NAVIGATION HELPERS
    # ----------------------------------------------------
    def clear_container(self):
        for widget in self.container.winfo_children():
            widget.destroy()

    def get_step_sequence(self):
        return ["Hardware", "Personalize", "Install"] if self.backend_var.get() == "cloud" else ["Hardware", "Compute Tier", "Model Files", "Personalize", "Install"]

    def make_header(self, step_name, title):
        self.clear_container()
        steps = self.get_step_sequence()
        idx = (steps.index(step_name) + 1) if step_name in steps else 1
        ctk.CTkLabel(self.container, text=f"STEP {idx} OF {len(steps)} | {step_name.upper()}", font=("Arial", 11, "bold"), text_color=COLOR_ACCENT).pack(pady=(15, 0))
        ctk.CTkLabel(self.container, text=title, font=("Arial", 22, "bold"), text_color=COLOR_TEXT).pack(pady=(5, 10))

    def make_nav_row(self, back_cmd, next_text, next_cmd):
        nav = ctk.CTkFrame(self.container, fg_color="transparent")
        nav.pack(side="bottom", fill="x", padx=30, pady=20)
        if back_cmd:
            ctk.CTkButton(nav, text="< Back", command=back_cmd, width=110, fg_color=COLOR_BACK_BTN, hover_color=COLOR_BACK_BTN_HOVER, text_color=COLOR_TEXT).pack(side="left")
        ctk.CTkButton(nav, text=next_text, command=next_cmd, fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, text_color=COLOR_TEXT).pack(side="right")

    # ----------------------------------------------------
    # STEP 1: RIG ANALYSIS
    # ----------------------------------------------------
    def show_rig_analysis(self):
        self.make_header("Hardware", "Hardware Analysis")

        info_frame = ctk.CTkFrame(self.container, fg_color=COLOR_PANEL_ALT)
        info_frame.pack(fill="x", padx=30, pady=10)

        gpu_txt = f"NVIDIA GPU ({self.vram_gb} GB VRAM) - CUDA v{self.cuda_version}" if self.has_cuda else "No NVIDIA GPU Detected (CPU Mode)"
        ctk.CTkLabel(info_frame, text=f"* System Memory: {self.ram_gb} GB RAM", font=("Arial", 14), text_color=COLOR_TEXT).pack(anchor="w", padx=20, pady=(10, 4))
        ctk.CTkLabel(info_frame, text=f"* Graphics Backend: {gpu_txt}", font=("Arial", 14), text_color=COLOR_TEXT).pack(anchor="w", padx=20, pady=(0, 10))

        ctk.CTkLabel(self.container, text="Select Compute Engine:", font=("Arial", 14, "bold"), text_color=COLOR_TEXT).pack(anchor="w", padx=30, pady=(12, 6))

        r_opts = [
            ("cuda", "CUDA (NVIDIA GPU Acceleration - Recommended)", self.has_cuda),
            ("cpu", "AVX2 (CPU Only - Standard Fallback)", True),
            ("cloud", "Cloud API (Fully Remote - Zero Local Downloads)", True)
        ]
        for val, label, enabled in r_opts:
            r = ctk.CTkRadioButton(self.container, text=label, variable=self.backend_var, value=val, fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, text_color=COLOR_TEXT, border_color=COLOR_TEXT_MUTED)
            r.pack(pady=5, anchor="w", padx=30)
            if not enabled:
                r.configure(state="disabled")

        self.make_nav_row(None, "Continue", lambda: self.show_user_details() if self.backend_var.get() == "cloud" else self.show_model_selection())

    # ----------------------------------------------------
    # STEP 2: MODEL SELECTION
    # ----------------------------------------------------
    def show_model_selection(self):
        self.make_header("Compute Tier", "Select Model")

        recommended = self.get_recommended_tier()
        ctk.CTkLabel(self.container, text=f"Recommended for your setup: Gemma 4 ({recommended})", font=("Arial", 13, "bold"), text_color=COLOR_ACCENT).pack(anchor="w", padx=30, pady=(0, 15))

        for tier in self.config.get("models", {}).keys():
            ctk.CTkRadioButton(self.container, text=f"Gemma 4 ({tier})", variable=self.tier_var, value=tier, fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, text_color=COLOR_TEXT, border_color=COLOR_TEXT_MUTED).pack(pady=8, anchor="w", padx=30)

        self.make_nav_row(self.show_rig_analysis, "Next: Model Files", self.show_model_files)

    # ----------------------------------------------------
    # STEP 3: MODEL FILES VERIFICATION & SMART DOWNLOAD
    # ----------------------------------------------------
    def find_existing_model_dir(self, tier, model_fn):
        candidates = [
            os.path.join(os.path.expanduser("~"), "Downloads"),
            os.path.join(os.path.dirname(BASE_DIR), f"dot-engine-{tier.lower()}"),
            os.path.join(os.path.dirname(BASE_DIR), "dot-engine"),
            os.path.join("E:", os.sep, "dot-engine", f"dot-engine-{tier.lower()}"),
            os.path.join("E:", os.sep, "dot-engine"),
            os.path.join("D:", os.sep, "dot-engine", f"dot-engine-{tier.lower()}"),
            os.path.join("C:", os.sep, "dot-engine", f"dot-engine-{tier.lower()}"),
        ]
        for c in candidates:
            if os.path.exists(c):
                p = os.path.join(c, model_fn)
                if os.path.exists(p) and os.path.getsize(p) > 1024 * 1024:
                    return c
        return None

    def import_from_source(self, src_path, bin_dir, model_fn, mmproj_fn):
        os.makedirs(bin_dir, exist_ok=True)
        count = 0
        if os.path.isdir(src_path):
            for item in os.listdir(src_path):
                if item in (model_fn, mmproj_fn) or item.endswith((".gguf", ".dll")) or item == "llama-server.exe":
                    s = os.path.join(src_path, item)
                    d = os.path.join(bin_dir, item)
                    if not os.path.exists(d):
                        try:
                            os.link(s, d)
                            count += 1
                        except Exception:
                            try:
                                shutil.copy2(s, d)
                                count += 1
                            except Exception as err:
                                log_error(f"Failed to copy {s} to {d}: {err}")
        elif os.path.isfile(src_path):
            fn = os.path.basename(src_path)
            d = os.path.join(bin_dir, fn)
            if not os.path.exists(d):
                try:
                    os.link(src_path, d)
                    count += 1
                except Exception:
                    shutil.copy2(src_path, d)
                    count += 1
        return count

    def show_model_files(self):
        self.make_header("Model Files", "Model Files Setup")

        tier = self.tier_var.get()
        model_info = self.config.get("models", {}).get(tier, {})
        if not model_info:
            self.show_fatal_error_screen(f"Configuration missing model specs for tier '{tier}'")
            return

        model_fn, mmproj_fn = model_info["filename"], model_info["mmproj"]
        repo_id = model_info["repo_id"]

        bin_dir = os.path.join(BASE_DIR, "bin")
        os.makedirs(bin_dir, exist_ok=True)

        ctk.CTkLabel(
            self.container,
            text=(
                f"Dot uses Gemma 4 ({tier}) for local multimodal intelligence.\n"
                "Download automatically below, auto-import if already on your PC, or select a file."
            ),
            font=("Arial", 12), text_color=COLOR_TEXT_MUTED, justify="left", wraplength=520
        ).pack(anchor="w", padx=30, pady=(0, 6))

        status_box = ctk.CTkFrame(self.container, fg_color=COLOR_PANEL_ALT)
        status_box.pack(fill="x", padx=30, pady=(0, 6))

        labels = {}
        for title, fn in [("Main Model (GGUF)", model_fn), ("Vision Projector (mmproj)", mmproj_fn)]:
            row = ctk.CTkFrame(status_box, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=4)
            ctk.CTkLabel(row, text=f"{title}: {fn}", font=("Arial", 11), text_color=COLOR_TEXT).pack(side="left")
            lbl = ctk.CTkLabel(row, text="Checking...", font=("Arial", 11, "bold"))
            lbl.pack(side="right")
            labels[fn] = lbl

        err_lbl = ctk.CTkLabel(self.container, text="", font=("Arial", 11), text_color=COLOR_ERROR)
        err_lbl.pack(pady=2)

        def refresh_status():
            all_ok = True
            for fn, lbl in labels.items():
                p = os.path.join(bin_dir, fn)
                exists = os.path.exists(p) and os.path.getsize(p) > 1024 * 1024
                lbl.configure(text="Found" if exists else "Not found", text_color=COLOR_SUCCESS if exists else COLOR_ERROR)
                all_ok = all_ok and exists
            return all_ok

        dl_status_lbl = ctk.CTkLabel(self.container, text="", font=("Arial", 11), text_color=COLOR_TEXT)
        dl_status_lbl.pack(pady=(0, 2))

        dl_progress = ctk.CTkProgressBar(self.container, width=520, progress_color=COLOR_ACCENT)
        dl_progress.set(0)

        # Download Worker
        downloading = [False]

        def start_auto_download():
            if downloading[0]:
                return
            downloading[0] = True
            dl_btn.configure(state="disabled", text="Downloading...")
            dl_progress.pack(pady=4)

            def dl_worker():
                try:
                    targets = [
                        (model_fn, f"https://huggingface.co/{repo_id}/resolve/main/{model_fn}"),
                        (mmproj_fn, f"https://huggingface.co/{repo_id}/resolve/main/{mmproj_fn}")
                    ]
                    for idx, (fn, url) in enumerate(targets):
                        target_file = os.path.join(bin_dir, fn)
                        if os.path.exists(target_file) and os.path.getsize(target_file) > 1024 * 1024:
                            continue

                        part_file = target_file + ".part"
                        self.after(0, lambda f=fn: dl_status_lbl.configure(text=f"Connecting to download {f}..."))
                        res = requests.get(url, stream=True, timeout=30)
                        res.raise_for_status()

                        total_bytes = int(res.headers.get("content-length", 0))
                        downloaded = 0
                        start_t = time.time()
                        last_update_t = start_t

                        with open(part_file, "wb") as f:
                            for chunk in res.iter_content(chunk_size=1024 * 512):
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    now = time.time()
                                    if now - last_update_t > 0.4:
                                        last_update_t = now
                                        elapsed = max(now - start_t, 0.1)
                                        speed_mb = (downloaded / (1024 * 1024)) / elapsed
                                        pct = (downloaded / total_bytes) if total_bytes > 0 else 0
                                        msg = f"Downloading {fn}: {round(downloaded/(1024**3), 2)}/{round(total_bytes/(1024**3), 2)} GB ({int(pct*100)}%) - {round(speed_mb, 1)} MB/s"
                                        self.after(0, lambda m=msg, p=pct: (dl_status_lbl.configure(text=m), dl_progress.set(p)))

                        if os.path.exists(target_file):
                            os.remove(target_file)
                        os.rename(part_file, target_file)

                    self.after(0, lambda: (
                        dl_status_lbl.configure(text="Download Complete! Models ready.", text_color=COLOR_SUCCESS),
                        dl_btn.configure(state="normal", text="Downloaded"),
                        refresh_status()
                    ))
                except Exception as ex:
                    log_error(f"Auto-download failed: {ex}")
                    self.after(0, lambda m=str(ex): (
                        dl_status_lbl.configure(text=f"Download error: {m[:100]}", text_color=COLOR_ERROR),
                        dl_btn.configure(state="normal", text="Retry Download")
                    ))
                finally:
                    downloading[0] = False

            threading.Thread(target=dl_worker, daemon=True).start()

        # Action Buttons Area
        actions_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        actions_frame.pack(fill="x", padx=30, pady=4)

        dl_btn = ctk.CTkButton(
            actions_frame, text="Download Automatically (1-Click)", command=start_auto_download,
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, text_color=COLOR_TEXT, height=34
        )
        dl_btn.pack(fill="x", pady=(0, 6))

        # Check for auto-detected local files
        detected_dir = self.find_existing_model_dir(tier, model_fn)
        if detected_dir and not refresh_status():
            det_frame = ctk.CTkFrame(self.container, fg_color=COLOR_PANEL_ALT)
            det_frame.pack(fill="x", padx=30, pady=(2, 6))
            folder_display = os.path.basename(detected_dir) or detected_dir
            ctk.CTkLabel(det_frame, text=f"Found on PC in: {folder_display}", font=("Arial", 11, "bold"), text_color=COLOR_SUCCESS).pack(side="left", padx=10, pady=4)

            def do_import():
                self.import_from_source(detected_dir, bin_dir, model_fn, mmproj_fn)
                refresh_status()
                det_frame.destroy()

            ctk.CTkButton(det_frame, text="Import (Instant)", width=120, command=do_import, fg_color=COLOR_SUCCESS, hover_color=COLOR_SUCCESS_HOVER).pack(side="right", padx=10, pady=4)

        # File Chooser Buttons
        chooser_row = ctk.CTkFrame(self.container, fg_color="transparent")
        chooser_row.pack(fill="x", padx=30, pady=2)

        def pick_file():
            f = filedialog.askopenfilename(title="Select GGUF Model File", filetypes=[("GGUF Model Files", "*.gguf"), ("All files", "*.*")])
            if f:
                self.import_from_source(f, bin_dir, model_fn, mmproj_fn)
                refresh_status()

        def pick_folder():
            d = filedialog.askdirectory(title="Select Folder Containing Models")
            if d:
                self.import_from_source(d, bin_dir, model_fn, mmproj_fn)
                refresh_status()

        ctk.CTkButton(chooser_row, text="Select File...", command=pick_file, width=120, fg_color=COLOR_BACK_BTN, hover_color=COLOR_BACK_BTN_HOVER, text_color=COLOR_TEXT).pack(side="left", padx=(0, 5))
        ctk.CTkButton(chooser_row, text="Select Folder...", command=pick_folder, width=120, fg_color=COLOR_BACK_BTN, hover_color=COLOR_BACK_BTN_HOVER, text_color=COLOR_TEXT).pack(side="left", padx=5)
        ctk.CTkButton(chooser_row, text="Open bin Folder", command=lambda: os.startfile(bin_dir), width=120, fg_color=COLOR_BACK_BTN, hover_color=COLOR_BACK_BTN_HOVER, text_color=COLOR_TEXT).pack(side="right")

        refresh_status()

        def on_next():
            if refresh_status():
                self.show_user_details()
            else:
                err_lbl.configure(text="Both model files must be in the bin folder before continuing.")

        self.make_nav_row(self.show_model_selection, "Check & Continue", on_next)

    # ----------------------------------------------------
    # STEP 4: PERSONALIZATION & CLOUD CONFIG
    # ----------------------------------------------------
    def show_user_details(self):
        self.make_header("Personalize", "Personalize Assistant")
        is_cloud = self.backend_var.get() == "cloud"

        ctk.CTkLabel(self.container, text="User Name / Call Sign:", font=("Arial", 13), text_color=COLOR_TEXT).pack(anchor="w", padx=30, pady=(5, 2))
        ctk.CTkEntry(self.container, textvariable=self.user_name_var, width=520, fg_color=COLOR_PANEL_ALT, border_color=COLOR_ACCENT_MUTED, text_color=COLOR_TEXT).pack(anchor="w", padx=30, pady=(0, 8))

        ctk.CTkLabel(self.container, text="GitHub Personal Access Token (Optional for GitHub MCP):", font=("Arial", 13), text_color=COLOR_TEXT).pack(anchor="w", padx=30, pady=(5, 2))
        ctk.CTkEntry(self.container, textvariable=self.github_token_var, placeholder_text="ghp_... (Optional)", show="*", width=520, fg_color=COLOR_PANEL_ALT, border_color=COLOR_ACCENT_MUTED, text_color=COLOR_TEXT).pack(anchor="w", padx=30, pady=(0, 8))

        if is_cloud:
            def on_provider_change(val):
                for p_info in CLOUD_PROVIDERS.values():
                    if p_info["label"] == val:
                        self.base_url_var.set(p_info["base_url"])
                        self.model_var.set(p_info["default_model"])
                        break

            ctk.CTkLabel(self.container, text="Cloud Provider:", font=("Arial", 13), text_color=COLOR_TEXT).pack(anchor="w", padx=30, pady=(5, 2))
            ctk.CTkOptionMenu(
                self.container, values=[p["label"] for p in CLOUD_PROVIDERS.values()], variable=self.provider_var,
                command=on_provider_change, width=520, fg_color=COLOR_PANEL_ALT, button_color=COLOR_ACCENT, button_hover_color=COLOR_ACCENT_HOVER, dropdown_fg_color=COLOR_PANEL, text_color=COLOR_TEXT
            ).pack(anchor="w", padx=30, pady=(0, 8))

            ctk.CTkLabel(self.container, text="Base URL:", font=("Arial", 13), text_color=COLOR_TEXT).pack(anchor="w", padx=30, pady=(5, 2))
            ctk.CTkEntry(self.container, textvariable=self.base_url_var, width=520, fg_color=COLOR_PANEL_ALT, border_color=COLOR_ACCENT_MUTED, text_color=COLOR_TEXT).pack(anchor="w", padx=30, pady=(0, 8))

            ctk.CTkLabel(self.container, text="Model:", font=("Arial", 13), text_color=COLOR_TEXT).pack(anchor="w", padx=30, pady=(5, 2))
            ctk.CTkEntry(self.container, textvariable=self.model_var, width=520, fg_color=COLOR_PANEL_ALT, border_color=COLOR_ACCENT_MUTED, text_color=COLOR_TEXT).pack(anchor="w", padx=30, pady=(0, 8))

            ctk.CTkLabel(self.container, text="API Key:", font=("Arial", 13), text_color=COLOR_TEXT).pack(anchor="w", padx=30, pady=(5, 2))
            self.api_entry = ctk.CTkEntry(self.container, textvariable=self.api_key_var, show="*", width=520, fg_color=COLOR_PANEL_ALT, border_color=COLOR_ACCENT_MUTED, text_color=COLOR_TEXT)
            self.api_entry.pack(anchor="w", padx=30, pady=(0, 10))

        elif self.backend_var.get() == "cuda":
            ctk.CTkLabel(self.container, text="GPU Offload Layers (Advanced):", font=("Arial", 13), text_color=COLOR_TEXT).pack(anchor="w", padx=30, pady=(5, 2))
            layer_lbl = ctk.CTkLabel(self.container, text=f"{self.layers_var.get()} Layers", font=("Arial", 12), text_color=COLOR_TEXT_MUTED)
            slider = ctk.CTkSlider(
                self.container, from_=0, to=99, number_of_steps=99, variable=self.layers_var,
                command=lambda v: layer_lbl.configure(text=f"{int(v)} Layers (Max Offload)" if int(v) == 99 else f"{int(v)} Layers"),
                width=520, progress_color=COLOR_ACCENT, button_color=COLOR_ACCENT, button_hover_color=COLOR_ACCENT_HOVER
            )
            slider.pack(anchor="w", padx=30, pady=(0, 5))
            layer_lbl.pack(anchor="w", padx=30, pady=(0, 10))

        back_cmd = self.show_rig_analysis if is_cloud else self.show_model_files
        self.make_nav_row(back_cmd, "Start Installation", self.start_installation)

    # ----------------------------------------------------
    # STEP 5: WORKER & INSTALLATION
    # ----------------------------------------------------
    def start_installation(self):
        if self.backend_var.get() == "cloud" and not self.api_key_var.get().strip():
            self.api_entry.configure(border_color=COLOR_ERROR)
            return

        self.make_header("Install", "Installing Components...")
        self.progress = ctk.CTkProgressBar(self.container, width=520, progress_color=COLOR_ACCENT)
        self.progress.pack(pady=20)
        self.progress.set(0)

        self.status_lbl = ctk.CTkLabel(self.container, text="Starting installation pipeline...", font=("Arial", 13), text_color=COLOR_TEXT)
        self.status_lbl.pack(pady=10)

        threading.Thread(target=self.run_install_worker, daemon=True).start()

    def update_status(self, text, val=None):
        self.after(0, lambda: self.status_lbl.configure(text=text))
        if val is not None:
            self.after(0, lambda: self.progress.set(val))

    def run_install_worker(self):
        try:
            py_exe = get_python_exe()

            # 1. Verify / Install Python project requirements
            self.update_status("Checking Python dependencies...", 0.1)
            needs_pip = False
            try:
                check_res = subprocess.run(
                    [py_exe, "-c", "import torch, fastapi, uvicorn, fastmcp, playwright, pynput, bs4, httpx"],
                    capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                )
                if check_res.returncode != 0:
                    needs_pip = True
            except Exception:
                needs_pip = True

            req_path = os.path.join(BASE_DIR, "requirements.txt")
            if needs_pip and os.path.exists(req_path):
                self.update_status("Installing Python dependencies (PyTorch, MCP, audio models)...", 0.15)
                res = subprocess.run([py_exe, "-m", "pip", "install", "-r", req_path, "--disable-pip-version-check"], capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if res.returncode != 0:
                    log_error(f"pip install failed: {res.stderr}")
                    raise RuntimeError(f"pip install failed: {res.stderr[:200] if res.stderr else 'unknown error'}")

            # 2. Install Playwright browser
            self.update_status("Ensuring Playwright browser binaries...", 0.25)
            try:
                subprocess.run([py_exe, "-m", "playwright", "install", "chromium"], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except Exception as pw_err:
                log_error(f"Playwright browser install warning: {pw_err}")

            # 3. Frontend npm install (skip if node_modules already exists)
            dume_dir = os.path.join(BASE_DIR, "dum-e")
            nm_dir = os.path.join(dume_dir, "node_modules")
            if os.path.exists(os.path.join(dume_dir, "package.json")):
                if not os.path.exists(nm_dir) or len(os.listdir(nm_dir)) < 5:
                    self.update_status("Installing frontend dependencies (npm install)...", 0.35)
                    npm_cmd = shutil.which("npm") or "npm"
                    subprocess.run([npm_cmd, "install"], cwd=dume_dir, shell=True, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                else:
                    self.update_status("Frontend dependencies verified...", 0.35)

                # Ensure frontend is built and bundled for Neutralino desktop
                dume_res = os.path.join(dume_dir, "bin", "resources.neu")
                out_res = os.path.join(dume_dir, "out", "Dot", "resources.neu")
                dist_index = os.path.join(dume_dir, "dist", "index.html")
                if not os.path.exists(dume_res) or not os.path.exists(out_res) or not os.path.exists(dist_index):
                    self.update_status("Building Dot desktop application bundle...", 0.4)
                    try:
                        npx_cmd = shutil.which("npx") or "npx"
                        subprocess.run([npx_cmd, "-y", "@neutralinojs/neu", "build"], cwd=dume_dir, shell=True, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                        if os.path.exists(out_res):
                            shutil.copy2(out_res, dume_res)
                            shutil.copy2(out_res, os.path.join(dume_dir, "resources.neu"))
                            built_exe = os.path.join(dume_dir, "out", "Dot", "Dot-win_x64.exe")
                            if os.path.exists(built_exe):
                                shutil.copy2(built_exe, os.path.join(dume_dir, "bin", "Dot-win_x64.exe"))
                    except Exception as neu_err:
                        log_error(f"Neutralino build warning: {neu_err}")

            backend = self.backend_var.get()

            # 4. Local Engine Downloads
            if backend != "cloud":
                bin_dir = os.path.join(BASE_DIR, "bin")
                os.makedirs(bin_dir, exist_ok=True)

                server_exe = os.path.join(bin_dir, "llama-server.exe")
                cuda_dll = os.path.join(bin_dir, "ggml-cuda.dll")

                engine_already_ready = False
                if backend == "cuda" and os.path.exists(server_exe) and os.path.exists(cuda_dll):
                    engine_already_ready = True
                elif backend == "cpu" and os.path.exists(server_exe):
                    engine_already_ready = True

                if engine_already_ready:
                    self.update_status("Verified local inference engine binaries in bin/...", 0.75)
                else:
                    self.update_status("Fetching llama.cpp binaries from GitHub...", 0.5)
                    headers = {"User-Agent": "Dot-Setup-Wizard/1.0"}
                    res = requests.get("https://api.github.com/repos/ggml-org/llama.cpp/releases", headers=headers, params={"per_page": 8}, timeout=15)
                    res.raise_for_status()

                    zip_urls = self.resolve_release_zips(res.json(), backend)
                    for i, url in enumerate(zip_urls):
                        self.update_status(f"Downloading engine archive ({i+1}/{len(zip_urls)})...", 0.55 + (i * 0.15))
                        z_res = requests.get(url, stream=True, timeout=60)
                        z_res.raise_for_status()
                        with zipfile.ZipFile(io.BytesIO(z_res.content)) as zf:
                            zf.extractall(bin_dir)

                # Post-install engine verification
                if not os.path.exists(server_exe):
                    raise RuntimeError("llama-server.exe was not found in bin/ after installation.")
                if backend == "cuda" and not os.path.exists(cuda_dll):
                    raise RuntimeError("CUDA Acceleration Error: ggml-cuda.dll was not found in bin/. GPU offload requires CUDA binaries.")

                # Quick pre-flight test to verify DLL linkage
                try:
                    t_res = subprocess.run([server_exe, "--version"], cwd=bin_dir, capture_output=True, text=True, timeout=10)
                    if t_res.returncode != 0:
                        log_error(f"llama-server test returned code {t_res.returncode}: {t_res.stderr}")
                except Exception as test_err:
                    log_error(f"llama-server preflight test warning: {test_err}")

            # 5. Finalize
            self.update_status("Writing configuration and generating launcher...", 0.9)
            self.finalize_setup()
            self.update_status("Setup Complete!", 1.0)
            self.after(0, self.show_success_screen)

        except Exception as e:
            log_error(f"Installation worker failed: {e}")
            self.after(0, lambda: self.show_fatal_error_screen(f"Installation failed: {e}"))

    def resolve_release_zips(self, releases, backend):
        for release in releases:
            assets = release.get("assets", [])
            if backend == "cpu":
                cpu_url = next(
                    (a["browser_download_url"] for a in assets
                     if "win" in a["name"].lower() and "x64.zip" in a["name"].lower() and ("cpu" in a["name"].lower() or "avx2" in a["name"].lower())),
                    None
                )
                if cpu_url:
                    return [cpu_url]
                continue

            # CUDA backend matching:
            # Pair the main CUDA server binary (llama-b*-bin-win-cuda-*.zip)
            # with the CUDA runtime library archive (cudart-llama-bin-win-cuda-*.zip)
            candidates = {}
            for a in assets:
                name = a["name"].lower()
                if "cuda" in name and "win" in name and "x64.zip" in name:
                    m = re.search(r"cuda-?(?:cu)?(\d+(?:\.\d+)*)", name)
                    if not m:
                        continue
                    parts = m.group(1).split(".")
                    ver = float(f"{parts[0]}.{parts[1]}") if len(parts) > 1 else float(parts[0])
                    if ver > self.cuda_version:
                        continue
                    if ver not in candidates:
                        candidates[ver] = {}
                    if name.startswith("cudart"):
                        candidates[ver]["cudart"] = a["browser_download_url"]
                    else:
                        candidates[ver]["bin"] = a["browser_download_url"]

            sorted_vers = sorted(candidates.keys(), reverse=True)
            for ver in sorted_vers:
                c = candidates[ver]
                if "bin" in c:
                    res = [c["bin"]]
                    if "cudart" in c:
                        res.append(c["cudart"])
                    return res

        raise ValueError(f"Could not find compatible llama.cpp Windows binaries for {backend.upper()} (CUDA max {self.cuda_version}) in recent releases.")

    # ----------------------------------------------------
    # STEP 6: FINALIZE & LAUNCHER SCRIPT
    # ----------------------------------------------------
    def finalize_setup(self):
        backend = self.backend_var.get()
        tier = "cloud" if backend == "cloud" else self.tier_var.get()

        self.config["active_settings"].update({
            "backend": backend,
            "selected_tier": tier,
            "user_name": self.user_name_var.get().strip() or "User",
            "gpu_layers": self.layers_var.get() if backend == "cuda" else 0
        })

        if backend == "cloud":
            provider_key = next((k for k, v in CLOUD_PROVIDERS.items() if v["label"] == self.provider_var.get()), "custom")
            self.config["cloud"] = {
                "provider": provider_key,
                "base_url": self.base_url_var.get().strip(),
                "model": self.model_var.get().strip(),
                "api_key": self.api_key_var.get().strip()
            }

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=4)

        # Write GitHub Token to .env files
        gh_token = self.github_token_var.get().strip()
        env_content = f'GITHUB_TOKEN="{gh_token}"\n'
        for env_path in [os.path.join(BASE_DIR, "dum-e", "src", "dot", ".env"), os.path.join(BASE_DIR, "dum-e", ".env")]:
            try:
                os.makedirs(os.path.dirname(env_path), exist_ok=True)
                with open(env_path, "w", encoding="utf-8") as f:
                    f.write(env_content)
            except Exception as e:
                log_error(f"Warning: Failed to write {env_path}: {e}")

        # Build start_dot.bat
        orchestrator_cmd = "cd dum-e && python -m uvicorn server:app --port 3000"
        frontend_cmd = "cd dum-e && npx @neutralinojs/neu run"

        engine_block = ""
        if backend != "cloud":
            active_model = self.config["models"][tier]
            gpu_flag = f"-ngl {self.layers_var.get()}" if backend == "cuda" else ""
            port = self.config["active_settings"].get("port", 11434)
            llama_cmd = f"llama-server.exe -m {active_model['filename']} --mmproj {active_model['mmproj']} --port {port} -c {active_model.get('context_size', 8192)} -fa on {gpu_flag} --temp 0.0 --alias dot-engine"

            engine_block = f"""echo [1/3] Starting Local Inference Engine ({backend.upper()})...
if not exist "bin\\llama-server.exe" (
    echo [ERROR] bin\\llama-server.exe was not found! Please run setup.py first.
    pause
    exit /b 1
)
cd bin
start "Dot Inference Engine" cmd /k "{llama_cmd}"
cd ..

<nul set /p =[1/3] Waiting for engine on port {port} 
set ENGINE_RETRIES=0
:WAIT_ENGINE
powershell -Command "try {{ $null = (New-Object Net.Sockets.TcpClient('127.0.0.1', {port})).Close(); exit 0 }} catch {{ exit 1 }}" >nul 2>&1
if errorlevel 1 (
    set /a ENGINE_RETRIES+=1
    if !ENGINE_RETRIES! geq 30 (
        echo  [FAILED]
        echo.
        echo [ERROR] Inference engine failed to start on port {port} within 60 seconds.
        echo Please inspect the "Dot Inference Engine" window for error details.
        pause
        exit /b 1
    )
    <nul set /p =.
    timeout /t 2 /nobreak >nul
    goto WAIT_ENGINE
)
echo  [DONE]
echo.
"""

        env_block = ""
        if backend == "cloud":
            env_block = f"""set DOT_CLOUD_API_KEY={self.config['cloud']['api_key']}
set DOT_CLOUD_BASE_URL={self.config['cloud']['base_url']}
set DOT_CLOUD_MODEL={self.config['cloud']['model']}
"""

        bat_content = f"""@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
{env_block}
:: Activate the virtual environment
call .venv\\Scripts\\activate.bat
if errorlevel 1 (
    echo [ERROR] Could not activate .venv. Run start_setup.bat first.
    pause
    exit /b 1
)

echo ========================================================
echo   Dot is starting up...
echo ========================================================
echo.
{engine_block}echo [2/3] Starting Python Orchestrator...
start "Dot Backend" cmd /k "call .venv\\Scripts\\activate.bat && cd dum-e && python -m uvicorn server:app --port 3000"

<nul set /p =[2/3] Waiting for orchestrator on port 3000 
set ORCH_RETRIES=0
:WAIT_ORCH
powershell -Command "try {{ $null = (New-Object Net.Sockets.TcpClient('127.0.0.1', 3000)).Close(); exit 0 }} catch {{ exit 1 }}" >nul 2>&1
if errorlevel 1 (
    set /a ORCH_RETRIES+=1
    if !ORCH_RETRIES! geq 30 (
        echo  [FAILED]
        echo.
        echo [ERROR] Orchestrator failed to start on port 3000 within 60 seconds.
        echo Check the Dot Backend window for error messages.
        pause
        exit /b 1
    )
    <nul set /p =.
    timeout /t 2 /nobreak >nul
    goto WAIT_ORCH
)
echo  [DONE]
echo.
echo [3/3] Launching Dot UI...
start "Dot Frontend" cmd /c "{frontend_cmd}"
echo.
echo ========================================================
echo   All systems go. Dot is ready.
echo ========================================================
echo   (You can close this window)
"""
        with open(os.path.join(BASE_DIR, "start_dot.bat"), "w", encoding="utf-8") as f:
            f.write(bat_content)

    # ----------------------------------------------------
    # SUCCESS & ERROR SCREENS
    # ----------------------------------------------------
    def show_success_screen(self):
        self.clear_container()
        ctk.CTkLabel(self.container, text="Installation Finished!", font=("Arial", 22, "bold"), text_color=COLOR_SUCCESS).pack(pady=(30, 15))
        tier = self.config["active_settings"]["selected_tier"]
        backend = self.config["active_settings"]["backend"].upper()

        summary = f"Configured Engine: {'Cloud (' + self.config['cloud']['provider'] + ')' if tier == 'cloud' else 'Gemma 4 (' + tier + ')'}\nHardware Backend: {backend}\nLauncher: start_dot.bat"
        ctk.CTkLabel(self.container, text=summary, font=("Arial", 14), text_color=COLOR_TEXT, justify="center").pack(pady=10)
        ctk.CTkButton(self.container, text="Finish & Exit", command=self.destroy, fg_color=COLOR_SUCCESS, hover_color=COLOR_SUCCESS_HOVER).pack(side="bottom", pady=25)

    def show_fatal_error_screen(self, msg):
        self.clear_container()
        ctk.CTkLabel(self.container, text="Setup Failed", font=("Arial", 22, "bold"), text_color=COLOR_ERROR).pack(pady=(30, 10))
        ctk.CTkLabel(self.container, text=msg, font=("Arial", 13), text_color=COLOR_TEXT, wraplength=500).pack(pady=10)
        ctk.CTkLabel(self.container, text=f"Crash details saved to: {LOG_FILE}", font=("Arial", 11), text_color=COLOR_TEXT_MUTED).pack(pady=10)
        ctk.CTkButton(self.container, text="Exit Setup", command=self.destroy, fg_color=COLOR_ERROR, hover_color=COLOR_ERROR_HOVER).pack(side="bottom", pady=20)


if __name__ == "__main__":
    try:
        app = DotInstaller()
        app.mainloop()
    except Exception as e:
        log_error(f"Fatal crash during setup mainloop: {e}")
        sys.exit(1)