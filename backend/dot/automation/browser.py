from fastmcp import FastMCP, Context
from fastmcp.client.sampling import SamplingMessage
from mcp.types import ImageContent, TextContent
from playwright.async_api import async_playwright
import webbrowser
import urllib.parse
import re
import httpx
from bs4 import BeautifulSoup
from typing import Optional
import socket
import sys
import os
import json

# Configure UTF-8 encoding for standard streams to prevent charmap errors on Windows.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def _is_port_open(port: int = 9222, host: str = "127.0.0.1", timeout: float = 0.05) -> bool:
    """Verifies that the specified port accepts TCP connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False

mcp = FastMCP(name="Dot Browser Automation")

# Single persistent browser/page for the session — automation tools
# act on this shared state, not a fresh browser per call.
_playwright = None
_browser = None
_page = None
_current_headless = None

TOOL_DEPENDENCIES = {
    "browser_click": ["browser_snapshot"],
    "browser_fill": ["browser_snapshot"],
}

from dot.config.settings import is_browser_headless


async def _ensure_browser():
    global _playwright, _browser, _page, _current_headless

    desired_headless = is_browser_headless()

    # Verify if existing browser and page instances are still open and connected
    is_alive = False
    if _page is not None and _browser is not None:
        try:
            if not _page.is_closed() and _browser.is_connected():
                if _current_headless is None or _current_headless == desired_headless:
                    is_alive = True
        except Exception:
            is_alive = False

    if is_alive:
        return _page

    # Clean up any stale handles
    try:
        if _page: await _page.close()
    except Exception: pass
    try:
        if _browser: await _browser.close()
    except Exception: pass
    try:
        if _playwright: await _playwright.stop()
    except Exception: pass

    _page = None
    _browser = None
    _playwright = None

    _playwright = await async_playwright().start()
    
    connected_cdp = False
    if not desired_headless and _is_port_open(9222):
        try:
            _browser = await _playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
            context = _browser.contexts[0]
            open_pages = [p for p in context.pages if not p.is_closed()]
            _page = open_pages[0] if open_pages else await context.new_page()
            connected_cdp = True
            _current_headless = False
            print("[System] Connected to active daily browser session.", file=sys.stderr)
        except Exception as e:
            print(f"[System] CDP connection attempt failed: {e}", file=sys.stderr)

    if not connected_cdp:
        launched = False
        last_launch_err = None
        # Try installed Google Chrome first, then Microsoft Edge, then bundled Chromium
        for channel in ["chrome", "msedge", None]:
            try:
                launch_kwargs = {"headless": desired_headless}
                if channel:
                    launch_kwargs["channel"] = channel
                _browser = await _playwright.chromium.launch(**launch_kwargs)
                _page = await _browser.new_page(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                )
                launched = True
                _current_headless = desired_headless
                break
            except Exception as err:
                last_launch_err = err
                continue

        if not launched:
            print(f"[Error] Playwright launch failed: {last_launch_err}", file=sys.stderr)
            raise RuntimeError(f"Playwright chromium failed to launch: {last_launch_err}. Please ensure Google Chrome is installed.")

    return _page


async def _prune_snapshot(node, max_depth=6, depth=0):
    """Reduces Playwright's accessibility tree to role+name+value,
    dropping generic/empty nodes that add noise without signal."""
    if node is None or depth > max_depth:
        return None

    role = node.get("role")
    name = node.get("name", "")

    # skip structurally uninteresting nodes with no name and no children worth keeping
    pruned_children = []
    for child in node.get("children", []) or []:
        pruned_child = _prune_snapshot(child, max_depth, depth + 1)
        if pruned_child:
            pruned_children.append(pruned_child)

    if role in ("generic", "none") and not name and not pruned_children:
        return None

    result = {"role": role}
    if name:
        result["name"] = name
    if node.get("value"):
        result["value"] = node["value"]
    if pruned_children:
        result["children"] = pruned_children
    return result


@mcp.tool
async def navigate(url: str) -> dict:
    """Navigate the active browser page to a specified URL.
    
    Args:
        url (str): The complete web address to navigate to.
        
    Returns:
        dict: A status dictionary containing success, detail, and error keys.
    """
    try:
        page = await _ensure_browser()
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        return {"success": True, "detail": f"navigated to {url}", "error": None}
    except Exception as e:
        return {"success": False, "detail": f"navigation to {url} failed", "error": str(e)}


@mcp.tool
async def ai_background_load_page(url: str) -> dict:
    """Navigate the active browser page to a specified URL (legacy alias)."""
    return await navigate(url)


@mcp.tool
async def play_video(query: str) -> dict:
    """Find and play a video or song on YouTube.
    
    Args:
        query (str): The video or song name to find and play.
        
    Returns:
        dict: A status dictionary indicating if playback succeeded.
    """
    clean_query = query.lower()
    for prefix in ["play", "open", "watch", "listen to", "video of", "song"]:
        if clean_query.startswith(prefix):
            clean_query = clean_query[len(prefix):].strip()
    clean_query = clean_query.replace("on youtube", "").replace("in youtube", "").replace("youtube", "").strip()
    if not clean_query:
        clean_query = query.strip()

    target_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(clean_query)}"
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        }
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(target_url, headers=headers)
            matches = re.findall(r"/watch\?v=([a-zA-Z0-9_-]{11})", resp.text)
            if matches:
                target_url = f"https://www.youtube.com/watch?v={matches[0]}"
    except Exception:
        pass

    try:
        webbrowser.open(target_url)
        return {
            "success": True,
            "detail": f"Playing '{clean_query}' on YouTube: {target_url}",
            "url": target_url,
            "terminal": True,
            "error": None
        }
    except Exception as e:
        return {"success": False, "detail": None, "error": str(e), "terminal": False}


@mcp.tool
async def search_web(query: str, max_results: int = 4) -> dict:
    """Search the web for links and information.
    
    Args:
        query (str): The search keywords or question.
        max_results (int, optional): Maximum search results to return. Defaults to 4.
        
    Returns:
        dict: A dictionary containing search results with titles, URLs, and snippets.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
    
    # Fast organic search via DuckDuckGo HTML endpoint.
    try:
        from bs4 import BeautifulSoup
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                headers=headers
            )
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            items = []
            for div in soup.select("div.result"):
                title_a = div.select_one("a.result__a")
                snippet_a = div.select_one("a.result__snippet")
                if title_a:
                    href = title_a.get("href", "")
                    if "uddg=" in href:
                        href = urllib.parse.unquote(href.split("uddg=")[1].split("&")[0])
                    title = title_a.get_text(strip=True)
                    snippet = snippet_a.get_text(strip=True) if snippet_a else ""
                    if href and title and not href.startswith("/"):
                        items.append({"title": title, "url": href, "snippet": snippet[:250]})
            if items:
                return {
                    "success": True,
                    "query": query,
                    "results": items[:max_results],
                    "instruction": "Search completed. Pick the best URL from 'results' and call 'browser_navigate' to load it, or use snippets to answer.",
                    "error": None
                }
    except Exception as e:
        print(f"[Warning] Fast search failed ({e}), falling back to Playwright...", file=sys.stderr)

    # 2. Playwright Fallback via Bing
    try:
        page = await _ensure_browser()
        q = urllib.parse.quote_plus(query)
        await page.goto(f"https://www.bing.com/search?q={q}", wait_until="domcontentloaded", timeout=12000)
        await page.wait_for_timeout(1000)
        
        results = await page.evaluate('''() => {
            const items = [];
            for (const li of document.querySelectorAll('li.b_algo')) {
                const a = li.querySelector('h2 a');
                const p = li.querySelector('div.b_caption p, p');
                if (a && a.innerText.trim()) {
                    items.push({
                        title: a.innerText.trim(),
                        url: a.href,
                        snippet: p ? p.innerText.trim().slice(0, 250) : ''
                    });
                }
            }
            return items;
        }''')
        
        return {
            "success": True,
            "query": query,
            "results": results[:max_results],
            "instruction": "Search completed. Pick the best URL from 'results' and call 'browser_navigate' to load it, or use snippets to answer.",
            "error": None
        }
    except Exception as e:
        return {"success": False, "query": query, "results": [], "error": str(e)}


@mcp.tool
def open_in_browser(target: str) -> dict:
    """Open a URL or search query in the user's default desktop browser window.
    
    Args:
        target (str): Web address or search term to show to the human user.
        
    Returns:
        dict: A status dictionary confirming that the desktop browser opened.
    """
    try:
        if target.startswith("http://") or target.startswith("https://"):
            url = target
        else:
            search_query = urllib.parse.quote(f"!ducky {target}")
            url = f"https://duckduckgo.com/?q={search_query}"
        webbrowser.open(url)
        return {
            "success": True,
            "detail": f"opened '{target}' in desktop browser",
            "error": None,
            "terminal": True
        }
    except Exception as e:
        return {"success": False, "detail": None, "error": str(e), "terminal": False}


@mcp.tool
def open_desktop_tab_for_user(target: str) -> dict:
    """Open a URL or search query in the user's default desktop browser (legacy alias)."""
    return open_in_browser(target)

@mcp.tool
async def screenshot(ctx: Context, question: str = "Describe what's visible on screen.") -> dict:
    """
    ONLY use this to capture internal web pages inside the browser
    Capture a screenshot of the current browser viewport (only what's
    visibly on screen, not the full scrollable page) and have the vision
    model describe it in plain text. Use this when the user asks what's
    on screen, what a page looks like, or to describe visual content
    a text-only extraction (browser_extract_text) can't capture.
    

    Args:
        question (str, optional): What to focus on when describing the screenshot
            (e.g. "Is there a login button?", "What's the main headline?").
            Defaults to a general description.

    Returns:
        dict: A status dictionary where 'detail' contains a short TEXT description
        of the screenshot — never raw image bytes.
    """
    try:
        page = await _ensure_browser()
        screenshot_bytes = await page.screenshot(full_page=False, timeout=5000)
        import base64
        encoded = base64.b64encode(screenshot_bytes).decode("utf-8")
        result = await ctx.sample(
            messages=[
                SamplingMessage(
                    role="user",
                    content=ImageContent(type="image", data=encoded, mimeType="image/png"),
                ),
                SamplingMessage(
                    role="user",
                    content=TextContent(type="text", text=question),
                ),
            ],
            system_prompt="Describe the screenshot in 2-3 concise sentences.",
            max_tokens=200,
        )
        description = result.text if hasattr(result, "text") else str(result)
        return {"success": True, "detail": description, "error": None}
    except Exception as e:
        return {"success": False, "detail": None, "error": str(e)}


@mcp.tool
async def snapshot() -> dict:
    """
    Get the current state of the webpage. Use this to see search 
    results, headings, and links before clicking or extracting text.
    Returns a pruned list of interactive and structural DOM elements.
    
    Returns:
        dict: A status dictionary where 'detail' contains a list of up to 40 interactive elements (tag, text, href, name).
    """
    try:
        page = await _ensure_browser()
        
        # Inject JavaScript to grab interactive and structural elements
        js_code = """
        () => {
            let elements = Array.from(document.querySelectorAll('a, h1, h2, h3, button, input'));
            return elements.map(el => ({
                tag: el.tagName.toLowerCase(),
                text: el.innerText.trim(),
                href: el.href || null,
                name: el.name || el.id || el.getAttribute('aria-label') || null
            })).filter(el => el.text !== ''); // Remove empty elements
        }
        """
        
        elements = await page.evaluate(js_code)
        
        # Limit to the first 40 elements to prevent blowing up the LLM's context window
        pruned_elements = elements[:40] 
        
        return {"success": True, "detail": pruned_elements, "error": None}
    except Exception as e:
        return {"success": False, "detail": None, "error": str(e)}


@mcp.tool
async def click(role: str, name: str) -> dict:
    """Click a button, link, or element on the active webpage.
    
    Use the snapshot tool first to inspect the element role and accessible name.
    
    Args:
        role (str): The HTML tag or ARIA role of the element to click.
        name (str): The visible text or accessible name of the element.
        
    Returns:
        dict: A status dictionary confirming the click action or error details.
    """
    try:
        page = await _ensure_browser()
        locator = page.get_by_role(role, name=name)
        await locator.click(timeout=5000)
        await page.wait_for_load_state("domcontentloaded", timeout=5000)
        return {"success": True, "detail": f"clicked {role} '{name}'", "error": None}
    except Exception as e:
        return {"success": False, "detail": f"click failed on {role} '{name}'", "error": str(e)}


@mcp.tool
async def fill(role: str, name: str, text: str) -> dict:
    """Type text into an input field on the active webpage.
    
    Use the snapshot tool first to inspect the field role and accessible name.
    
    Args:
        role (str): The HTML tag or ARIA role of the input element.
        name (str): The visible placeholder or accessible name of the input field.
        text (str): The exact text string to enter.
        
    Returns:
        dict: A status dictionary confirming the fill action or error details.
    """
    try:
        page = await _ensure_browser()
        locator = page.get_by_role(role, name=name)
        await locator.fill(text, timeout=5000)
        return {"success": True, "detail": f"filled {role} '{name}' with text", "error": None}
    except Exception as e:
        return {"success": False, "detail": f"fill failed on {role} '{name}'", "error": str(e)}


@mcp.tool
async def extract_text(role: str = None, name: str = None) -> dict:
    """
    Read and extract the visible text content from the active webpage.
    To read the full article or page, call this with NO arguments.
    Only provide role and name if targeting a specific heading/link found in snapshot.
    
    Args:
        role (str, optional): The HTML tag or role of a specific element to extract from. Defaults to None.
        name (str, optional): The accessible name or text of a specific element to extract from. Defaults to None.
        
    Returns:
        dict: A status dictionary where 'detail' contains the extracted text string.
    """
    try:
        page = await _ensure_browser()
        text = None
        if role and name:
            try:
                locator = page.get_by_role(role, name=name)
                text = await locator.inner_text(timeout=3000)
            except Exception:
                # If specific locator timed out or role doesn't exist, fall back to page body
                pass

        if not text:
            text = await page.inner_text("body", timeout=5000)

        current_url = page.url or "unknown"
        try:
            page_title = await page.title()
        except Exception:
            page_title = "Untitled Page"

        header = f"[Active Webpage: '{page_title}' | URL: {current_url}]\n"
        return {
            "success": True,
            "url": current_url,
            "title": page_title,
            "detail": f"{header}{text}",
            "error": None
        }
    except Exception as e:
        return {"success": False, "detail": None, "error": str(e)}


@mcp.tool
async def close_browser() -> dict:
    """
    Close the active browser window and shut down the Playwright session once the task is finished.
    Call this when you have finished your browsing task or extracted the necessary data.
    """
    global _playwright, _browser, _page
    try:
        if _page:
            try: await _page.close()
            except Exception: pass
        if _browser:
            try: await _browser.close()
            except Exception: pass
        if _playwright:
            try: await _playwright.stop()
            except Exception: pass
        _page = None
        _browser = None
        _playwright = None
        return {"success": True, "detail": "Browser closed successfully.", "error": None}
    except Exception as e:
        _page = None
        _browser = None
        _playwright = None
        return {"success": False, "detail": None, "error": str(e)}


if __name__ == "__main__":
    mcp.run()