from fastmcp import FastMCP
from playwright.async_api import async_playwright

mcp = FastMCP(name="Dot Browser Automation")

# Single persistent browser/page for the session — automation tools
# act on this shared state, not a fresh browser per call.
_playwright = None
_browser = None
_page = None

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
            # Fallback: If port 9222 isn't open, just launch a new browser so the agent doesn't crash
            print(f"[System] CDP connection failed ({e}). Falling back to a new browser instance.")
            _browser = await _playwright.chromium.launch(headless=False)
            _page = await _browser.new_page()
            
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
async def browser_navigate(url: str) -> dict:
    """Navigate the browser to a URL."""
    try:
        page = await _ensure_browser()
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        return {"success": True, "detail": f"navigated to {url}", "error": None}
    except Exception as e:
        return {"success": False, "detail": f"navigation to {url} failed", "error": str(e)}


@mcp.tool
async def browser_snapshot() -> dict:
    """Get the current state of the webpage. Use this to see search 
    results, headings, and links before clicking or extracting text."""
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
async def browser_click(role: str, name: str) -> dict:
    """Click a button, link, or search result on the current webpage.
    CRITICAL: You MUST use browser_snapshot first to find the exact 'role' and 'name' 
    of the element. NEVER guess the role or name."""
    try:
        page = await _ensure_browser()
        locator = await page.get_by_role(role, name=name)
        locator.click(timeout=5000)
        await page.wait_for_load_state("domcontentloaded", timeout=5000)
        return {"success": True, "detail": f"clicked {role} '{name}'", "error": None}
    except Exception as e:
        return {"success": False, "detail": f"click failed on {role} '{name}'", "error": str(e)}


@mcp.tool
async def browser_fill(role: str, name: str, text: str) -> dict:
    """Type text into a search box, form field, or input on the current webpage. 
    CRITICAL: You MUST use browser_snapshot first to find the exact 'role' and 'name' 
    of the element. NEVER guess the role or name."""
    try:
        page = await _ensure_browser()
        locator = await page.get_by_role(role, name=name)
        locator.fill(text, timeout=5000)
        return {"success": True, "detail": f"filled {role} '{name}' with text", "error": None}
    except Exception as e:
        return {"success": False, "detail": f"fill failed on {role} '{name}'", "error": str(e)}


@mcp.tool
async def browser_extract_text(role: str = None, name: str = None) -> dict:
    """Read/extract the visible text content from the webpage or a 
    specific element — titles, search result text, article content.
    Use this to get the actual text/title of what's on screen."""
    try:
        page = await _ensure_browser()
        if role and name:
            locator = await page.get_by_role(role, name=name)
            text = locator.inner_text(timeout=5000)
        else:
            text = await page.inner_text("body", timeout=5000)
        return {"success": True, "detail": text, "error": None}
    except Exception as e:
        return {"success": False, "detail": None, "error": str(e)}


if __name__ == "__main__":
    mcp.run()