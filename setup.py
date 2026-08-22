import customtkinter as ctk
import psutil
import subprocess
import os
import json
import threading
import requests
import zipfile
import io
import sys
import logging
import traceback
import re
import webbrowser
import shutil

def resource_path(relative_path):
    """Resolve path to a bundled resource (works both in dev and PyInstaller .exe)."""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)

def get_system_python():
    """Return the system Python interpreter path.
    Inside a PyInstaller bundle sys.executable is the frozen .exe,
    so we search PATH for the real Python instead."""
    if getattr(sys, 'frozen', False):
        for name in ("python", "py", "python3"):
            found = shutil.which(name)
            if found:
                return found
        raise FileNotFoundError(
            "Could not find a Python interpreter on your system PATH.\n"
            "Please install Python 3.10+ and ensure it is added to PATH."
        )
    return sys.executable

# ==========================================
# 1. LOGGING CONFIGURATION & GLOBAL HOOKS
# ==========================================
LOG_FILE = "error.log"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.ERROR,
    format="[%(asctime)s] %(levelname)s [%(filename)s:%(lineno)d] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def log_and_display_error(msg, exc_info=None):
    """Utility to write errors to error.log with full stack traces."""
    if exc_info:
        logging.error(msg, exc_info=exc_info)
    else:
        logging.exception(msg)

def global_exception_handler(exc_type, exc_value, exc_traceback):
    """Catch any unhandled exception on the main GUI thread."""
    logging.error("Unhandled main thread exception", exc_info=(exc_type, exc_value, exc_traceback))

def thread_exception_handler(args):
    """Catch any unhandled exception inside background worker threads."""
    logging.error("Unhandled worker thread exception", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

sys.excepthook = global_exception_handler
threading.excepthook = thread_exception_handler

# ==========================================
# 2. COLOR THEME — RED & BLACK
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

# ==========================================
# 3. CLOUD PROVIDER PRESETS
# ==========================================
# Only vendors with an OpenAI-compatible chat-completions endpoint belong here.
# "custom" covers anything else OpenAI-compatible (routers, proxies, self-hosted
# gateways, etc.) by letting the user type in their own base_url/model.
CLOUD_PROVIDERS = {
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini"
    },
    "gemini": {
        "label": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-3.7-flash"
    },
    "custom": {
        "label": "Custom / Other (OpenAI-compatible)",
        "base_url": "",
        "default_model": ""
    }
}

# ==========================================
# 4. SETUP WIZARD GUI CLASS
# ==========================================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")  # base theme; every widget below overrides its own colors

class DotInstaller(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Dot Setup & Rig Analyzer")
        self.geometry("620x580")
        self.resizable(False, False)
        self.configure(fg_color=COLOR_BG)

        self.config_path = "appconfig.json"
        self.config = {}
        self.has_cuda = False
        self.vram_gb = 0
        self.ram_gb = 0

        # Persisted wizard state so Back navigation doesn't lose input
        self._saved_user_details = {}

        # Load Master Configuration
        self.load_configuration()

        # Main Viewport Container
        self.container = ctk.CTkFrame(self, corner_radius=12, fg_color=COLOR_PANEL)
        self.container.pack(fill="both", expand=True, padx=20, pady=20)

        # Start at Step 1
        self.show_rig_analysis()

    def clear_container(self):
        for widget in self.container.winfo_children():
            widget.destroy()

    # ----------------------------------------------------
    # SHARED UI HELPERS
    # ----------------------------------------------------
    def get_step_sequence(self):
        """The wizard skips 'Compute Tier' and 'Model Files' entirely for the
        cloud backend, so the step count/labels are computed dynamically
        rather than hardcoded per screen."""
        if hasattr(self, 'backend_var') and self.backend_var.get() == "cloud":
            return ["Hardware", "Personalize", "Install"]
        return ["Hardware", "Compute Tier", "Model Files", "Personalize", "Install"]

    def make_step_label(self, current):
        seq = self.get_step_sequence()
        if current in seq:
            idx = seq.index(current) + 1
            text = f"STEP {idx} OF {len(seq)}  ·  {current.upper()}"
        else:
            text = current.upper()
        ctk.CTkLabel(
            self.container, text=text, font=("Arial", 11, "bold"), text_color=COLOR_ACCENT
        ).pack(pady=(15, 0))

    def make_nav_row(self, back_command, next_text, next_command, show_back=True):
        """Builds the shared bottom navigation row: Back (left) + primary action (right)."""
        nav_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        nav_frame.pack(side="bottom", fill="x", padx=30, pady=20)

        if show_back and back_command is not None:
            back_btn = ctk.CTkButton(
                nav_frame, text="< Back", command=back_command, width=110,
                fg_color=COLOR_BACK_BTN, hover_color=COLOR_BACK_BTN_HOVER, text_color=COLOR_TEXT
            )
            back_btn.pack(side="left")

        next_btn = ctk.CTkButton(
            nav_frame, text=next_text, command=next_command,
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, text_color=COLOR_TEXT
        )
        next_btn.pack(side="right")

    def show_fatal_error_screen(self, message):
        """Displays a clean error state to the user without crashing the window."""
        self.clear_container()
        ctk.CTkLabel(
            self.container,
            text="Setup Failed",
            font=("Arial", 22, "bold"),
            text_color=COLOR_ERROR
        ).pack(pady=(30, 10))

        ctk.CTkLabel(
            self.container,
            text=message,
            font=("Arial", 14),
            text_color=COLOR_TEXT,
            wraplength=500
        ).pack(pady=10)

        ctk.CTkLabel(
            self.container,
            text=f"A detailed crash report has been saved to: {LOG_FILE}",
            font=("Arial", 12),
            text_color=COLOR_TEXT_MUTED
        ).pack(pady=15)

        ctk.CTkButton(
            self.container,
            text="Exit Setup",
            command=self.destroy,
            fg_color=COLOR_ERROR,
            hover_color=COLOR_ERROR_HOVER
        ).pack(side="bottom", pady=20)

    # ----------------------------------------------------
    # CONFIG LOADER
    # ----------------------------------------------------
    def load_configuration(self):
        try:
            if not os.path.exists(self.config_path):
                raise FileNotFoundError(f"Configuration template '{self.config_path}' was not found in the current directory.")

            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)

            # Validate basic keys
            for key in ["backends", "models", "launcher_templates", "active_settings"]:
                if key not in self.config:
                    raise KeyError(f"Missing required configuration section: '{key}'")

            # Ensure the cloud config block always exists, even for older
            # config files that predate the dedicated cloud section.
            if "cloud" not in self.config:
                self.config["cloud"] = {
                    "provider": "openai",
                    "base_url": CLOUD_PROVIDERS["openai"]["base_url"],
                    "model": CLOUD_PROVIDERS["openai"]["default_model"],
                    "api_key": ""
                }

        except Exception:
            log_and_display_error("Failed to load or parse appconfig.json during initialization")
            # Defer showing fatal error until container is mounted
            self.after(100, lambda: self.show_fatal_error_screen("Could not read appconfig.json. Please ensure the file exists and is valid JSON."))

    # ----------------------------------------------------
    # STEP 1: RIG ANALYSIS & HARDWARE PROBING
    # ----------------------------------------------------
    def show_rig_analysis(self):
        if not self.config:
            return

        self.clear_container()
        self.make_step_label("Hardware")
        ctk.CTkLabel(self.container, text="Hardware Analysis", font=("Arial", 22, "bold"), text_color=COLOR_TEXT).pack(pady=(5, 10))

        self.cuda_version = 0.0  # Default fallback
        self.vram_gb = 0
        self.has_cuda = False

        # 1. Probe System RAM
        try:
            self.ram_gb = round(psutil.virtual_memory().total / (1024**3), 1)
        except Exception:
            self.ram_gb = 8.0

        # 2. Probe NVIDIA GPU VRAM (Isolated Check)
        try:
            vram_output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                encoding="utf-8",
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)  # Prevents cmd popups on Windows
            )
            self.vram_gb = round(int(vram_output.strip().split("\n")[0]) / 1024, 1)
            self.has_cuda = True
        except Exception:
            self.has_cuda = False

        # 3. Probe Max Supported CUDA Version (Isolated Check)
        if self.has_cuda:
            try:
                full_output = subprocess.check_output(
                    ["nvidia-smi"],
                    encoding="utf-8",
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                )
                # Broader regex to safely catch "12", "12.4", or "12.4.1"
                match = re.search(r"CUDA\s+(?:UMD\s+)?Version:\s*(\d+(?:\.\d+)?)", full_output, re.IGNORECASE)
                if match:
                    self.cuda_version = float(match.group(1))
                else:
                    self.cuda_version = 11.0  # Safe fallback if driver text format changes
            except Exception:
                self.cuda_version = 11.0  # Safe fallback if command fails

        # 4. UI Status Display
        info_frame = ctk.CTkFrame(self.container, fg_color=COLOR_PANEL_ALT)
        info_frame.pack(fill="x", padx=30, pady=10)

        # Dynamic string based on what the probes found
        gpu_status = f"NVIDIA GPU ({self.vram_gb} GB VRAM) - CUDA v{self.cuda_version}" if self.has_cuda else "No NVIDIA GPU (CPU Mode)"

        ctk.CTkLabel(info_frame, text=f"• System Memory: {self.ram_gb} GB RAM", font=("Arial", 14), text_color=COLOR_TEXT).pack(anchor="w", padx=20, pady=(10, 4))
        ctk.CTkLabel(info_frame, text=f"• Graphics Backend: {gpu_status}", font=("Arial", 14), text_color=COLOR_TEXT).pack(anchor="w", padx=20, pady=(0, 10))

        # 5. Backend Selector
        ctk.CTkLabel(self.container, text="Select Compute Engine:", font=("Arial", 14, "bold"), text_color=COLOR_TEXT).pack(pady=(10, 5))

        # Only set a default the first time this screen is shown, so going
        # Back here later preserves whatever the user had picked before.
        if not hasattr(self, 'backend_var'):
            self.backend_var = ctk.StringVar(value="cuda" if self.has_cuda else "cpu")

        radio_kwargs = dict(fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, text_color=COLOR_TEXT, border_color=COLOR_TEXT_MUTED)

        # Option 1: CUDA
        r_cuda = ctk.CTkRadioButton(self.container, text="CUDA (NVIDIA GPU Acceleration — Recommended)", variable=self.backend_var, value="cuda", **radio_kwargs)
        r_cuda.pack(pady=4, anchor="w", padx=40)
        if not self.has_cuda:
            r_cuda.configure(state="disabled")

        # Option 2: CPU
        r_cpu = ctk.CTkRadioButton(self.container, text="AVX2 (CPU Only — Standard Fallback)", variable=self.backend_var, value="cpu", **radio_kwargs)
        r_cpu.pack(pady=4, anchor="w", padx=40)

        # Option 3: Cloud
        r_cloud = ctk.CTkRadioButton(self.container, text="Cloud API (Fully Remote — Zero Local Downloads)", variable=self.backend_var, value="cloud", **radio_kwargs)
        r_cloud.pack(pady=4, anchor="w", padx=40)

        # First step — no Back button.
        self.make_nav_row(back_command=None, next_text="Continue to Tier Selection", next_command=self.show_model_selection, show_back=False)

    # ----------------------------------------------------
    # STEP 2: MODEL SELECTION
    # ----------------------------------------------------
    def show_model_selection(self):
        if hasattr(self, 'backend_var') and self.backend_var.get() == "cloud":
            self.show_user_details()
            return
        self.clear_container()
        self.make_step_label("Compute Tier")
        ctk.CTkLabel(self.container, text="Select Model", font=("Arial", 22, "bold"), text_color=COLOR_TEXT).pack(pady=(5, 10))

        # Determine Recommendation
        recommended = "2B"
        if self.vram_gb >= 12 or self.ram_gb >= 32:
            recommended = "12B"
        elif self.vram_gb >= 6 or self.ram_gb >= 16:
            recommended = "4B"

        ctk.CTkLabel(
            self.container,
            text=f"Recommended for your setup: Gemma 4 ({recommended})",
            font=("Arial", 13, "bold"),
            text_color=COLOR_ACCENT
        ).pack(pady=(0, 15))

        # Only set a default the first time, so Back preserves the pick.
        if not hasattr(self, 'tier_var'):
            self.tier_var = ctk.StringVar(value=recommended if recommended in self.config["models"] else "4B")

        # 2. Dynamically Generate Radio Buttons from appconfig.json
        for tier, details in self.config.get("models", {}).items():
            context = details.get("context_size", 8192)
            desc = f"Gemma 4 ({tier})"

            ctk.CTkRadioButton(
                self.container, text=desc, variable=self.tier_var, value=tier,
                fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, text_color=COLOR_TEXT, border_color=COLOR_TEXT_MUTED
            ).pack(pady=8, anchor="w", padx=60)

        self.make_nav_row(back_command=self.show_rig_analysis, next_text="Next: Model Files", next_command=self.show_model_files)

    # ----------------------------------------------------
    # STEP 3: MODEL FILE ACQUISITION (manual — gated on Hugging Face)
    # ----------------------------------------------------
    def show_model_files(self):
        self.clear_container()
        self.make_step_label("Model Files")
        ctk.CTkLabel(self.container, text="Download Model Files", font=("Arial", 22, "bold"), text_color=COLOR_TEXT).pack(pady=(5, 10))

        tier = self.tier_var.get()
        model_info = self.config["models"][tier]
        repo_id = model_info["repo_id"]
        model_filename = model_info["filename"]
        mmproj_filename = model_info["mmproj"]

        page_url = f"https://huggingface.co/{repo_id}"

        os.makedirs("bin", exist_ok=True)
        bin_dir = os.path.abspath("bin")
        short_path = os.path.join(os.path.basename(os.path.dirname(bin_dir)), "bin")

        ctk.CTkLabel(
            self.container,
            text=(
                f"Gemma 4 ({tier}) is gated on Hugging Face and can't be downloaded automatically.\n"
                "1. Open the model page and log in to accept the license.\n"
                "2. Download both files below from that page.\n"
                "3. Place them directly inside the folder shown at the bottom, then check again."
            ),
            font=("Arial", 12), text_color=COLOR_TEXT_MUTED, justify="left", wraplength=520
        ).pack(anchor="w", padx=30, pady=(0, 8))

        ctk.CTkButton(
            self.container, text="Open Model Page", width=200,
            command=lambda: webbrowser.open(page_url),
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, text_color=COLOR_TEXT
        ).pack(anchor="w", padx=30, pady=(0, 12))

        files_frame = ctk.CTkFrame(self.container, fg_color=COLOR_PANEL_ALT)
        files_frame.pack(fill="x", padx=30, pady=(0, 10))

        self.model_status_labels = {}

        def add_file_row(label_text, filename):
            row = ctk.CTkFrame(files_frame, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=8)

            ctk.CTkLabel(row, text=label_text, font=("Arial", 13, "bold"), text_color=COLOR_TEXT).pack(anchor="w")

            name_row = ctk.CTkFrame(row, fg_color="transparent")
            name_row.pack(fill="x")
            ctk.CTkLabel(name_row, text=filename, font=("Arial", 11), text_color=COLOR_TEXT_MUTED).pack(side="left")

            status_label = ctk.CTkLabel(name_row, text="Not found", font=("Arial", 12, "bold"), text_color=COLOR_ERROR)
            status_label.pack(side="left", padx=15)
            self.model_status_labels[filename] = status_label

        add_file_row("Main Model (GGUF)", model_filename)
        add_file_row("Vision Projector (mmproj)", mmproj_filename)

        path_row = ctk.CTkFrame(self.container, fg_color="transparent")
        path_row.pack(fill="x", padx=30, pady=(5, 5))
        ctk.CTkLabel(path_row, text=f"Place files in: {short_path}", font=("Arial", 12), text_color=COLOR_TEXT).pack(side="left")
        ctk.CTkButton(
            path_row, text="Open Folder", width=110,
            command=lambda: self._open_folder(bin_dir),
            fg_color=COLOR_BACK_BTN, hover_color=COLOR_BACK_BTN_HOVER, text_color=COLOR_TEXT
        ).pack(side="right")

        self.model_files_error = ctk.CTkLabel(self.container, text="", font=("Arial", 12), text_color=COLOR_ERROR, wraplength=520)
        self.model_files_error.pack(pady=(5, 0))

        # Check immediately in case the files are already there from a previous run.
        self._refresh_model_file_status(model_filename, mmproj_filename)

        def on_continue():
            found = self._refresh_model_file_status(model_filename, mmproj_filename)
            if found:
                self.model_files_error.configure(text="")
                self.show_user_details()
            else:
                self.model_files_error.configure(text="Both files must be present in the folder above before continuing.")

        self.make_nav_row(back_command=self.show_model_selection, next_text="Check & Continue", next_command=on_continue)

    def _refresh_model_file_status(self, model_filename, mmproj_filename):
        """Updates the Found/Not found labels in place and returns True only
        if both files are present and non-trivial in size."""
        all_found = True
        for filename in (model_filename, mmproj_filename):
            path = os.path.join("bin", filename)
            present = os.path.exists(path) and os.path.getsize(path) > 1024 * 1024
            label = self.model_status_labels.get(filename)
            if label:
                label.configure(text="Found" if present else "Not found", text_color=COLOR_SUCCESS if present else COLOR_ERROR)
            all_found = all_found and present
        return all_found

    def _open_folder(self, path):
        try:
            os.startfile(path)
        except Exception:
            log_and_display_error(f"Failed to open folder: {path}")

    # ----------------------------------------------------
    # STEP 4: USER DETAILS & CLOUD CONFIGURATION
    # ----------------------------------------------------
    def show_user_details(self):
        self.clear_container()
        self.make_step_label("Personalize")
        ctk.CTkLabel(self.container, text="Personalize Assistant", font=("Arial", 22, "bold"), text_color=COLOR_TEXT).pack(pady=(5, 15))

        saved = self._saved_user_details

        entry_kwargs = dict(fg_color=COLOR_PANEL_ALT, border_color=COLOR_ACCENT_MUTED, text_color=COLOR_TEXT)

        # Text Inputs
        ctk.CTkLabel(self.container, text="User Name / Call Sign:", font=("Arial", 13), text_color=COLOR_TEXT).pack(anchor="w", padx=40, pady=(5, 2))
        self.name_entry = ctk.CTkEntry(self.container, placeholder_text="e.g. Vishnu", width=340, **entry_kwargs)
        if saved.get("name"):
            self.name_entry.insert(0, saved["name"])
        self.name_entry.pack(padx=40, pady=(0, 10))

        is_cloud = hasattr(self, 'backend_var') and self.backend_var.get() == "cloud"

        # These only get created (and only get read later) when the cloud
        # backend was actually chosen. Local backends never touch cloud
        # fields at all — there is no "optional fallback" path.
        self.provider_var = None
        self.base_url_entry = None
        self.model_entry = None
        self.api_entry = None

        if is_cloud:
            default_provider_label = saved.get("provider_label", CLOUD_PROVIDERS["openai"]["label"])
            default_base_url = saved.get("base_url", CLOUD_PROVIDERS["openai"]["base_url"])
            default_model = saved.get("model", CLOUD_PROVIDERS["openai"]["default_model"])

            # Provider dropdown
            ctk.CTkLabel(self.container, text="Cloud Provider:", font=("Arial", 13), text_color=COLOR_TEXT).pack(anchor="w", padx=40, pady=(5, 2))
            provider_labels = [p["label"] for p in CLOUD_PROVIDERS.values()]
            self.provider_var = ctk.StringVar(value=default_provider_label)
            provider_menu = ctk.CTkOptionMenu(
                self.container, values=provider_labels, variable=self.provider_var,
                width=340, command=self._on_provider_change,
                fg_color=COLOR_PANEL_ALT, button_color=COLOR_ACCENT, button_hover_color=COLOR_ACCENT_HOVER,
                dropdown_fg_color=COLOR_PANEL, text_color=COLOR_TEXT
            )
            provider_menu.pack(padx=40, pady=(0, 10))

            # Base URL (auto-filled by provider, editable)
            ctk.CTkLabel(self.container, text="Base URL:", font=("Arial", 13), text_color=COLOR_TEXT).pack(anchor="w", padx=40, pady=(5, 2))
            self.base_url_entry = ctk.CTkEntry(self.container, width=340, **entry_kwargs)
            self.base_url_entry.insert(0, default_base_url)
            self.base_url_entry.pack(padx=40, pady=(0, 10))

            # Model name (auto-filled by provider, editable)
            ctk.CTkLabel(self.container, text="Model:", font=("Arial", 13), text_color=COLOR_TEXT).pack(anchor="w", padx=40, pady=(5, 2))
            self.model_entry = ctk.CTkEntry(self.container, width=340, **entry_kwargs)
            self.model_entry.insert(0, default_model)
            self.model_entry.pack(padx=40, pady=(0, 10))

            # API key
            ctk.CTkLabel(self.container, text="Cloud API Key:", font=("Arial", 13), text_color=COLOR_TEXT).pack(anchor="w", padx=40, pady=(5, 2))
            self.api_entry = ctk.CTkEntry(self.container, placeholder_text="Required: Enter Cloud API Key", width=340, show="*", **entry_kwargs)
            if saved.get("api_key"):
                self.api_entry.insert(0, saved["api_key"])
            self.api_entry.pack(padx=40, pady=(0, 15))

        # GPU Layers Slider (Only render if CUDA was selected)
        if hasattr(self, 'backend_var') and self.backend_var.get() == "cuda":
            ctk.CTkLabel(self.container, text="GPU Offload Layers (Advanced):", font=("Arial", 13), text_color=COLOR_TEXT).pack(anchor="w", padx=40, pady=(5, 2))

            if not hasattr(self, 'layers_var'):
                self.layers_var = ctk.IntVar(value=99)

            def update_layers_label(value):
                val = int(value)
                status = " (Max Offload)" if val == 99 else " (CPU Only)" if val == 0 else " (Partial Offload)"
                self.layers_label.configure(text=f"{val} Layers{status}")

            self.layers_slider = ctk.CTkSlider(
                self.container, from_=0, to=99, number_of_steps=99, variable=self.layers_var,
                command=update_layers_label, width=340,
                progress_color=COLOR_ACCENT, button_color=COLOR_ACCENT, button_hover_color=COLOR_ACCENT_HOVER
            )
            self.layers_slider.pack(padx=40, pady=(0, 5))

            self.layers_label = ctk.CTkLabel(self.container, text=f"{self.layers_var.get()} Layers", font=("Arial", 12), text_color=COLOR_TEXT_MUTED)
            self.layers_label.pack(pady=(0, 10))
            update_layers_label(self.layers_var.get())

        self.make_nav_row(back_command=self._back_from_user_details, next_text="Start Installation", next_command=self.start_installation)

    def _on_provider_change(self, selected_label):
        """Auto-fill base_url/model when the user switches providers, without
        clobbering anything they've already typed by hand for 'custom'."""
        for key, info in CLOUD_PROVIDERS.items():
            if info["label"] == selected_label:
                self.base_url_entry.delete(0, "end")
                self.base_url_entry.insert(0, info["base_url"])
                self.model_entry.delete(0, "end")
                self.model_entry.insert(0, info["default_model"])
                break

    def _capture_user_details_state(self):
        """Snapshots the current form values so Back/Forward navigation
        doesn't lose anything the user already typed."""
        state = {"name": self.name_entry.get().strip() if self.name_entry else ""}
        if self.provider_var:
            state["provider_label"] = self.provider_var.get()
        if self.base_url_entry:
            state["base_url"] = self.base_url_entry.get().strip()
        if self.model_entry:
            state["model"] = self.model_entry.get().strip()
        if self.api_entry:
            state["api_key"] = self.api_entry.get().strip()
        self._saved_user_details = state

    def _back_from_user_details(self):
        self._capture_user_details_state()
        if hasattr(self, 'backend_var') and self.backend_var.get() == "cloud":
            # Cloud skips tier selection and model files on the way forward, so skip them going back too.
            self.show_rig_analysis()
        else:
            self.show_model_files()

    # ----------------------------------------------------
    # STEP 5: THREADED DOWNLOAD & EXTRACTION
    # ----------------------------------------------------
    def start_installation(self):
        try:
            self._capture_user_details_state()

            is_cloud = self.backend_var.get() == "cloud"
            api_key = self.api_entry.get().strip() if self.api_entry else ""

            # Form Validation: Reject if Cloud mode but no key
            if is_cloud and not api_key:
                self.api_entry.configure(border_color=COLOR_ERROR)  # Flash red
                return

            name = self.name_entry.get().strip()
            self.config["active_settings"]["user_name"] = name if name else "User"
            self.config["active_settings"]["backend"] = self.backend_var.get()

            if is_cloud:
                self.config["active_settings"]["selected_tier"] = "cloud"
                self.config["active_settings"]["gpu_layers"] = 0

                selected_label = self.provider_var.get()
                provider_key = next(
                    (k for k, v in CLOUD_PROVIDERS.items() if v["label"] == selected_label),
                    "custom"
                )
                self.config["cloud"]["provider"] = provider_key
                self.config["cloud"]["base_url"] = self.base_url_entry.get().strip()
                self.config["cloud"]["model"] = self.model_entry.get().strip()
                self.config["cloud"]["api_key"] = api_key
            else:
                self.config["active_settings"]["selected_tier"] = self.tier_var.get()
                self.config["active_settings"]["gpu_layers"] = self.layers_var.get() if self.backend_var.get() == "cuda" else 0

        except Exception:
            log_and_display_error("Error collecting user inputs from form")
            self.show_fatal_error_screen("Failed to process form entries.")
            return

        self.clear_container()
        self.make_step_label("Install")
        ctk.CTkLabel(self.container, text="Installing Components...", font=("Arial", 22, "bold"), text_color=COLOR_TEXT).pack(pady=(10, 10))

        self.progress = ctk.CTkProgressBar(self.container, width=420, progress_color=COLOR_ACCENT)
        self.progress.pack(pady=20)
        self.progress.set(0)

        self.status_label = ctk.CTkLabel(self.container, text="Initializing download pipeline...", font=("Arial", 13), text_color=COLOR_TEXT)
        self.status_label.pack(pady=10)

        # Execute heavy IO inside isolated thread
        threading.Thread(target=self.download_and_extract_worker, daemon=True).start()

    def update_status(self, text, progress_val=None):
        """Thread-safe UI status update."""
        self.after(0, lambda: self.status_label.configure(text=text))
        if progress_val is not None:
            self.after(0, lambda: self.progress.set(progress_val))

    def get_dynamic_release_urls(self, backend_choice):
        """Finds the correct engine ZIPs for the chosen backend, walking
        backward through recent releases in case the newest tag is missing a
        Windows asset (llama.cpp's CI occasionally fails to publish specific
        platform builds for a given release).

        Matching is done by a positive check for "cpu" in the filename
        (the current unified engine package, e.g.
        llama-b10423-bin-win-cpu-x64.zip) rather than by excluding every
        known accelerator tag, since new backend zips get added over time
        and a blacklist silently rots.
        """
        releases_url = "https://api.github.com/repos/ggml-org/llama.cpp/releases"
        response = requests.get(releases_url, params={"per_page": 8}, timeout=15)
        response.raise_for_status()
        releases = response.json()

        if not releases:
            raise ValueError(
                "GitHub returned no llama.cpp releases at all. This usually means "
                "you've hit GitHub's unauthenticated API rate limit (60 req/hr) — "
                "wait a while and try again."
            )

        last_seen_names = []

        for release in releases:
            assets = release.get("assets", [])
            if assets:
                last_seen_names = [a["name"] for a in assets]

            # Positive match for the base/unified engine package.
            cpu_exe_url = ""
            for asset in assets:
                name = asset["name"].lower()
                if "win" in name and "x64.zip" in name and "cpu" in name:
                    cpu_exe_url = asset["browser_download_url"]
                    break

            if not cpu_exe_url:
                continue  # this release's Windows CPU build is missing/broken — try an older one

            if backend_choice == "cpu":
                return [cpu_exe_url]

            # CUDA path: also need a matching cuda backend/runtime zip for this driver.
            highest_version = 0.0
            dll_url = ""
            for asset in assets:
                name = asset["name"].lower()
                if "cuda" in name and "win" in name and "x64.zip" in name:
                    match = re.search(r'cuda-?(\d+(?:\.\d+)?)', name)
                    if match:
                        asset_version = float(match.group(1))
                        if asset_version <= self.cuda_version and asset_version > highest_version:
                            highest_version = asset_version
                            dll_url = asset["browser_download_url"]

            if dll_url:
                self.update_status(f"Found Unified Engine + CUDA v{highest_version} DLLs...", 0.05)
                return [cpu_exe_url, dll_url]
            # cpu engine found but no compatible cuda package in this release — keep trying older ones

        available = ", ".join(last_seen_names) if last_seen_names else "(none)"
        raise ValueError(
            f"Could not find a compatible Windows '{backend_choice}' build across the last "
            f"{len(releases)} llama.cpp releases. Assets in the most recent release: {available}"
        )

    def verify_model_files_present(self, model_dest, mmproj_dest, tier):
        """Defense-in-depth check before install — the wizard's Model Files
        step already verifies this, but a user could delete/move the files
        in between, so we check again right before we need them."""
        missing = [p for p in (model_dest, mmproj_dest) if not os.path.exists(p) or os.path.getsize(p) < 1024 * 1024]
        if missing:
            names = "\n".join(f"  - {os.path.basename(p)}" for p in missing)
            raise ValueError(
                f"Missing model file(s) for the {tier} tier in bin/:\n{names}\n\n"
                "Go back to the Model Files step and make sure both files are placed in the bin folder."
            )

    def download_and_extract_worker(self):
        try:
            # 0. Install Python dependencies from the bundled requirements.txt
            req_path = resource_path("requirements.txt")
            if os.path.exists(req_path):
                self.update_status("Installing Python dependencies (this may take a while)...", 0.02)
                python_exe = get_system_python()
                result = subprocess.run(
                    [python_exe, "-m", "pip", "install", "-r", req_path, "--quiet"],
                    capture_output=True, text=True,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                )
                if result.returncode != 0:
                    raise RuntimeError(
                        f"pip install failed:\n{result.stderr.strip() or result.stdout.strip()}"
                    )

            backend_choice = self.config["active_settings"]["backend"]
            if backend_choice == "cloud":
                self.update_status("Cloud environment selected. Skipping local downloads...", 0.5)
                self.update_status("Generating launcher scripts...", 0.95)
                self.finalize_setup()
                self.update_status("Setup Complete! Cloud backend configured.", 1.0)
                self.after(0, self.show_success_screen)
                return
            tier = self.config["active_settings"]["selected_tier"]
            active_model = self.config["models"][tier]

            os.makedirs("bin", exist_ok=True)

            # 1. Download & Extract llama.cpp (Handles both Exe + DLL zips)
            zip_urls = self.get_dynamic_release_urls(backend_choice)

            for i, zip_url in enumerate(zip_urls):
                self.update_status(f"Downloading engine archive {i+1} of {len(zip_urls)}...", 0.05 + (i * 0.1))

                response = requests.get(zip_url, stream=True, timeout=30)
                response.raise_for_status()

                zip_buffer = io.BytesIO()
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        zip_buffer.write(chunk)

                with zipfile.ZipFile(zip_buffer) as zip_ref:
                    zip_ref.extractall("bin")

            # 2. Model files are gated on Hugging Face and can't be fetched
            # automatically — the wizard's "Model Files" step already had the
            # user place them in bin/. Re-verify they're still there.
            model_filename = active_model["filename"]
            mmproj_filename = active_model["mmproj"]
            model_dest = os.path.join("bin", model_filename)
            mmproj_dest = os.path.join("bin", mmproj_filename)

            self.update_status("Verifying model files...", 0.85)
            self.verify_model_files_present(model_dest, mmproj_dest, tier)

            # 3. Finalize Scripts and Configuration
            self.update_status("Generating launcher scripts...", 0.95)
            self.finalize_setup()

            self.update_status("Setup Complete! Binaries extracted and configured.", 1.0)
            self.after(0, self.show_success_screen)

        except Exception as e:
            # Capture error string immediately to prevent Tkinter scoping deletion
            error_message = str(e)
            log_and_display_error("Unexpected error in download and extraction thread", exc_info=True)
            self.after(0, lambda msg=error_message: self.show_fatal_error_screen(f"Installation failed: {msg}"))

    # ----------------------------------------------------
    # STEP 6: CONFIG WRITING & SCRIPT GENERATION
    # ----------------------------------------------------
    def finalize_setup(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4)
        except Exception:
            log_and_display_error(f"Failed to write updated settings back to {self.config_path}")
            raise

        try:
            backend = self.config["active_settings"]["backend"]
            templates = self.config.get("launcher_templates", {})
            orchestrator_cmd = templates.get("orchestrator", "python src/dot/engine.py")
            frontend_cmd = templates.get("frontend", "neutralino-win_x64.exe")

            if backend == "cloud":
                # Cloud Launcher - Skips Local Inference Engine entirely.
                # Cloud credentials are exported as env vars so the
                # orchestrator (client.py) can pick them up as a backup to
                # reading them straight out of appconfig.json.
                cloud_cfg = self.config.get("cloud", {})
                bat_content = f"""@echo off
set DOT_CLOUD_API_KEY={cloud_cfg.get("api_key", "")}
set DOT_CLOUD_BASE_URL={cloud_cfg.get("base_url", "")}
set DOT_CLOUD_MODEL={cloud_cfg.get("model", "")}

echo ========================================================
echo   Dot is starting up — please wait...
echo ========================================================
echo.
echo [1/2] Starting Python Orchestrator (Cloud Engine)...
start "" /min cmd /c "{orchestrator_cmd}"

<nul set /p =[1/2] Waiting for orchestrator 
:WAIT_ORCH
powershell -Command "try {{ $null = (New-Object Net.Sockets.TcpClient('127.0.0.1', 3000)).Close(); exit 0 }} catch {{ exit 1 }}" >nul 2>&1
if errorlevel 1 (
    <nul set /p =.
    timeout /t 2 /nobreak >nul
    goto WAIT_ORCH
)
echo  [DONE]

echo [2/2] Launching Dot UI...
start "" /min cmd /c "{frontend_cmd}"
echo.
echo ========================================================
echo   All systems go! Dot is ready.
echo ========================================================
echo   (You can close this window)
"""
            else:
                # Local Launcher (Existing logic)
                tier = self.config["active_settings"]["selected_tier"]
                active_model = self.config["models"][tier]
                settings = self.config["active_settings"]

                if backend in templates:
                    cmd_template = templates[backend]
                elif "llama_server" in templates:
                    cmd_template = templates["llama_server"]
                else:
                    gpu_flag = "-ngl {gpu_layers}" if backend == "cuda" else ""
                    cmd_template = f"llama-server.exe -m {{model_file}} --mmproj {{mmproj_file}} --port {{port}} -c {{context_size}} -fa on {gpu_flag} --temp {{temperature}} --alias dot-engine"

                llama_cmd = cmd_template.format(
                    model_file=active_model["filename"],
                    mmproj_file=active_model["mmproj"],
                    port=settings.get("port", 11434),
                    context_size=settings.get("context_size", 8192),
                    temperature=settings.get("temperature", 0.0),
                    gpu_layers=settings.get("gpu_layers", 99)
                )

                port = settings.get("port", 11434)
                bat_content = f"""@echo off
echo ========================================================
echo   Dot is starting up — please wait...
echo ========================================================
echo.
echo [1/3] Starting Local Inference Engine ({backend.upper()})...
cd bin
start "" /min cmd /c "{llama_cmd}"
cd ..

<nul set /p =[1/3] Waiting for engine on port {port} 
:WAIT_ENGINE
powershell -Command "try {{ $null = (New-Object Net.Sockets.TcpClient('127.0.0.1', {port})).Close(); exit 0 }} catch {{ exit 1 }}" >nul 2>&1
if errorlevel 1 (
    <nul set /p =.
    timeout /t 2 /nobreak >nul
    goto WAIT_ENGINE
)
echo  [DONE]

echo [2/3] Starting Python Orchestrator...
start "" /min cmd /c "{orchestrator_cmd}"

<nul set /p =[2/3] Waiting for orchestrator on port 3000 
:WAIT_ORCH
powershell -Command "try {{ $null = (New-Object Net.Sockets.TcpClient('127.0.0.1', 3000)).Close(); exit 0 }} catch {{ exit 1 }}" >nul 2>&1
if errorlevel 1 (
    <nul set /p =.
    timeout /t 2 /nobreak >nul
    goto WAIT_ORCH
)
echo  [DONE]

echo [3/3] Launching Dot UI...
start "" /min cmd /c "{frontend_cmd}"
echo.
echo ========================================================
echo   All systems go! Dot is ready.
echo ========================================================
echo   (You can close this window)
"""
            with open("start_dot.bat", "w", encoding="utf-8") as f:
                f.write(bat_content)

        except Exception:
            log_and_display_error("Failed to generate start_dot.bat script", exc_info=True)
            raise

    def show_success_screen(self):
        self.clear_container()
        ctk.CTkLabel(
            self.container,
            text="Installation Finished!",
            font=("Arial", 22, "bold"),
            text_color=COLOR_SUCCESS
        ).pack(pady=(30, 15))

        tier = self.config["active_settings"]["selected_tier"]
        backend = self.config["active_settings"]["backend"].upper()

        summary_lines = [
            f"Configured Engine: Gemma 4 ({tier})" if tier != "cloud" else f"Configured Engine: Cloud ({self.config.get('cloud', {}).get('provider', 'openai')})",
            f"Hardware Backend: {backend}",
            "Execution Script: start_dot.bat"
        ]
        summary_text = "\n".join(summary_lines)
        ctk.CTkLabel(self.container, text=summary_text, font=("Arial", 14), text_color=COLOR_TEXT, justify="center").pack(pady=10)

        ctk.CTkButton(
            self.container,
            text="Finish & Exit",
            command=self.destroy,
            fg_color=COLOR_SUCCESS,
            hover_color=COLOR_SUCCESS_HOVER
        ).pack(side="bottom", pady=25)

# ==========================================
# 5. ENTRY POINT
# ==========================================
if __name__ == "__main__":
    try:
        app = DotInstaller()
        app.mainloop()
    except Exception:
        log_and_display_error("Fatal crash in mainloop execution")
        sys.exit(1)