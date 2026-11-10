"""
Sandboxed browser automation module for Dot.
Executes browser automation inside the Docker container via agent-browser.
Uses zero GPU VRAM.
Complies with ASD-STE100 technical writing standards.
"""

import urllib.parse
from typing import Optional
from dot.sandbox.executor import exec_in_sandbox


async def sandboxed_navigate_and_extract(url: str) -> str:
    """Loads a URL inside the container browser and extracts text content."""
    cmd = f'agent-browser read "{url}"'
    code, output = await exec_in_sandbox(cmd, timeout=25.0)
    if code != 0:
        # Fallback to python extraction if agent-browser binary is unavailable
        fallback_script = f"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--disable-gpu', '--no-sandbox'])
        page = await browser.new_page()
        try:
            await page.goto('{url}', timeout=15000, wait_until='domcontentloaded')
            text = await page.inner_text('body')
            print(' '.join(text.split())[:3000])
        finally:
            await browser.close()
asyncio.run(main())
"""
        py_cmd = f'python3 -c "{fallback_script.strip()}"'
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
    cmd = f'agent-browser screenshot --path "/workspace/{output_name}" "{url}"'
    code, output = await exec_in_sandbox(cmd, timeout=25.0)
    if code != 0:
        return f"Screenshot failed: {output.strip()}"
    return f"Screenshot saved to /workspace/{output_name}"


