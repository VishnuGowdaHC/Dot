"""
Docker container lifecycle manager for Dot sandbox.
Controls container startup, resource caps, and pause states.
Complies with ASD-STE100 technical writing standards.
"""

import os
import shutil
import asyncio
from pathlib import Path
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


def _get_docker_bin() -> str:
    """Finds the docker executable on the host system."""
    docker_bin = shutil.which("docker.exe") or shutil.which("docker") or "docker"
    return docker_bin


async def is_docker_available() -> bool:
    """Verifies that the Docker daemon runs on the host system."""
    docker_bin = _get_docker_bin()
    try:
        proc = await asyncio.create_subprocess_exec(
            docker_bin, "info",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
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
            stderr=asyncio.subprocess.DEVNULL
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
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
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
    docker_bin = _get_docker_bin()
    try:
        proc = await asyncio.create_subprocess_exec(
            docker_bin, "ps", "-q", "-f", f"name=^/{CONTAINER_NAME}$",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )
        stdout, _ = await proc.communicate()
        return bool(stdout.strip())
    except Exception:
        return False


async def is_sandbox_paused() -> bool:
    """Verifies if the sandbox container is paused."""
    docker_bin = _get_docker_bin()
    try:
        proc = await asyncio.create_subprocess_exec(
            docker_bin, "inspect", "--format={{.State.Paused}}", CONTAINER_NAME,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip().lower() == "true"
    except Exception:
        return False


async def start_sandbox() -> bool:
    """Starts the sandbox container with strict resource limits."""
    if await is_sandbox_running():
        return True

    docker_bin = _get_docker_bin()
    SANDBOX_WORKSPACE.mkdir(parents=True, exist_ok=True)

    # Ensure image exists before starting container.
    if not await is_image_present():
        built = await build_sandbox_image()
        if not built:
            return False

    # Remove any stale stopped container with the same name.
    cleanup_proc = await asyncio.create_subprocess_exec(
        docker_bin, "rm", "-f", CONTAINER_NAME,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
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
        "-v", f"{host_ws}:/workspace",
        "--tmpfs", "/tmp:rw,size=128m",
        IMAGE_TAG
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            print(f"[Sandbox] Container '{CONTAINER_NAME}' started successfully.")
            return True
        print(f"[Sandbox Error] Container start failed: {stderr.decode(errors='replace')}")
        return False
    except Exception as err:
        print(f"[Sandbox Error] Start error: {err}")
        return False


async def stop_sandbox() -> bool:
    """Stops and removes the sandbox container."""
    docker_bin = _get_docker_bin()
    try:
        proc = await asyncio.create_subprocess_exec(
            docker_bin, "rm", "-f", CONTAINER_NAME,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.wait()
        print(f"[Sandbox] Container '{CONTAINER_NAME}' stopped.")
        return True
    except Exception as err:
        print(f"[Sandbox Error] Stop error: {err}")
        return False


async def pause_sandbox() -> bool:
    """Freezes container processes for human intervention."""
    docker_bin = _get_docker_bin()
    try:
        proc = await asyncio.create_subprocess_exec(
            docker_bin, "pause", CONTAINER_NAME,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.wait()
        return proc.returncode == 0
    except Exception:
        return False


async def unpause_sandbox() -> bool:
    """Unfreezes container processes after human intervention."""
    docker_bin = _get_docker_bin()
    try:
        proc = await asyncio.create_subprocess_exec(
            docker_bin, "unpause", CONTAINER_NAME,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.wait()
        return proc.returncode == 0
    except Exception:
        return False


async def ensure_sandbox_ready() -> bool:
    """Ensures the Docker environment and sandbox container are active."""
    if not await is_docker_available():
        print("[Sandbox Error] Docker daemon is not available.")
        return False
    if not await is_sandbox_running():
        return await start_sandbox()
    if await is_sandbox_paused():
        await unpause_sandbox()
    return True

