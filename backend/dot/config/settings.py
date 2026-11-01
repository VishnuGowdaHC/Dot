"""
Configuration reader, writer, and environment variable synchronizer.
"""

import os
import json
from typing import Any, Dict, Optional
from dot.config.paths import CONFIG_PATH, BACKEND_ENV_PATH, DOT_ENV_PATH, DOT_PKG_ENV_PATH


def load_config() -> Dict[str, Any]:
    """Reads configuration data from appConfig.json."""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config(cfg: Dict[str, Any]) -> None:
    """Writes configuration data to appConfig.json."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)


def get_active_tier() -> str:
    """Returns the active model tier name."""
    cfg = load_config()
    active = cfg.get("active_settings", {})
    if active.get("backend") == "cloud":
        return "cloud"
    return str(active.get("selected_tier", "4B"))


def get_github_token() -> str:
    """Returns the configured GitHub Personal Access Token."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token

    cfg = load_config()
    token = cfg.get("github_token", "").strip()
    if token:
        return token

    for env_path in [BACKEND_ENV_PATH, DOT_ENV_PATH, DOT_PKG_ENV_PATH]:
        if env_path.exists():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("GITHUB_TOKEN="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            return val
            except Exception:
                pass
    return ""


def update_github_token(token: str) -> None:
    """Updates the GitHub token across process memory, config, and env files."""
    cleaned = token.strip()
    os.environ["GITHUB_TOKEN"] = cleaned

    cfg = load_config()
    cfg["github_token"] = cleaned
    save_config(cfg)

    content = f'GITHUB_TOKEN="{cleaned}"\n'
    for env_path in [BACKEND_ENV_PATH, DOT_ENV_PATH, DOT_PKG_ENV_PATH]:
        try:
            env_path.parent.mkdir(parents=True, exist_ok=True)
            env_path.write_text(content, encoding="utf-8")
        except Exception:
            pass


def is_browser_headless() -> bool:
    """Returns true if the browser must execute without a visible window."""
    cfg = load_config()
    return bool(cfg.get("active_settings", {}).get("browser_headless", False))


def set_browser_headless(headless: bool) -> None:
    """Updates and saves the browser headless configuration."""
    cfg = load_config()
    active = cfg.setdefault("active_settings", {})
    active["browser_headless"] = bool(headless)
    save_config(cfg)

