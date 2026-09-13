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

mcp = FastMCP(name="Dot Browser Automation")

# Single persistent browser/page for the session — automation tools
# act on this shared state, not a fresh browser per call.
_playwright = None
_browser = None
_page = None

TOOL_DEPENDENCIES = {
    "browser_click": ["browser_snapshot"],
    "browser_fill": ["browser_snapshot"],
   
}

async def _ensure_browser():
    global _playwright, _browser, _page

    # Verify if existing browser and page instances are still open and connected
    is_alive = False
    if _page is not None and _browser is not None:
        try:
            if not _page.is_closed() and _browser.is_connected():
                is_alive = True
        except Exception:
            is_alive = False

    if not is_alive:
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
        
        try:
            # First, try to connect to your active daily browser
            _browser = await _playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
            context = _browser.contexts[0]
            
            open_pages = [p for p in context.pages if not p.is_closed()]
            if open_pages:
                _page = open_pages[0] 
            else:
                _page = await context.new_page()
            print("[System] Successfully connected to active browser session.")
            
        except Exception as e:
            # Fallback: If port 9222 isn't open, launch a new browser
            print(f"[System] CDP connection failed ({e}). Falling back to a new browser instance.")
            try:
                _browser = await _playwright.chromium.launch(headless=False)
                _page = await _browser.new_page(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                )
            except Exception as launch_err:
                print(f"[Error] Playwright browser launch failed: {launch_err}. Please run 'playwright install chromium'.")
                raise RuntimeError(f"Playwright chromium browser not found or failed to launch ({launch_err}). Run 'playwright install chromium'.")
            
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
async def ai_background_load_page(url: str) -> dict:
    """
    Navigate the browser to a specified URL to read, extract, or summarize its content.
    
    Args:
        url (str): The complete web address to navigate to (e.g., 'https://github.com' or 'https://www.deeplearning.ai/courses/agentic-ai').
        
    Returns:
        dict: A status dictionary containing 'success', 'detail', and 'error' keys.
    """
    try:
        page = await _ensure_browser()
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        return {"success": True, "detail": f"navigated to {url}", "error": None}
    except Exception as e:
        return {"success": False, "detail": f"navigation to {url} failed", "error": str(e)}

@mcp.tool
async def search_web(query: str, max_results: int = 4) -> dict:
    """
    Search the web for a given query when a direct URL is NOT provided.
    Returns the top organic search results containing their titles, snippets, and clean destination URLs.
    Use this to find relevant links, then use 'browser_ai_background_load_page' with the chosen URL.
    
    Args:
        query (str): The search query to look up (e.g. 'Andrew Ng latest news' or 'deeplearning ai agentic course').
        max_results (int, optional): The maximum number of search results to return. Defaults to 4.
        
    Returns:
        dict: A dictionary containing 'success', 'results' (list of {title, url, snippet}), and 'instruction'.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
    
    # 1. Fast, reliable organic HTML search (avoids connection drops and CAPTCHAs)
    try:
        from bs4 import BeautifulSoup
        resp = httpx.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers=headers,
            timeout=8.0
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
                    "instruction": "Search completed. Pick the best URL from 'results' and call 'browser_ai_background_load_page' to navigate to it, or use the snippets to answer.",
                    "error": None
                }
    except Exception as e:
        print(f"[Warning] Fast search failed ({e}), falling back to Playwright...")

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
            "instruction": "Search completed. Pick the best URL from 'results' and call 'browser_ai_background_load_page' to navigate to it, or use the snippets to answer.",
            "error": None
        }
    except Exception as e:
        return {"success": False, "query": query, "results": [], "error": str(e)}

@mcp.tool
def open_desktop_tab_for_user(target: str) -> dict:
    """
    Launch an external browser window on the user's desktop to display a URL or search query to the human user.
    CRITICAL: This is a FIRE-AND-FORGET action that opens the user's OS browser!
    DO NOT USE THIS TOOL IF:
    - You need to read, inspect, extract, or summarize content from a web page.
    - The user asked a question, requested code examples, or needs an explanation.
    - For reading web pages, ALWAYS use 'browser_ai_background_load_page' followed by 'browser_extract_text'.
    ONLY use this tool when the user EXPLICITLY asks to open a site or search for them to view in their own desktop browser (e.g., 'open youtube in my browser', 'launch reddit for me').
    
    Args:
        target (str): The search query or website name to open for the user.
        
    Returns:
        dict: A status dictionary indicating if the local browser successfully opened.
    """
    print(f"Opening quick search for '{target}' via !ducky ")
    try:
        searchQuery = urllib.parse.quote(f"!ducky {target}")
        url = f"https://duckduckgo.com/?q={searchQuery}"
        webbrowser.open(url)
        return {
            "success": True,
            "detail": f"opened quick search for '{target}'",
            "error": None,
            "terminal": True
        }
    except Exception as e:
        return {"success": False, "detail": None, "error": str(e), "terminal": False}

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
    """
    Click a button, link, or search result on the active webpage. Requires: browser_browser_snapshot.
    CRITICAL: You MUST use browser_snapshot first to find the exact 'role' (tag) and 'name' (text/aria-label) 
    of the element. NEVER guess the role or name.
    
    Args:
        role (str): The HTML tag or ARIA role of the element to click (e.g., 'a', 'button').
        name (str): The visible text or accessible name of the element to click.
        
    Returns:
        dict: A status dictionary confirming the click action or containing error details.
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
    """
    Type text into a search box, form field, or input on the current webpage. 
    CRITICAL: You MUST use browser_snapshot first to find the exact 'role' and 'name' 
    of the input element. NEVER guess the role or name.
    
    Args:
        role (str): The HTML tag or ARIA role of the input element (e.g., 'input').
        name (str): The visible text, placeholder, or accessible name of the input field.
        text (str): The exact string of text to type into the field.
        
    Returns:
        dict: A status dictionary confirming the fill action or containing error details.
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