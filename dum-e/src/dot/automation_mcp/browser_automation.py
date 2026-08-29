from fastmcp import FastMCP, Context
from fastmcp.client.sampling import SamplingMessage
from mcp.types import ImageContent, TextContent
from playwright.async_api import async_playwright
import webbrowser
import urllib.parse
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
    if _page is None:
        _playwright = await async_playwright().start()
        
        try:
            # First, try to connect to your active daily browser
            _browser = await _playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
            context = _browser.contexts[0]
            
            if context.pages:
                _page = context.pages[0] 
            else:
                _page = await context.new_page()
            print("[System] Successfully connected to active browser session.")
            
        except Exception as e:
            # Fallback: If port 9222 isn't open, launch a new browser
            print(f"[System] CDP connection failed ({e}). Falling back to a new browser instance.")
            try:
                _browser = await _playwright.chromium.launch(headless=False)
                _page = await _browser.new_page()
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
    USE ONLY FOR COMPLEX PLANS
    Navigate the active browser session to a specified URL.
    
    Args:
        url (str): The complete web address to navigate to (e.g., 'https://github.com').
        
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
def open_desktop_tab_for_user(target: str) -> dict:
    """
    Open a quick web search or jump directly to a site in the user's
    default browser using DuckDuckGo bangs. This is a FIRE-AND-FORGET
    action — once it succeeds, the task is complete, no follow-up needed.
    
    Args:
        target (str): The search query or website name (e.g., 'Shape of You', 'Python documentation').
        
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
    If role and name are provided, it extracts text from that specific element.
    If no arguments are provided, it extracts all visible text from the entire page body.
    
    Args:
        role (str, optional): The HTML tag or role of a specific element to extract from. Defaults to None.
        name (str, optional): The accessible name or text of a specific element to extract from. Defaults to None.
        
    Returns:
        dict: A status dictionary where 'detail' contains the extracted text string.
    """
    try:
        page = await _ensure_browser()
        if role and name:
            locator = page.get_by_role(role, name=name)
            text = await locator.inner_text(timeout=5000)
        else:
            text = await page.inner_text("body", timeout=5000)
        return {"success": True, "detail": text, "error": None}
    except Exception as e:
        return {"success": False, "detail": None, "error": str(e)}


if __name__ == "__main__":
    mcp.run()