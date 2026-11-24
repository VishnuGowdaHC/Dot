"""
Docker container lifecycle manager for Dot sandbox.
Controls container startup, resource caps, and pause states.
Complies with ASD-STE100 technical writing standards.
"""

import shutil
import asyncio
from typing import Optional

from dot.config.paths import ROOT_DIR, BACKEND_DIR

IMAGE_TAG = "dot-sandbox:latest"
CONTAINER_NAME = "dot-sandbox"
SANDBOX_WORKSPACE = ROOT_DIR / "sandbox_workspace"
DOCKERFILE_PATH = BACKEND_DIR / "Dockerfile.sandbox"

# Maximum container memory limit in gigabytes.
MAX_MEMORY = "1.5g"
# Maximum CPU cores assigned to the container.
MAX_CPUS = "2.0"

_LIFECYCLE_LOCK: Optional[asyncio.Lock] = None
_LOCK_LOOP: Optional[asyncio.AbstractEventLoop] = None
_SANDBOX_RUNNING_CACHE: Optional[bool] = None
_SANDBOX_PAUSED_CACHE: bool = False


def _get_lifecycle_lock() -> asyncio.Lock:
    """Returns an asyncio lock bound to the active event loop."""
    global _LIFECYCLE_LOCK, _LOCK_LOOP
    loop = asyncio.get_running_loop()
    if _LIFECYCLE_LOCK is None or _LOCK_LOOP is not loop:
        _LIFECYCLE_LOCK = asyncio.Lock()
        _LOCK_LOOP = loop
    return _LIFECYCLE_LOCK


def invalidate_sandbox_cache() -> None:
    """Clears the cached container running and pause state."""
    global _SANDBOX_RUNNING_CACHE, _SANDBOX_PAUSED_CACHE
    _SANDBOX_RUNNING_CACHE = None
    _SANDBOX_PAUSED_CACHE = False


def _get_docker_bin() -> str:
    """Finds the docker executable on the host system."""
    return shutil.which("docker.exe") or shutil.which("docker") or "docker"


async def is_docker_available() -> bool:
    """Verifies that the Docker daemon runs on the host system."""
    docker_bin = _get_docker_bin()
    try:
        proc = await asyncio.create_subprocess_exec(
            docker_bin, "info",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        return proc.returncode == 0
    except Exception:
        return False


async def is_image_present() -> bool:
    """Verifies that the sandbox image exists locally."""
    docker_bin = _get_docker_bin()
    try:
        proc = await asyncio.create_subprocess_exec(
            docker_bin, "images", "-q", IMAGE_TAG,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        return bool(stdout.strip())
    except Exception:
        return False


async def build_sandbox_image() -> bool:
    """Builds the lightweight sandbox image from Dockerfile.sandbox."""
    docker_bin = _get_docker_bin()
    if not DOCKERFILE_PATH.exists():
        print(f"[Sandbox Error] Dockerfile not found at {DOCKERFILE_PATH}")
        return False

    print(f"[Sandbox] Building image '{IMAGE_TAG}'...")
    try:
        proc = await asyncio.create_subprocess_exec(
            docker_bin, "build",
            "-t", IMAGE_TAG,
            "-f", str(DOCKERFILE_PATH),
            str(BACKEND_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode == 0:
            print(f"[Sandbox] Image '{IMAGE_TAG}' built successfully.")
            return True
        print(f"[Sandbox Error] Image build failed: {stderr.decode(errors='replace')}")
        return False
    except Exception as err:
        print(f"[Sandbox Error] Build error: {err}")
        return False


async def is_sandbox_running() -> bool:
    """Verifies if the sandbox container is currently running."""
    global _SANDBOX_RUNNING_CACHE
    docker_bin = _get_docker_bin()
    try:
        proc = await asyncio.create_subprocess_exec(
            docker_bin, "ps", "-q", "-f", f"name=^/{CONTAINER_NAME}$",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        running = bool(stdout.strip())
        _SANDBOX_RUNNING_CACHE = running
        return running
    except Exception:
        _SANDBOX_RUNNING_CACHE = False
        return False


async def is_sandbox_paused() -> bool:
    """Verifies if the sandbox container is paused."""
    global _SANDBOX_PAUSED_CACHE
    docker_bin = _get_docker_bin()
    try:
        proc = await asyncio.create_subprocess_exec(
            docker_bin, "inspect", "--format={{.State.Paused}}", CONTAINER_NAME,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        paused = stdout.decode().strip().lower() == "true"
        _SANDBOX_PAUSED_CACHE = paused
        return paused
    except Exception:
        _SANDBOX_PAUSED_CACHE = False
        return False


async def _start_sandbox_unlocked() -> bool:
    """Starts the sandbox container without acquiring the lifecycle lock."""
    global _SANDBOX_RUNNING_CACHE, _SANDBOX_PAUSED_CACHE
    if await is_sandbox_running():
        return True

    docker_bin = _get_docker_bin()
    SANDBOX_WORKSPACE.mkdir(parents=True, exist_ok=True)

    # Ensure the image exists before starting the container.
    if not await is_image_present():
        built = await build_sandbox_image()
        if not built:
            return False

    # Remove any stale stopped container with the same name.
    cleanup_proc = await asyncio.create_subprocess_exec(
        docker_bin, "rm", "-f", CONTAINER_NAME,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await cleanup_proc.wait()

    host_ws = str(SANDBOX_WORKSPACE.resolve()).replace("\\", "/")
    cmd = [
        docker_bin, "run", "-d",
        "--name", CONTAINER_NAME,
        f"--memory={MAX_MEMORY}",
        f"--memory-swap={MAX_MEMORY}",
        f"--cpus={MAX_CPUS}",
        "--pids-limit=256",
        "--init",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "-v", f"{host_ws}:/workspace",
        "--tmpfs", "/tmp:rw,size=128m",
        IMAGE_TAG,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode == 0:
            _SANDBOX_RUNNING_CACHE = True
            _SANDBOX_PAUSED_CACHE = False
            print(f"[Sandbox] Container '{CONTAINER_NAME}' started successfully.")
            return True
        _SANDBOX_RUNNING_CACHE = False
        print(f"[Sandbox Error] Container start failed: {stderr.decode(errors='replace')}")
        return False
    except Exception as err:
        _SANDBOX_RUNNING_CACHE = False
        print(f"[Sandbox Error] Start error: {err}")
        return False


async def start_sandbox() -> bool:
    """Starts the sandbox container with strict resource and security limits."""
    async with _get_lifecycle_lock():
        return await _start_sandbox_unlocked()


async def _stop_sandbox_unlocked() -> bool:
    """Stops and removes the sandbox container without acquiring the lock."""
    global _SANDBOX_RUNNING_CACHE, _SANDBOX_PAUSED_CACHE
    docker_bin = _get_docker_bin()
    try:
        proc = await asyncio.create_subprocess_exec(
            docker_bin, "rm", "-f", CONTAINER_NAME,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        _SANDBOX_RUNNING_CACHE = False
        _SANDBOX_PAUSED_CACHE = False
        if proc.returncode == 0:
            print(f"[Sandbox] Container '{CONTAINER_NAME}' stopped.")
            return True
        return False
    except Exception as err:
        print(f"[Sandbox Error] Stop error: {err}")
        return False


async def stop_sandbox() -> bool:
    """Stops and removes the sandbox container."""
    async with _get_lifecycle_lock():
        return await _stop_sandbox_unlocked()


async def _pause_sandbox_unlocked() -> bool:
    """Freezes container processes without acquiring the lifecycle lock."""
    global _SANDBOX_PAUSED_CACHE
    docker_bin = _get_docker_bin()
    try:
        proc = await asyncio.create_subprocess_exec(
            docker_bin, "pause", CONTAINER_NAME,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if proc.returncode == 0:
            _SANDBOX_PAUSED_CACHE = True
            return True
        return False
    except Exception:
        return False


async def pause_sandbox() -> bool:
    """Freezes container processes for human intervention."""
    async with _get_lifecycle_lock():
        return await _pause_sandbox_unlocked()


async def _unpause_sandbox_unlocked() -> bool:
    """Unfreezes container processes without acquiring the lifecycle lock."""
    global _SANDBOX_PAUSED_CACHE
    docker_bin = _get_docker_bin()
    try:
        proc = await asyncio.create_subprocess_exec(
            docker_bin, "unpause", CONTAINER_NAME,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if proc.returncode == 0:
            _SANDBOX_PAUSED_CACHE = False
            return True
        return False
    except Exception:
        return False


async def unpause_sandbox() -> bool:
    """Unfreezes container processes after human intervention."""
    async with _get_lifecycle_lock():
        return await _unpause_sandbox_unlocked()


async def ensure_sandbox_ready() -> bool:
    """Ensures the Docker environment and sandbox container are active."""
    async with _get_lifecycle_lock():
        if _SANDBOX_RUNNING_CACHE is True:
            if _SANDBOX_PAUSED_CACHE:
                await _unpause_sandbox_unlocked()
            return True

        if not await is_docker_available():
            print("[Sandbox Error] Docker daemon is not available.")
            return False
        if not await is_sandbox_running():
            return await _start_sandbox_unlocked()
        if await is_sandbox_paused():
            await _unpause_sandbox_unlocked()
        return True
