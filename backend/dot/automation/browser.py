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
from typing import Optional, List, Dict, Any
from pathlib import Path
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
_ACTIVE_SCRATCH_ELEMENTS: List[Dict[str, Any]] = []

TOOL_DEPENDENCIES = {
    "browser_click": ["browser_snapshot"],
    "browser_fill": ["browser_snapshot"],
}

from dot.config.settings import is_browser_headless
from dot.config.paths import LOGS_DIR


def _dump_to_scratch(elements: list, scratch_path: Optional[Path] = None) -> str:
    """Writes extracted webpage elements with coordinates and ref tags to scratch buffer.

    Complies with ASD-STE100 rules.
    """
    if scratch_path is None:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        scratch_path = LOGS_DIR / "scratch_page.md"
    else:
        scratch_path = Path(scratch_path)
        scratch_path.parent.mkdir(parents=True, exist_ok=True)

    lines = ["# Active Webpage Element Scratchpad\n"]
    current_section = None
    for el in elements:
        sec = el.get("section") or "General"
        if sec != current_section:
            current_section = sec
            lines.append(f"\n## Section: {sec}")
        ref = el.get("ref", "")
        tag = el.get("tag", "")
        role = el.get("role", "")
        text = el.get("text", "")
        coords = el.get("coords", {})
        coord_str = f"({coords.get('x', 0)}, {coords.get('y', 0)}, {coords.get('width', 0)}x{coords.get('height', 0)})"
        ref_prefix = f"[{ref}] " if ref else ""
        lines.append(f"- {ref_prefix}<{tag} role='{role}'> '{text}' @ {coord_str}")

    content = "\n".join(lines)
    scratch_path.write_text(content, encoding="utf-8")
    return str(scratch_path)


def _search_scratch_elements(
    query: str,
    elements: Optional[list] = None,
    tag_type: Optional[str] = None,
    section_hint: Optional[str] = None,
) -> list:
    """Filters cached scratch elements by query text, tag type, and section context.

    Complies with ASD-STE100 rules.
    """
    global _ACTIVE_SCRATCH_ELEMENTS
    items = elements if elements is not None else _ACTIVE_SCRATCH_ELEMENTS
    query_clean = query.strip().lower()
    matches = []

    for el in items:
        # Section hint filter
        if section_hint:
            sec = (el.get("section") or "").lower()
            if section_hint.lower() not in sec:
                continue

        # Tag type filter
        if tag_type:
            tgt = tag_type.strip().lower()
            el_tag = (el.get("tag") or "").lower()
            el_type = (el.get("type") or "").lower()
            el_role = (el.get("role") or "").lower()
            if tgt not in (el_tag, el_type, el_role):
                continue

        # Query match: prefer word boundary / exact matches first
        text = (el.get("text") or "").lower()
        name = (el.get("name") or "").lower()
        ref = (el.get("ref") or "").lower()
        pattern = rf"\b{re.escape(query_clean)}\b"

        is_match = (
            query_clean == text
            or query_clean == name
            or query_clean == ref
            or bool(re.search(pattern, text))
            or bool(re.search(pattern, name))
            or (not query_clean and (tag_type or section_hint))
        )
        if is_match:
            matches.append(el)

    return matches


def clean_readable_text(text: str, max_chars: int = 4000) -> str:
    """Extracts main content from raw page text or markdown.

    Complies with ASD-STE100 rules.
    """
    if not text:
        return ""

    # Strip HTML script, style, and tag boilerplate to prevent context pollution.
    cleaned_markup = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
    cleaned_markup = re.sub(r"<script[\s\S]*?</script>", "", cleaned_markup, flags=re.IGNORECASE)
    cleaned_markup = re.sub(r"<[^>]+>", " ", cleaned_markup)
    # Strip raw MediaWiki template blocks and leftover attribute fragments.
    cleaned_markup = re.sub(r"\{\{[\s\S]*?\}\}", "", cleaned_markup)
    cleaned_markup = re.sub(r'"\}\]\]\}>', "", cleaned_markup)

    lines = cleaned_markup.splitlines()

    # Strip Wikipedia sidebar navigation between article title and encyclopedia banner.
    wiki_banner_idx = None
    for idx, line in enumerate(lines):
        if "from wikipedia, the free encyclopedia" in line.strip().lower():
            wiki_banner_idx = idx
            break
    if wiki_banner_idx is not None:
        title_line = next((l.strip() for l in lines[:wiki_banner_idx] if re.match(r"^#\s+[^#]", l.strip())), None)
        lines = ([title_line, ""] if title_line else []) + lines[wiki_banner_idx + 1:]

    target_idx = None

    # Search for headings containing relevant content markers
    for idx, line in enumerate(lines):
        line_str = line.strip()
        if re.match(r"^#{1,3}\s+", line_str):
            line_lower = line_str.lower()
            if any(k in line_lower for k in ("quiz", "question", "article", "overview", "lesson", "main")):
                target_idx = idx
                break

    # If no marker matched, find the primary article title heading, skipping navigation headers
    if target_idx is None:
        for idx, line in enumerate(lines):
            line_str = line.strip()
            if re.match(r"^#\s+[^#]", line_str):
                line_lower = line_str.lower()
                if not any(k in line_lower for k in ("contents", "navigation", "menu", "sidebar")):
                    target_idx = idx
                    break

    if target_idx is not None:
        lines = lines[target_idx:]

    cleaned_lines = []
    empty_count = 0
    for line in lines:
        stripped = line.rstrip()
        if not stripped:
            empty_count += 1
            if empty_count <= 2:
                cleaned_lines.append("")
        else:
            empty_count = 0
            cleaned_lines.append(stripped)

    result = "\n".join(cleaned_lines).strip()
    if len(result) > max_chars:
        result = result[:max_chars].rstrip() + "\n...[truncated]"
    return result


def _build_compact_manifest(
    title: str,
    url: str,
    elements: list,
    max_elements: int = 30,
) -> str:
    """Builds a token-efficient summary of the page and primary interactive elements.

    Complies with ASD-STE100 rules.
    """
    lines = [f"Page: {title.strip()} ({url.strip()})"]

    # Prioritize form controls, buttons, radios, checkboxes, and headings
    actionable_roles = {"button", "radio", "checkbox", "textbox", "searchbox", "combobox", "submit"}
    actionable = [el for el in elements if el.get("role") in actionable_roles or el.get("tag") in ("button", "input", "select", "textarea")]
    headings = [el for el in elements if el.get("role") in ("heading",) or el.get("tag") in ("h1", "h2", "h3", "h4", "legend")]
    content_text = [el for el in elements if el.get("role") in ("paragraph", "text", "statictext") and len(el.get("text", "")) > 10]
    others = [el for el in elements if el not in actionable and el not in headings and el not in content_text]

    selected = []
    seen = set()
    # Prioritize headings, substantive text, actionable controls, then others
    for el in (headings[:8] + content_text[:6] + actionable + others):
        identifier = el.get("ref") or el.get("text")
        if identifier and identifier not in seen:
            seen.add(identifier)
            selected.append(el)
        if len(selected) >= max_elements:
            break

    current_section = None
    for el in selected:
        sec = el.get("section") or "General"
        if sec != current_section:
            current_section = sec
            lines.append(f"\n[{sec}]")

        ref = el.get("ref", "")
        role = el.get("role") or el.get("tag") or "element"
        text = el.get("text") or el.get("name") or ""
        ref_prefix = f"[{ref}] " if ref else ""
        lines.append(f"- {ref_prefix}{role} '{text}'")

    if len(elements) > len(selected):
        lines.append(f"\n... and {len(elements) - len(selected)} more controls cached in logs/scratch_page.md. Use 'probe_page' to search.")

    return "\n".join(lines).strip()


async def _extract_elements_with_coordinates(page) -> list:
    """Extracts interactive controls and bounding box coordinates from active page."""
    js_code = """
    () => {
        let targets = Array.from(document.querySelectorAll('a, button, input, select, textarea, [role="button"], [role="radio"], [role="checkbox"], [role="link"]'));

        function getSection(el) {
            let parent = el.closest('fieldset, form, section, article, div[class*="question"], div[class*="card"]');
            if (parent) {
                let h = parent.querySelector('h1, h2, h3, legend, [role="heading"]');
                if (h && h.innerText) return h.innerText.trim().slice(0, 80);
            }
            let prev = el;
            while (prev) {
                while (prev.previousElementSibling) {
                    prev = prev.previousElementSibling;
                    if (['H1', 'H2', 'H3', 'LEGEND'].includes(prev.tagName)) {
                        return prev.innerText.trim().slice(0, 80);
                    }
                }
                prev = prev.parentElement;
            }
            return "General";
        }

        let results = [];
        let idx = 1;
        for (let el of targets) {
            let rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0 || window.getComputedStyle(el).display === 'none') {
                continue;
            }
            let tag = el.tagName.toLowerCase();
            let role = el.getAttribute('role') || (tag === 'input' ? (el.type || 'text') : tag);
            let text = el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || el.title || '';
            text = text.trim();

            if ((tag === 'input' && (el.type === 'radio' || el.type === 'checkbox')) && !text) {
                if (el.labels && el.labels[0]) {
                    text = el.labels[0].innerText.trim();
                } else if (el.nextElementSibling && el.nextElementSibling.tagName === 'LABEL') {
                    text = el.nextElementSibling.innerText.trim();
                } else if (el.parentElement) {
                    text = el.parentElement.innerText.trim();
                }
            }

            let name = el.name || el.id || null;
            let type = el.type || (tag === 'button' ? 'button' : tag);

            results.push({
                ref: `@e${idx++}`,
                tag: tag,
                role: role,
                type: type,
                text: text.slice(0, 100),
                name: name,
                section: getSection(el),
                coords: {
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height)
                }
            });
            if (results.length >= 100) break;
        }
        return results;
    }
    """
    try:
        return await page.evaluate(js_code)
    except Exception:
        return []


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
            try:
                if _browser:
                    await _browser.close()
            except Exception:
                pass
            _browser = None
            _page = None

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
        pruned_child = await _prune_snapshot(child, max_depth, depth + 1)
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
async def navigate(url: str, auto_snapshot: bool = True) -> dict:
    """Navigate the active browser to a specified website or web address.

    Use this to open URLs, visit domains, load web pages, or begin web research tasks.
    When auto_snapshot is enabled, automatically captures interactive controls and writes them to scratch.md.

    Args:
        url (str): The complete web address to navigate to.
        auto_snapshot (bool): When True, automatically inspects elements and populates scratch.md.

    Returns:
        dict: A status dictionary containing success, detail, and error keys.
    """
    global _ACTIVE_SCRATCH_ELEMENTS
    clean_url = (url or "").strip()
    lowered_url = clean_url.lower()
    if lowered_url.startswith(("file://", "javascript:")):
        return {
            "success": False,
            "detail": f"navigation to {clean_url} blocked",
            "error": "Blocked unsafe URL scheme. Use http:// or https://.",
        }
    if clean_url and not lowered_url.startswith(("http://", "https://", "data:", "about:")):
        clean_url = f"https://{clean_url}"
    url = clean_url

    try:
        page = await _ensure_browser()
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)

        if not auto_snapshot:
            return {"success": True, "detail": f"navigated to {url}", "error": None}

        # Auto-extract elements, populate scratch buffer, and return compact manifest
        elements = await _extract_elements_with_coordinates(page)
        _ACTIVE_SCRATCH_ELEMENTS = elements
        scratch_path = _dump_to_scratch(elements)
        title = await page.title() or url
        manifest = _build_compact_manifest(title=title, url=url, elements=elements)

        return {
            "success": True,
            "detail": f"Navigated to {url}.\n\n[Active Page Manifest]:\n{manifest}\n\n[Full controls cached in {scratch_path}]",
            "scratch_file": scratch_path,
            "element_count": len(elements),
            "error": None,
        }
    except Exception as e:
        return {"success": False, "detail": f"navigation to {url} failed", "error": str(e)}


@mcp.tool
async def probe_page(
    query: str = "",
    tag_type: Optional[str] = None,
    section_hint: Optional[str] = None,
) -> dict:
    """Probe cached elements in scratch.md with tag type and section disambiguation.

    Use this to locate specific buttons, inputs, or choices without extra browser roundtrips.

    Args:
        query (str): Keyword to match against element text, name, or ref ID.
        tag_type (str, optional): Element kind to filter: 'button', 'radio', 'checkbox', 'input', 'link'.
        section_hint (str, optional): Heading or section container text to disambiguate identical labels.

    Returns:
        dict: A status dictionary containing matching elements with ref tags and coordinates.
    """
    matches = _search_scratch_elements(
        query=query,
        elements=_ACTIVE_SCRATCH_ELEMENTS,
        tag_type=tag_type,
        section_hint=section_hint,
    )
    return {
        "success": True,
        "count": len(matches),
        "matches": matches[:10],
        "error": None,
    }


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


def _decode_ddg_url(url: str) -> str:
    """Decodes DuckDuckGo redirect links to obtain direct target URLs."""
    if not url:
        return ""
    if "uddg=" in url:
        try:
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)
            if "uddg" in params and params["uddg"]:
                return params["uddg"][0]
        except Exception:
            pass
    if url.startswith("//"):
        return f"https:{url}"
    return url


@mcp.tool
async def search_web(query: str, max_results: int = 4) -> dict:
    """Searches the web for links and information.

    Executes within the persistent browser session.
    Returns organic search results with titles, URLs, and snippets.
    Complies with ASD-STE100 rules.
    """
    global _ACTIVE_SCRATCH_ELEMENTS
    clean_query = query.strip()
    if not clean_query:
        return {"success": False, "query": clean_query, "results": [], "error": "Query cannot be empty"}

    try:
        page = await _ensure_browser()
    except Exception as err:
        return {"success": False, "query": clean_query, "results": [], "error": f"Browser unavailable: {err}"}

    q = urllib.parse.quote_plus(clean_query)
    results = []

    # 1. Primary search engine: DuckDuckGo HTML
    try:
        ddg_url = f"https://html.duckduckgo.com/html/?q={q}"
        await page.goto(ddg_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(1000)

        ddg_items = await page.evaluate('''() => {
            const items = [];
            const rows = document.querySelectorAll('.result');
            for (const row of rows) {
                const link = row.querySelector('.result__title a, a.result__url, a.result__a');
                const snippet = row.querySelector('.result__snippet');
                if (link) {
                    const title = (link.innerText || '').trim();
                    const href = link.href || link.getAttribute('href') || '';
                    if (title && href) {
                        items.push({
                            title: title,
                            url: href,
                            snippet: (snippet ? snippet.innerText : '').trim().slice(0, 300)
                        });
                    }
                }
            }
            return items;
        }''')

        for item in ddg_items:
            direct_url = _decode_ddg_url(item.get("url", ""))
            if direct_url and direct_url.startswith("http"):
                results.append({
                    "title": item.get("title", "").strip(),
                    "url": direct_url,
                    "snippet": item.get("snippet", "").strip()
                })
    except Exception as e:
        print(f"[Warning] In-browser DuckDuckGo search failed: {e}", file=sys.stderr)

    # 2. Secondary fallback engine: Yahoo Search
    if not results:
        try:
            yahoo_url = f"https://search.yahoo.com/search?p={q}"
            await page.goto(yahoo_url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1000)

            yahoo_items = await page.evaluate('''() => {
                const items = [];
                const rows = document.querySelectorAll('ol.searchCenterMiddle li, div#web ol li');
                for (const row of rows) {
                    const link = row.querySelector('h3 a, h2 a, a.d-ib');
                    const snippet = row.querySelector('div.compText, p');
                    if (link && link.href && !link.href.includes('search.yahoo.com')) {
                        const rawTitle = (link.innerText || '').trim();
                        if (rawTitle) {
                            items.push({
                                title: rawTitle,
                                url: link.href,
                                snippet: (snippet ? snippet.innerText : '').trim().slice(0, 300)
                            });
                        }
                    }
                }
                return items;
            }''')

            for item in yahoo_items:
                raw_title = item.get("title", "").strip()
                title_lines = [line.strip() for line in raw_title.splitlines() if line.strip()]
                clean_title = title_lines[-1] if title_lines else raw_title
                results.append({
                    "title": clean_title,
                    "url": item.get("url", ""),
                    "snippet": item.get("snippet", "").strip()
                })
        except Exception as e:
            print(f"[Warning] In-browser Yahoo search failed: {e}", file=sys.stderr)

    # Auto-extract active controls on search results page to keep scratchpad updated
    try:
        elements = await _extract_elements_with_coordinates(page)
        _ACTIVE_SCRATCH_ELEMENTS = elements
        _dump_to_scratch(elements)
    except Exception:
        pass

    if results:
        return {
            "success": True,
            "query": clean_query,
            "results": results[:max_results],
            "instruction": "Search completed. Pick the best URL from 'results' and call 'browser_navigate' to load it, or use snippets to answer.",
            "error": None
        }

    return {
        "success": False,
        "query": clean_query,
        "results": [],
        "instruction": "No organic search results found. Try alternative keywords or navigate directly.",
        "error": "No search results found"
    }


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
        dict: A status dictionary containing a compact manifest of interactive elements.
    """
    global _ACTIVE_SCRATCH_ELEMENTS
    clean_url = (url or "").strip()
    lowered_url = clean_url.lower()
    if lowered_url.startswith(("file://", "javascript:")):
        return {
            "success": False,
            "detail": f"navigation to {clean_url} blocked",
            "error": "Blocked unsafe URL scheme. Use http:// or https://.",
        }
    if clean_url and not lowered_url.startswith(("http://", "https://", "data:", "about:")):
        clean_url = f"https://{clean_url}"
    url = clean_url

    try:
        page = await _ensure_browser()
        elements = await _extract_elements_with_coordinates(page)
        _ACTIVE_SCRATCH_ELEMENTS = elements
        scratch_path = _dump_to_scratch(elements)
        title = await page.title() or "Current Webpage"
        url = page.url
        manifest = _build_compact_manifest(title=title, url=url, elements=elements)

        return {
            "success": True,
            "detail": f"[Active Page Manifest]:\n{manifest}\n\n[Full controls cached in {scratch_path}]",
            "scratch_file": scratch_path,
            "element_count": len(elements),
            "error": None,
        }
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
        target_text = name or text or description

        # Fast coordinate click for cached @eN references
        ref_match = re.search(r"@e\d+", selector or target_text or "")
        if ref_match:
            ref_id = ref_match.group(0)
            cached = next((el for el in _ACTIVE_SCRATCH_ELEMENTS if el.get("ref") == ref_id), None)
            if cached and cached.get("coords"):
                coords = cached["coords"]
                cx = coords.get("x", 0) + coords.get("width", 0) / 2
                cy = coords.get("y", 0) + coords.get("height", 0) / 2
                await page.mouse.click(cx, cy)
                return {
                    "success": True,
                    "detail": f"Clicked {ref_id} ('{cached.get('text', '')}') at coordinates ({int(cx)}, {int(cy)}).",
                    "error": None,
                }

        locator = None
        target_desc = ""

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

        # Fast coordinate click and type for cached @eN references
        ref_match = re.search(r"@e\d+", selector or name or "")
        if ref_match:
            ref_id = ref_match.group(0)
            cached = next((el for el in _ACTIVE_SCRATCH_ELEMENTS if el.get("ref") == ref_id), None)
            if cached and cached.get("coords"):
                coords = cached["coords"]
                cx = coords.get("x", 0) + coords.get("width", 0) / 2
                cy = coords.get("y", 0) + coords.get("height", 0) / 2
                await page.mouse.click(cx, cy)
                await page.keyboard.press("Control+a")
                await page.keyboard.press("Backspace")
                await page.keyboard.type(text)
                return {
                    "success": True,
                    "detail": f"Filled {ref_id} ('{cached.get('text', '')}') with '{text}'.",
                    "error": None,
                }

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
        ref_match = re.search(r"@e\d+", selector or name or "")
        if ref_match:
            ref_id = ref_match.group(0)
            cached = next((el for el in _ACTIVE_SCRATCH_ELEMENTS if el.get("ref") == ref_id), None)
            if cached and cached.get("text"):
                extracted = cached["text"]

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