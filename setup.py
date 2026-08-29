import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import webbrowser
import zipfile
import customtkinter as ctk
import psutil
import requests

# ==========================================
# 1. CONSTANTS & THEME
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "appConfig.json")
LOG_FILE = os.path.join(BASE_DIR, "error.log")

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

logging.basicConfig(filename=LOG_FILE, level=logging.ERROR, format="[%(asctime)s] %(levelname)s - %(message)s")


def log_error(msg, exc_info=True):
    logging.error(msg, exc_info=exc_info)


def get_python_exe():
    venv_py = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
    return venv_py if os.path.exists(venv_py) else sys.executable


# ==========================================
# 2. MAIN INSTALLER APPLICATION
# ==========================================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


class DotInstaller(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Dot Setup & Rig Analyzer")
        self.geometry("620x580")
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
            return cfg
        except Exception as e:
            log_error("Failed to load appConfig.json")
            self.after(100, lambda: self.show_fatal_error_screen(f"Could not load appConfig.json: {e}"))
            return {}

    def probe_hardware(self):
        ram = round(psutil.virtual_memory().total / (1024**3), 1)
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
            pass

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
        ctk.CTkLabel(self.container, text=f"STEP {idx} OF {len(steps)}  ·  {step_name.upper()}", font=("Arial", 11, "bold"), text_color=COLOR_ACCENT).pack(pady=(15, 0))
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
        ctk.CTkLabel(info_frame, text=f"• System Memory: {self.ram_gb} GB RAM", font=("Arial", 14), text_color=COLOR_TEXT).pack(anchor="w", padx=20, pady=(10, 4))
        ctk.CTkLabel(info_frame, text=f"• Graphics Backend: {gpu_txt}", font=("Arial", 14), text_color=COLOR_TEXT).pack(anchor="w", padx=20, pady=(0, 10))

        ctk.CTkLabel(self.container, text="Select Compute Engine:", font=("Arial", 14, "bold"), text_color=COLOR_TEXT).pack(pady=(10, 5))

        r_opts = [
            ("cuda", "CUDA (NVIDIA GPU Acceleration — Recommended)", self.has_cuda),
            ("cpu", "AVX2 (CPU Only — Standard Fallback)", True),
            ("cloud", "Cloud API (Fully Remote — Zero Local Downloads)", True)
        ]
        for val, label, enabled in r_opts:
            r = ctk.CTkRadioButton(self.container, text=label, variable=self.backend_var, value=val, fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, text_color=COLOR_TEXT, border_color=COLOR_TEXT_MUTED)
            r.pack(pady=4, anchor="w", padx=40)
            if not enabled:
                r.configure(state="disabled")

        self.make_nav_row(None, "Continue", lambda: self.show_user_details() if self.backend_var.get() == "cloud" else self.show_model_selection())

    # ----------------------------------------------------
    # STEP 2: MODEL SELECTION
    # ----------------------------------------------------
    def show_model_selection(self):
        self.make_header("Compute Tier", "Select Model")

        recommended = self.get_recommended_tier()
        ctk.CTkLabel(self.container, text=f"Recommended for your setup: Gemma 4 ({recommended})", font=("Arial", 13, "bold"), text_color=COLOR_ACCENT).pack(pady=(0, 15))

        for tier in self.config.get("models", {}).keys():
            ctk.CTkRadioButton(self.container, text=f"Gemma 4 ({tier})", variable=self.tier_var, value=tier, fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, text_color=COLOR_TEXT, border_color=COLOR_TEXT_MUTED).pack(pady=8, anchor="w", padx=60)

        self.make_nav_row(self.show_rig_analysis, "Next: Model Files", self.show_model_files)

    # ----------------------------------------------------
    # STEP 3: MODEL FILES VERIFICATION
    # ----------------------------------------------------
    def show_model_files(self):
        self.make_header("Model Files", "Download Model Files")

        tier = self.tier_var.get()
        model_info = self.config["models"][tier]
        model_fn, mmproj_fn = model_info["filename"], model_info["mmproj"]
        page_url = f"https://huggingface.co/{model_info['repo_id']}"

        bin_dir = os.path.join(BASE_DIR, "bin")
        os.makedirs(bin_dir, exist_ok=True)

        ctk.CTkLabel(
            self.container,
            text=(
                f"Gemma 4 ({tier}) is gated on Hugging Face and requires manual license acceptance.\n"
                "1. Click 'Open Model Page' and accept the license.\n"
                "2. Download both files below and place them in the 'bin' folder."
            ),
            font=("Arial", 12), text_color=COLOR_TEXT_MUTED, justify="left", wraplength=520
        ).pack(anchor="w", padx=30, pady=(0, 8))

        ctk.CTkButton(self.container, text="Open Model Page", width=200, command=lambda: webbrowser.open(page_url), fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, text_color=COLOR_TEXT).pack(anchor="w", padx=30, pady=(0, 12))

        status_box = ctk.CTkFrame(self.container, fg_color=COLOR_PANEL_ALT)
        status_box.pack(fill="x", padx=30, pady=(0, 10))

        labels = {}
        for title, fn in [("Main Model (GGUF)", model_fn), ("Vision Projector (mmproj)", mmproj_fn)]:
            row = ctk.CTkFrame(status_box, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=6)
            ctk.CTkLabel(row, text=f"{title}: {fn}", font=("Arial", 12), text_color=COLOR_TEXT).pack(side="left")
            lbl = ctk.CTkLabel(row, text="Checking...", font=("Arial", 12, "bold"))
            lbl.pack(side="right")
            labels[fn] = lbl

        err_lbl = ctk.CTkLabel(self.container, text="", font=("Arial", 12), text_color=COLOR_ERROR)
        err_lbl.pack(pady=4)

        def refresh_status():
            all_ok = True
            for fn, lbl in labels.items():
                p = os.path.join(bin_dir, fn)
                exists = os.path.exists(p) and os.path.getsize(p) > 1024 * 1024
                lbl.configure(text="Found" if exists else "Not found", text_color=COLOR_SUCCESS if exists else COLOR_ERROR)
                all_ok = all_ok and exists
            return all_ok

        refresh_status()

        path_row = ctk.CTkFrame(self.container, fg_color="transparent")
        path_row.pack(fill="x", padx=30, pady=5)
        ctk.CTkLabel(path_row, text="Target Folder: bin/", font=("Arial", 12), text_color=COLOR_TEXT).pack(side="left")
        ctk.CTkButton(path_row, text="Open Folder", width=110, command=lambda: os.startfile(bin_dir), fg_color=COLOR_BACK_BTN, hover_color=COLOR_BACK_BTN_HOVER, text_color=COLOR_TEXT).pack(side="right")

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

        ctk.CTkLabel(self.container, text="User Name / Call Sign:", font=("Arial", 13), text_color=COLOR_TEXT).pack(anchor="w", padx=40, pady=(5, 2))
        ctk.CTkEntry(self.container, textvariable=self.user_name_var, width=340, fg_color=COLOR_PANEL_ALT, border_color=COLOR_ACCENT_MUTED, text_color=COLOR_TEXT).pack(padx=40, pady=(0, 8))

        ctk.CTkLabel(self.container, text="GitHub Personal Access Token (Optional for GitHub MCP):", font=("Arial", 13), text_color=COLOR_TEXT).pack(anchor="w", padx=40, pady=(5, 2))
        ctk.CTkEntry(self.container, textvariable=self.github_token_var, placeholder_text="ghp_... (Optional)", show="*", width=340, fg_color=COLOR_PANEL_ALT, border_color=COLOR_ACCENT_MUTED, text_color=COLOR_TEXT).pack(padx=40, pady=(0, 8))

        if is_cloud:
            def on_provider_change(val):
                for p_info in CLOUD_PROVIDERS.values():
                    if p_info["label"] == val:
                        self.base_url_var.set(p_info["base_url"])
                        self.model_var.set(p_info["default_model"])
                        break

            ctk.CTkLabel(self.container, text="Cloud Provider:", font=("Arial", 13), text_color=COLOR_TEXT).pack(anchor="w", padx=40, pady=(5, 2))
            ctk.CTkOptionMenu(
                self.container, values=[p["label"] for p in CLOUD_PROVIDERS.values()], variable=self.provider_var,
                command=on_provider_change, width=340, fg_color=COLOR_PANEL_ALT, button_color=COLOR_ACCENT, button_hover_color=COLOR_ACCENT_HOVER, dropdown_fg_color=COLOR_PANEL, text_color=COLOR_TEXT
            ).pack(padx=40, pady=(0, 10))

            ctk.CTkLabel(self.container, text="Base URL:", font=("Arial", 13), text_color=COLOR_TEXT).pack(anchor="w", padx=40, pady=(5, 2))
            ctk.CTkEntry(self.container, textvariable=self.base_url_var, width=340, fg_color=COLOR_PANEL_ALT, border_color=COLOR_ACCENT_MUTED, text_color=COLOR_TEXT).pack(padx=40, pady=(0, 10))

            ctk.CTkLabel(self.container, text="Model:", font=("Arial", 13), text_color=COLOR_TEXT).pack(anchor="w", padx=40, pady=(5, 2))
            ctk.CTkEntry(self.container, textvariable=self.model_var, width=340, fg_color=COLOR_PANEL_ALT, border_color=COLOR_ACCENT_MUTED, text_color=COLOR_TEXT).pack(padx=40, pady=(0, 10))

            ctk.CTkLabel(self.container, text="API Key:", font=("Arial", 13), text_color=COLOR_TEXT).pack(anchor="w", padx=40, pady=(5, 2))
            self.api_entry = ctk.CTkEntry(self.container, textvariable=self.api_key_var, show="*", width=340, fg_color=COLOR_PANEL_ALT, border_color=COLOR_ACCENT_MUTED, text_color=COLOR_TEXT)
            self.api_entry.pack(padx=40, pady=(0, 15))

        elif self.backend_var.get() == "cuda":
            ctk.CTkLabel(self.container, text="GPU Offload Layers (Advanced):", font=("Arial", 13), text_color=COLOR_TEXT).pack(anchor="w", padx=40, pady=(5, 2))
            layer_lbl = ctk.CTkLabel(self.container, text=f"{self.layers_var.get()} Layers", font=("Arial", 12), text_color=COLOR_TEXT_MUTED)
            slider = ctk.CTkSlider(
                self.container, from_=0, to=99, number_of_steps=99, variable=self.layers_var,
                command=lambda v: layer_lbl.configure(text=f"{int(v)} Layers (Max Offload)" if int(v) == 99 else f"{int(v)} Layers"),
                width=340, progress_color=COLOR_ACCENT, button_color=COLOR_ACCENT, button_hover_color=COLOR_ACCENT_HOVER
            )
            slider.pack(padx=40, pady=(0, 5))
            layer_lbl.pack(pady=(0, 10))

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
        self.progress = ctk.CTkProgressBar(self.container, width=420, progress_color=COLOR_ACCENT)
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
            # 1. Frontend npm install
            dume_dir = os.path.join(BASE_DIR, "dum-e")
            if os.path.exists(os.path.join(dume_dir, "package.json")):
                self.update_status("Installing frontend dependencies (npm install)...", 0.1)
                npm_cmd = shutil.which("npm") or "npm"
                subprocess.run([npm_cmd, "install"], cwd=dume_dir, shell=True, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

            backend = self.backend_var.get()

            # 2. Local Engine Downloads
            if backend != "cloud":
                self.update_status("Fetching llama.cpp binaries from GitHub...", 0.3)
                bin_dir = os.path.join(BASE_DIR, "bin")
                os.makedirs(bin_dir, exist_ok=True)

                headers = {"User-Agent": "Dot-Setup-Wizard/1.0"}
                res = requests.get("https://api.github.com/repos/ggml-org/llama.cpp/releases", headers=headers, params={"per_page": 8}, timeout=15)
                res.raise_for_status()

                zip_urls = self.resolve_release_zips(res.json(), backend)
                for i, url in enumerate(zip_urls):
                    self.update_status(f"Downloading engine archive ({i+1}/{len(zip_urls)})...", 0.4 + (i * 0.2))
                    z_res = requests.get(url, stream=True, timeout=30)
                    z_res.raise_for_status()
                    with zipfile.ZipFile(io.BytesIO(z_res.content)) as zf:
                        zf.extractall(bin_dir)

            # 3. Finalize
            self.update_status("Writing configuration and generating launcher...", 0.9)
            self.finalize_setup()
            self.update_status("Setup Complete!", 1.0)
            self.after(0, self.show_success_screen)

        except Exception as e:
            log_error("Installation worker failed")
            self.after(0, lambda: self.show_fatal_error_screen(f"Installation failed: {e}"))

    def resolve_release_zips(self, releases, backend):
        for release in releases:
            assets = release.get("assets", [])
            cpu_url = next((a["browser_download_url"] for a in assets if "win" in a["name"].lower() and "x64.zip" in a["name"].lower() and "cpu" in a["name"].lower()), None)
            if not cpu_url:
                continue
            if backend == "cpu":
                return [cpu_url]

            # CUDA matching
            cuda_url, highest_v = None, 0.0
            for a in assets:
                name = a["name"].lower()
                if "cuda" in name and "win" in name and "x64.zip" in name:
                    m = re.search(r"cuda-?(\d+(?:\.\d+)?)", name)
                    if m and float(m.group(1)) <= self.cuda_version and float(m.group(1)) > highest_v:
                        highest_v, cuda_url = float(m.group(1)), a["browser_download_url"]

            if cuda_url:
                return [cpu_url, cuda_url]
        raise ValueError("Could not find compatible llama.cpp Windows binaries in recent releases.")

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
            except Exception:
                pass

        # Build start_dot.bat
        venv_py = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
        py_cmd = f"..\\.venv\\Scripts\\python.exe" if os.path.exists(venv_py) else "py -3.12"
        orchestrator_cmd = f"cd dum-e && {py_cmd} -m uvicorn server:app --port 3000"
        frontend_cmd = "cd dum-e && npx @neutralinojs/neu run"

        engine_block = ""
        if backend != "cloud":
            active_model = self.config["models"][tier]
            gpu_flag = f"-ngl {self.layers_var.get()}" if backend == "cuda" else ""
            port = self.config["active_settings"].get("port", 11434)
            llama_cmd = f"llama-server.exe -m {active_model['filename']} --mmproj {active_model['mmproj']} --port {port} -c {active_model.get('context_size', 8192)} -fa on {gpu_flag} --temp 0.0 --alias dot-engine"

            engine_block = f"""echo [1/3] Starting Local Inference Engine ({backend.upper()})...
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
echo.
"""

        env_block = ""
        if backend == "cloud":
            env_block = f"""set DOT_CLOUD_API_KEY={self.config['cloud']['api_key']}
set DOT_CLOUD_BASE_URL={self.config['cloud']['base_url']}
set DOT_CLOUD_MODEL={self.config['cloud']['model']}
"""

        bat_content = f"""@echo off
{env_block}
echo ========================================================
echo   Dot is starting up -- please wait...
echo ========================================================
echo.
{engine_block}echo [2/3] Starting Python Orchestrator...
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
echo.
echo [3/3] Launching Dot UI...
start "" /min cmd /c "{frontend_cmd}"
echo.
echo ========================================================
echo   All systems go! Dot is ready.
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
    except Exception:
        log_error("Fatal crash during setup mainloop")
        sys.exit(1)