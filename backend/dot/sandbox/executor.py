"""
Asynchronous command executor for the Dot sandbox container.
Runs commands inside the container and streams live output.
Complies with ASD-STE100 technical writing standards.
"""

import asyncio
from typing import Tuple, Optional, Callable

from dot.sandbox.manager import (
    CONTAINER_NAME,
    ensure_sandbox_ready,
    invalidate_sandbox_cache,
    pause_sandbox,
    _get_docker_bin,
)
from dot.sandbox.intervention import get_intervention_manager


async def _run_exec_once(
    command: str,
    timeout: float,
    working_dir: str,
    stream_callback: Optional[Callable[[str], None]],
) -> Tuple[int, str]:
    """Executes one docker exec subprocess and captures output."""
    docker_bin = _get_docker_bin()
    timeout_sec = max(1, int(timeout))
    cmd = [
        docker_bin, "exec", "-i",
        "-w", working_dir,
        CONTAINER_NAME,
        "timeout", "-k", "5s", f"{timeout_sec}s",
        "bash", "-c", command,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as spawn_err:
        return -1, f"Error spawning command in sandbox: {spawn_err}"

    output_chunks = []

    async def read_stream(stream) -> None:
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace")
            output_chunks.append(text)
            if stream_callback:
                try:
                    stream_callback(text)
                except Exception:
                    pass

    try:
        await asyncio.wait_for(
            asyncio.gather(
                read_stream(proc.stdout),
                read_stream(proc.stderr),
            ),
            timeout=timeout + 5.0,
        )
        await proc.wait()
        exit_code = proc.returncode if proc.returncode is not None else 0
        if exit_code == 124:
            return -1, f"Command execution timed out after {timeout} seconds."
        return exit_code, "".join(output_chunks)

    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()
        return -1, f"Command execution timed out after {timeout} seconds."

    except Exception as exec_err:
        return -1, f"Unexpected execution error: {exec_err}"


async def exec_in_sandbox(
    command: str,
    timeout: float = 120.0,
    working_dir: str = "/workspace",
    stream_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[int, str]:
    """Runs a shell command inside the sandbox container asynchronously."""
    mgr = get_intervention_manager()
    was_intervention_paused = mgr.is_paused

    ready = await ensure_sandbox_ready()
    if not ready:
        return -1, "Error: Docker sandbox container is not available."

    try:
        exit_code, output = await _run_exec_once(command, timeout, working_dir, stream_callback)
        # Retry once if cached state was stale and the container stopped externally.
        if exit_code != 0 and ("No such container" in output or "is not running" in output):
            invalidate_sandbox_cache()
            if await ensure_sandbox_ready():
                exit_code, output = await _run_exec_once(command, timeout, working_dir, stream_callback)
        return exit_code, output
    finally:
        if was_intervention_paused and mgr.is_paused:
            await pause_sandbox()
