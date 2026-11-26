"""
Auto-update service for checking and installing Dot GitHub releases.
Complies with ASD-STE100 technical writing standards.
"""

import asyncio
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

import httpx

from dot.config.paths import FRONTEND_DIR

GITHUB_REPO = "VishnuGowdaHC/Dot"
RELEASES_LATEST_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
DEFAULT_VERSION = "3.0.1"

UPDATE_PROGRESS: Dict[str, Any] = {
    "stage": "idle",
    "percent": 0,
    "downloaded_bytes": 0,
    "total_bytes": 0,
    "speed_bps": 0.0,
    "detail": "",
    "error": None,
}


def get_update_progress() -> Dict[str, Any]:
    """Returns a snapshot of the current update download and installation progress."""
    return dict(UPDATE_PROGRESS)


async def _set_progress(
    on_progress: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Updates the shared progress state and invokes an optional async callback."""
    UPDATE_PROGRESS.update(kwargs)
    snap = get_update_progress()
    if on_progress:
        try:
            await on_progress(snap)
        except Exception:
            pass
    return snap


def get_current_version() -> str:
    """Reads the installed Dot version from neutralino.config.json."""
    cfg_path = FRONTEND_DIR / "neutralino.config.json"
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            ver = str(data.get("version", "")).strip()
            if ver:
                return ver.lstrip("v")
        except Exception:
            pass
    return DEFAULT_VERSION


def parse_semver(version_str: str) -> Tuple[int, int, int]:
    """Parses a semantic version string into a three-integer tuple."""
    cleaned = str(version_str or "").strip().lstrip("vV")
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?", cleaned)
    if not match:
        return (0, 0, 0)
    major = int(match.group(1) or 0)
    minor = int(match.group(2) or 0)
    patch = int(match.group(3) or 0)
    return (major, minor, patch)


def is_newer_version(latest: str, current: str) -> bool:
    """Returns True when the latest version is greater than the current version."""
    return parse_semver(latest) > parse_semver(current)


def extract_release_assets(release_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts installer executable and SHA256 asset metadata from a GitHub release."""
    assets = release_data.get("assets", []) or []
    installer_url = None
    installer_name = None
    installer_size = 0
    sha256_url = None

    for asset in assets:
        name = str(asset.get("name", ""))
        lower = name.lower()
        url = asset.get("browser_download_url")
        if not url:
            continue
        if lower.endswith(".sha256") and "setup" in lower:
            sha256_url = url
        elif lower.endswith(".exe") and "setup" in lower:
            installer_url = url
            installer_name = name
            installer_size = int(asset.get("size", 0) or 0)

    return {
        "download_url": installer_url,
        "asset_name": installer_name,
        "asset_size": installer_size,
        "sha256_url": sha256_url,
    }


async def check_for_updates() -> Dict[str, Any]:
    """Queries GitHub Releases for a newer Dot installer version."""
    current_version = get_current_version()
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"Dot-Updater/{current_version}",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(RELEASES_LATEST_URL, headers=headers)
            if resp.status_code != 200:
                return {
                    "status": "error",
                    "current_version": current_version,
                    "update_available": False,
                    "error": f"GitHub API returned status {resp.status_code}.",
                }
            release = resp.json()
    except Exception as err:
        return {
            "status": "error",
            "current_version": current_version,
            "update_available": False,
            "error": str(err),
        }

    tag_name = str(release.get("tag_name", "")).strip()
    latest_version = tag_name.lstrip("vV")
    update_available = bool(latest_version and is_newer_version(latest_version, current_version))
    asset_info = extract_release_assets(release)

    return {
        "status": "ok",
        "current_version": current_version,
        "latest_version": latest_version or current_version,
        "tag_name": tag_name,
        "update_available": update_available,
        "release_notes": str(release.get("body", "") or "").strip(),
        "html_url": release.get("html_url", f"https://github.com/{GITHUB_REPO}/releases"),
        **asset_info,
        "error": None,
    }


def verify_sha256_file(file_path: Path, expected_content: str) -> bool:
    """Verifies that a downloaded file matches the expected SHA256 digest."""
    tokens = str(expected_content or "").strip().split()
    if not tokens:
        return False
    expected_hash = tokens[0].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        return False

    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower() == expected_hash


async def download_and_install_update(
    download_url: str,
    sha256_url: Optional[str] = None,
    expected_size: int = 0,
    on_progress: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
) -> Dict[str, Any]:
    """Downloads the installer, verifies its checksum, and starts the update."""
    if not download_url or not download_url.startswith("https://github.com/"):
        await _set_progress(on_progress, stage="error", percent=0, detail="Invalid update download URL.", error="Invalid update download URL.")
        return {"status": "error", "message": "Invalid update download URL."}

    update_dir = Path(tempfile.gettempdir()) / "DotUpdate"
    update_dir.mkdir(parents=True, exist_ok=True)
    installer_path = update_dir / "Dot-Setup-x64.exe"
    headers = {"User-Agent": f"Dot-Updater/{get_current_version()}"}

    await _set_progress(
        on_progress,
        stage="downloading",
        percent=0,
        downloaded_bytes=0,
        total_bytes=int(expected_size or 0),
        speed_bps=0.0,
        detail="Connecting to GitHub Releases...",
        error=None,
    )

    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            async with client.stream("GET", download_url, headers=headers) as resp:
                resp.raise_for_status()
                total_bytes = int(resp.headers.get("content-length") or expected_size or 0)
                downloaded = 0
                started_at = time.monotonic()
                last_emit = 0.0

                with open(installer_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        now = time.monotonic()
                        if now - last_emit >= 0.15 or (total_bytes > 0 and downloaded >= total_bytes):
                            elapsed = max(now - started_at, 0.01)
                            speed_bps = downloaded / elapsed
                            pct = min(99, int((downloaded / total_bytes) * 100)) if total_bytes > 0 else 0
                            dl_mb = downloaded / (1024 * 1024)
                            tot_mb = total_bytes / (1024 * 1024)
                            spd_mb = speed_bps / (1024 * 1024)
                            detail = (
                                f"Downloading installer ({dl_mb:.1f} / {tot_mb:.1f} MB at {spd_mb:.1f} MB/s)"
                                if total_bytes > 0
                                else f"Downloading installer ({dl_mb:.1f} MB at {spd_mb:.1f} MB/s)"
                            )
                            await _set_progress(
                                on_progress,
                                stage="downloading",
                                percent=pct,
                                downloaded_bytes=downloaded,
                                total_bytes=total_bytes,
                                speed_bps=speed_bps,
                                detail=detail,
                                error=None,
                            )
                            last_emit = now

            if sha256_url and sha256_url.startswith("https://github.com/"):
                await _set_progress(
                    on_progress,
                    stage="verifying",
                    percent=100,
                    speed_bps=0.0,
                    detail="Verifying SHA-256 installer checksum...",
                )
                sha_resp = await client.get(sha256_url, headers=headers)
                if sha_resp.status_code == 200:
                    valid = await asyncio.to_thread(verify_sha256_file, installer_path, sha_resp.text)
                    if not valid:
                        installer_path.unlink(missing_ok=True)
                        msg = "Checksum verification failed for downloaded installer."
                        await _set_progress(on_progress, stage="error", detail=msg, error=msg)
                        return {"status": "error", "message": msg}
    except Exception as err:
        msg = f"Update download failed: {err}"
        await _set_progress(on_progress, stage="error", detail=msg, error=msg)
        return {"status": "error", "message": msg}

    await _set_progress(
        on_progress,
        stage="launching",
        percent=100,
        speed_bps=0.0,
        detail="Starting silent installer...",
    )
    try:
        subprocess.Popen(
            [str(installer_path), "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"],
            cwd=str(update_dir),
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0x00000008),
        )
    except Exception as err:
        msg = f"Failed to start installer: {err}"
        await _set_progress(on_progress, stage="error", detail=msg, error=msg)
        return {"status": "error", "message": msg}

    final_msg = "Installer running. Dot will close and restart automatically."
    await _set_progress(on_progress, stage="installing", percent=100, detail=final_msg, error=None)
    return {"status": "installing", "message": final_msg, "installer_path": str(installer_path)}
