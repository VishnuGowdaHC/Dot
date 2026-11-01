"""
Centralized path definitions and single source of truth for project locations.
"""

import os
from pathlib import Path

# Package and root anchors
DOT_PKG_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = DOT_PKG_DIR.parent
ROOT_DIR = BACKEND_DIR.parent
FRONTEND_DIR = ROOT_DIR / "frontend"

# Configuration file paths
CONFIG_PATH = ROOT_DIR / "appConfig.json"
MCP_CONFIG_PATH = DOT_PKG_DIR / "config" / "mcp_servers.json"
ALLOWED_APPS_PATH = DOT_PKG_DIR / "config" / "allowed_apps.yml"

# Environment file paths
DOT_ENV_PATH = ROOT_DIR / ".env"
BACKEND_ENV_PATH = BACKEND_DIR / ".env"
DOT_PKG_ENV_PATH = DOT_PKG_DIR / ".env"

# Runtime directories
BIN_DIR = ROOT_DIR / "bin"
LOGS_DIR = ROOT_DIR / "logs"
DEBUG_LOG_FILE = LOGS_DIR / "agent_debug.log"
CONTEXT_LOG_FILE = LOGS_DIR / "agent_context.log"
OBS_LOG_DIR = LOGS_DIR / "observations"

# Storage and memory directories
MEMORY_DIR = DOT_PKG_DIR / "memory"
STORAGE_DIR = MEMORY_DIR / "storage"
TRANSCRIPTS_DIR = STORAGE_DIR / "transcripts"
SUMMARIES_DIR = STORAGE_DIR / "summaries"
TOKENIZER_DIR = MEMORY_DIR / "tokenizer_files"
CHROMA_DIR = STORAGE_DIR / "chroma_db"

# Bundled MCP server binaries
MCP_BIN_DIR = DOT_PKG_DIR / "mcp" / "bin"


def ensure_directories() -> None:
    """Creates required runtime directories if they do not exist."""
    for path in [LOGS_DIR, OBS_LOG_DIR, TRANSCRIPTS_DIR, SUMMARIES_DIR, CHROMA_DIR]:
        path.mkdir(parents=True, exist_ok=True)


ensure_directories()
