"""
Sandboxed browser automation module for Dot.
Executes browser automation inside the Docker container via agent-browser.
Uses zero GPU VRAM.
Complies with ASD-STE100 technical writing standards.
"""

import shlex
import urllib.parse
from pathlib import Path

from dot.sandbox.executor import exec_in_sandbox

_FALLBACK_SCRIPT = """
import asyncio
import os
from playwright.async_api import async_playwright

async def main():
    url = os.environ["DOT_TARGET_URL"]
    chrome_bin = os.getenv("CHROME_BIN", "/usr/bin/chromium")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=chrome_bin,
            args=["--disable-gpu"],
        )
        page = await browser.new_page()
        try:
            await page.goto(url, timeout=15000, wait_until="domcontentloaded")
            text = await page.inner_text("body")
            print(" ".join(text.split())[:3000])
        finally:
            await browser.close()

asyncio.run(main())
""".strip()


async def sandboxed_navigate_and_extract(url: str) -> str:
    """Loads a URL inside the container browser and extracts text content."""
    cmd = f"agent-browser read {shlex.quote(url)}"
    code, output = await exec_in_sandbox(cmd, timeout=25.0)
    if code != 0:
        # Use Playwright with system Chromium when agent-browser fails.
        py_cmd = f"DOT_TARGET_URL={shlex.quote(url)} python3 -c {shlex.quote(_FALLBACK_SCRIPT)}"
        fallback_code, fallback_out = await exec_in_sandbox(py_cmd, timeout=30.0)
        if fallback_code == 0:
            return fallback_out.strip()
        return f"Browser navigation failed: {output.strip()}"
    return output.strip()


async def sandboxed_search_web(query: str) -> str:
    """Executes a search query and extracts primary search snippets."""
    encoded_query = urllib.parse.quote_plus(query)
    search_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
    return await sandboxed_navigate_and_extract(search_url)


async def sandboxed_screenshot(url: str, output_name: str = "screenshot.png") -> str:
    """Captures a screenshot of a webpage and saves it to the workspace."""
    safe_name = Path(output_name).name
    if not safe_name or safe_name in (".", ".."):
        safe_name = "screenshot.png"
    output_path = f"/workspace/{safe_name}"
    cmd = f"agent-browser screenshot --path {shlex.quote(output_path)} {shlex.quote(url)}"
    code, output = await exec_in_sandbox(cmd, timeout=25.0)
    if code != 0:
        return f"Screenshot failed: {output.strip()}"
    return f"Screenshot saved to {output_path}"
