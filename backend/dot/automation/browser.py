from fastmcp import FastMCP, Context
from fastmcp.client.sampling import SamplingMessage
from mcp.types import ImageContent, TextContent
from playwright.async_api import async_playwright
import webbrowser
import urllib.parse
import re
import httpx
import base64
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

# Single persistent browser session for automation tools.
# Automation tools act on this shared state.
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
    """Navigate the active browser to a specified website or web address.

    Use this to open URLs, visit domains, load web pages, or begin web research tasks.

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


def _decode_bing_url(url: str) -> str:
    """Decodes Bing redirect links to obtain direct target URLs."""
    if "u=" in url:
        b64 = url.split("u=")[1].split("&")[0]
        if b64.startswith("a1"):
            b64 = b64[2:]
        b64 += "=" * (-len(b64) % 4)
        try:
            return base64.b64decode(b64).decode("utf-8", errors="ignore")
        except Exception:
            pass
    return url


@mcp.tool
async def search_web(query: str, max_results: int = 4) -> dict:
    """Searches the web for links and information.

    Returns organic search results with titles, URLs, and snippets.
    """
    clean_query = query.strip()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }

    # 1. Fast organic search via DuckDuckGo Lite HTTP request.
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            resp = await client.post(
                "https://lite.duckduckgo.com/lite/",
                data={"q": clean_query},
                headers=headers
            )
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                items = []
                for tr in soup.select("table tr"):
                    link = tr.select_one("a.result-link")
                    snippet_td = tr.select_one("td.result-snippet")
                    if link and link.get_text(strip=True):
                        raw_href = link.get("href", "")
                        title_text = link.get_text(strip=True)
                        items.append({"title": title_text, "url": raw_href, "snippet": ""})
                    elif snippet_td and items:
                        snippet_text = snippet_td.get_text(strip=True)[:250]
                        items[-1]["snippet"] = snippet_text

                if items:
                    return {
                        "success": True,
                        "query": clean_query,
                        "results": items[:max_results],
                        "instruction": "Search completed. Pick the best URL from 'results' and call 'browser_navigate' to load it, or use snippets to answer.",
                        "error": None
                    }
    except Exception as e:
        print(f"[Warning] DuckDuckGo Lite search failed: {e}", file=sys.stderr)

    # 2. Secondary fallback via direct Bing HTTP request.
    try:
        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
            resp = await client.get(
                f"https://www.bing.com/search?q={urllib.parse.quote_plus(clean_query)}",
                headers=headers
            )
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                items = []
                for li in soup.select("li.b_algo"):
                    title_a = li.select_one("h2 a")
                    snippet_p = li.select_one("div.b_caption p, p")
                    if title_a and title_a.get_text(strip=True):
                        raw_href = title_a.get("href", "")
                        clean_url = _decode_bing_url(raw_href)
                        title_text = title_a.get_text(strip=True)
                        snippet_text = snippet_p.get_text(strip=True)[:250] if snippet_p else ""
                        items.append({"title": title_text, "url": clean_url, "snippet": snippet_text})
                if items:
                    return {
                        "success": True,
                        "query": clean_query,
                        "results": items[:max_results],
                        "instruction": "Search completed. Pick the best URL from 'results' and call 'browser_navigate' to load it, or use snippets to answer.",
                        "error": None
                    }
    except Exception as e:
        print(f"[Warning] Direct Bing search failed: {e}", file=sys.stderr)

    # 3. Tertiary fallback via Wikipedia OpenSearch API.
    try:
        wiki_headers = {"User-Agent": "DotAssistant/1.0 (Desktop Agent; contact: dev@dot.ai)"}
        async with httpx.AsyncClient(timeout=4.0, follow_redirects=True, headers=wiki_headers) as client:
            wiki_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote_plus(clean_query)}&limit={max_results}&format=json"
            wiki_resp = await client.get(wiki_url)
            if wiki_resp.status_code == 200:
                wiki_data = wiki_resp.json()
                if len(wiki_data) >= 4 and wiki_data[1]:
                    wiki_items = []
                    for w_title, w_desc, w_link in zip(wiki_data[1], wiki_data[2], wiki_data[3]):
                        wiki_items.append({"title": w_title, "url": w_link, "snippet": w_desc or w_title})
                    if wiki_items:
                        return {
                            "success": True,
                            "query": clean_query,
                            "results": wiki_items[:max_results],
                            "instruction": "Search completed via Wikipedia. Pick the best URL or use snippets to answer.",
                            "error": None
                        }
    except Exception as e:
        print(f"[Warning] Wikipedia fallback search failed: {e}", file=sys.stderr)

    # 4. Quaternary fallback via Playwright.
    try:
        page = await _ensure_browser()
        q = urllib.parse.quote_plus(clean_query)
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

        for item in results:
            item["url"] = _decode_bing_url(item.get("url", ""))

        return {
            "success": True,
            "query": clean_query,
            "results": results[:max_results],
            "instruction": "Search completed. Pick the best URL from 'results' and call 'browser_navigate' to load it, or use snippets to answer.",
            "error": None
        }
    except Exception as e:
        return {"success": False, "query": clean_query, "results": [], "error": str(e)}


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
async def screenshot(ctx: Context = None, question: str = "Describe what's visible in the browser viewport.") -> dict:
    """
    Capture a screenshot of the automated browser webpage and describe it.
    DO NOT use this to capture the user's computer monitor, desktop, or active OS windows.
    Use os_tools_os_take_screenshot to capture and describe the user's physical screen or desktop.

    Args:
        question (str, optional): Focus for the description. Defaults to general description.

    Returns:
        dict: A status dictionary containing a text description in 'detail'.
    """
    try:
        page = await _ensure_browser()
        screenshot_bytes = await page.screenshot(full_page=False, timeout=5000)
        import base64
        encoded = base64.b64encode(screenshot_bytes).decode("utf-8")
        image_url = f"data:image/png;base64,{encoded}"

        description = None
        try:
            from dot.core.llm import async_llm
            description = await async_llm(
                query=question,
                image_url=image_url,
                system_prompt="Describe what is visible in this browser screenshot in 2-3 concise sentences.",
            )
        except Exception:
            description = None

        if not description and ctx and hasattr(ctx, "session") and ctx.session:
            try:
                import warnings
                from fastmcp.client.sampling import SamplingMessage
                from mcp.types import ImageContent, TextContent
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    sample_res = await ctx.session.create_message(
                        messages=[
                            SamplingMessage(
                                role="user",
                                content=ImageContent(type="image", data=encoded, mime_type="image/png"),
                            ),
                            SamplingMessage(
                                role="user",
                                content=TextContent(type="text", text=question),
                            ),
                        ],
                        system_prompt="Describe what is visible in this browser screenshot in 2-3 concise sentences.",
                        max_tokens=200,
                    )
                if hasattr(sample_res, "content"):
                    description = sample_res.content.text if hasattr(sample_res.content, "text") else str(sample_res.content)
            except Exception:
                pass

        if not description:
            description = "Browser screenshot captured successfully."

        return {"success": True, "detail": description, "error": None}
    except Exception as e:
        return {"success": False, "detail": None, "error": str(e)}


@mcp.tool
async def snapshot() -> dict:
    """Inspect and return interactive elements on the current webpage.

    Returns a list of links, buttons, headings, and input fields with roles and names.
    Call this before clicking or filling to locate exact element identifiers.

    Returns:
        dict: A status dictionary where detail contains up to 40 interactive elements.
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
async def click(
    role: Optional[str] = None,
    name: Optional[str] = None,
    selector: Optional[str] = None,
    text: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    """Click a button, link, tab, or interactive element on the active webpage.

    Specify either an ARIA role and accessible name, a CSS selector, or visible text.
    Use this to follow links, submit forms, switch tabs, or activate controls.
    Call the snapshot tool first to inspect available elements on the page.

    Args:
        role (str, optional): The ARIA role of the element, such as link, button, or tab.
        name (str, optional): The visible text or accessible label of the element.
        selector (str, optional): A CSS selector targeting the element directly.
        text (str, optional): The visible text of the link, button, or tab to click.
        description (str, optional): A short description of the clicked element.

    Returns:
        dict: A status dictionary confirming the click action or error details.
    """
    try:
        page = await _ensure_browser()
        locator = None
        target_desc = ""

        # Normalize text and name parameters
        target_text = name or text or description

        # Handle selector if provided
        if selector:
            clean_selector = selector
            if ":contains(" in clean_selector:
                clean_selector = clean_selector.replace(":contains(", ":has-text(")
            try:
                cand = page.locator(clean_selector)
                if await cand.count() > 0:
                    locator = cand
                    target_desc = f"selector '{clean_selector}'"
            except Exception:
                pass

        # Try ARIA role and name
        if not locator and role and target_text:
            try:
                cand = page.get_by_role(role, name=target_text)
                if await cand.count() > 0:
                    locator = cand
                    target_desc = f"{role} '{target_text}'"
            except Exception:
                pass

        # Try visible text matching
        if not locator and target_text:
            try:
                cand = page.get_by_text(target_text)
                if await cand.count() > 0:
                    locator = cand
                    target_desc = f"text '{target_text}'"
            except Exception:
                pass

        # Try pure role if no text
        if not locator and role:
            try:
                cand = page.get_by_role(role)
                if await cand.count() > 0:
                    locator = cand
                    target_desc = f"role '{role}'"
            except Exception:
                pass

        if not locator:
            if selector:
                clean_selector = selector.replace(":contains(", ":has-text(")
                locator = page.locator(clean_selector)
                target_desc = f"selector '{clean_selector}'"
            elif target_text:
                locator = page.get_by_text(target_text)
                target_desc = f"text '{target_text}'"
            else:
                current_url = getattr(page, "url", "unknown") if page else "unknown"
                return {
                    "success": False,
                    "detail": None,
                    "error": (
                        f"Provide a selector, role, name, or text to click an element on page '{current_url}'. "
                        "To click a window, video, or button on your desktop monitor, use os_click_text."
                    )
                }

        # Prefer visible elements to avoid targeting hidden dropdowns or menus.
        try:
            visible_cand = locator.locator("visible=true")
            if await visible_cand.count() > 0:
                locator = visible_cand
        except Exception:
            pass

        # Click the first matching element to prevent strict mode violations.
        target = locator.first
        await target.click(timeout=5000)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=4000)
        except Exception:
            pass
        return {"success": True, "detail": f"clicked {target_desc}", "error": None}
    except Exception as e:
        current_url = getattr(page, "url", "unknown") if page else "unknown"
        return {
            "success": False,
            "detail": None,
            "error": (
                f"Click failed on {target_desc or 'element'} on page '{current_url}': {str(e)}. "
                "If the target window is open on the desktop monitor outside this browser, "
                "use os_click_text or os_mouse_click."
            )
        }


@mcp.tool
async def fill(
    text: str,
    role: Optional[str] = None,
    name: Optional[str] = None,
    selector: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    """Type text into an input field or search box on the active webpage.

    Specify either an ARIA role and accessible name, or a CSS selector.
    Use this to enter search queries, login data, or form inputs.
    Call the snapshot tool first to inspect available form inputs.

    Args:
        text (str): The text string to enter into the field.
        role (str, optional): The ARIA role of the input, such as textbox or searchbox.
        name (str, optional): The placeholder, label, or accessible name of the input.
        selector (str, optional): A CSS selector targeting the input element directly.
        description (str, optional): A short description of the input field.

    Returns:
        dict: A status dictionary confirming the fill action or error details.
    """
    try:
        page = await _ensure_browser()
        locator = None
        target_desc = ""

        if selector:
            clean_selector = selector.replace(":contains(", ":has-text(")
            locator = page.locator(clean_selector).first
            target_desc = f"selector '{clean_selector}'"
        elif role and name:
            effective_roles = [role]
            if role in ("input", "search", "searchbox", "field"):
                effective_roles = ["textbox", "combobox", "searchbox"]

            for r in effective_roles:
                try:
                    candidate = page.get_by_role(r, name=name).first
                    if await candidate.count() > 0:
                        locator = candidate
                        target_desc = f"{r} '{name}'"
                        break
                except Exception:
                    continue

            if not locator:
                try:
                    candidate = page.get_by_placeholder(name).first
                    if await candidate.count() > 0:
                        locator = candidate
                        target_desc = f"placeholder '{name}'"
                except Exception:
                    pass
                if not locator:
                    locator = page.locator(f"input[name='{name}'], input#{name}, textarea[name='{name}']").first
                    target_desc = f"input '{name}'"
        elif name:
            locator = page.get_by_placeholder(name).first
            target_desc = f"placeholder '{name}'"
        else:
            return {
                "success": False,
                "detail": None,
                "error": "Provide either (role and name) or selector to fill an input."
            }

        await locator.fill(text, timeout=5000)
        return {"success": True, "detail": f"filled {target_desc} with text", "error": None}
    except Exception as e:
        return {"success": False, "detail": f"fill failed on {target_desc or 'input'}", "error": str(e)}


@mcp.tool
async def extract_text(
    role: Optional[str] = None,
    name: Optional[str] = None,
    url: Optional[str] = None,
    selector: Optional[str] = None,
    text: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    """Read and extract visible text content from the active webpage.

    Call with no arguments to extract the full text of the current page or article.
    Provide a selector, or a role and name, to extract text from a specific element or headline.
    Use this to read search results, articles, documentation, or post-click webpage updates.

    Args:
        role (str, optional): The ARIA role of a specific element to extract.
        name (str, optional): The accessible label or text of the target element.
        url (str, optional): An optional web address to load before extracting text.
        selector (str, optional): A CSS selector targeting specific text elements.
        text (str, optional): Optional text filter for matching elements.
        description (str, optional): A description of the target content to extract.

    Returns:
        dict: A status dictionary containing the extracted text in detail.
    """
    try:
        page = await _ensure_browser()
        if url and (page.url != url and not (page.url or "").rstrip("/").endswith(url.rstrip("/"))):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass

        extracted = None
        if selector:
            clean_selector = selector.replace(":contains(", ":has-text(")
            try:
                loc = page.locator(clean_selector)
                count = await loc.count()
                if count > 1:
                    texts = await loc.all_inner_texts()
                    extracted = "\n".join(t.strip() for t in texts if t.strip())
                elif count == 1:
                    extracted = await loc.first.inner_text(timeout=3000)
            except Exception:
                extracted = None

        target_name = name or text
        if not extracted and role and target_name:
            try:
                locator = page.get_by_role(role, name=target_name).first
                extracted = await locator.inner_text(timeout=3000)
            except Exception:
                extracted = None

        if not extracted:
            extracted = await page.inner_text("body", timeout=5000)

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
            "detail": f"{header}{extracted.strip()}",
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
    mcp.run(show_banner=False)