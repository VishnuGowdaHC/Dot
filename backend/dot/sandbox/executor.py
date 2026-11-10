"""
Asynchronous command executor for the Dot sandbox container.
Runs commands inside the container and streams live output.
Complies with ASD-STE100 technical writing standards.
"""

import asyncio
from typing import Tuple, Optional, Callable

from dot.sandbox.manager import CONTAINER_NAME, ensure_sandbox_ready, _get_docker_bin


async def exec_in_sandbox(
    command: str,
    timeout: float = 120.0,
    working_dir: str = "/workspace",
    stream_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[int, str]:
    """Runs a shell command inside the sandbox container asynchronously."""
    ready = await ensure_sandbox_ready()
    if not ready:
        return -1, "Error: Docker sandbox container is not available."

    docker_bin = _get_docker_bin()
    cmd = [
        docker_bin, "exec", "-i",
        "-w", working_dir,
        CONTAINER_NAME,
        "bash", "-c", command
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
    except Exception as spawn_err:
        return -1, f"Error spawning command in sandbox: {spawn_err}"

    output_chunks = []

    async def read_stream(stream, is_stderr: bool = False):
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
                read_stream(proc.stderr, is_stderr=True)
            ),
            timeout=timeout
        )
        await proc.wait()
        exit_code = proc.returncode if proc.returncode is not None else 0
        return exit_code, "".join(output_chunks)

    except asyncio.TimeoutError:
        # Kill the hanging command inside the container.
        kill_cmd = [docker_bin, "exec", CONTAINER_NAME, "pkill", "-9", "-f", command[:30]]
        kill_proc = await asyncio.create_subprocess_exec(
            *kill_cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await kill_proc.wait()
        try:
            proc.kill()
        except Exception:
            pass
        return -1, f"Command execution timed out after {timeout} seconds."

    except Exception as exec_err:
        return -1, f"Unexpected execution error: {exec_err}"

