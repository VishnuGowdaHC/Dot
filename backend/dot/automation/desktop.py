import os
import re
import subprocess
import tempfile
from fastmcp import FastMCP, Context
import psutil
import pygetwindow as gw
import pyautogui
import time
from datetime import datetime
import yaml
import json
from typing import List, Optional, Union
import sys
import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="torch.ao.nn.quantized")
warnings.filterwarnings("ignore", message=".*quantized tensor creation functions.*")

_original_stdout = sys.stdout
sys.stdout = sys.stderr

_OCR_READER = None

def _get_ocr_reader():
    """Lazily loads the EasyOCR reader on CPU to prevent GPU VRAM competition."""
    global _OCR_READER
    if _OCR_READER is None:
        try:
            import easyocr
            # Run EasyOCR on CPU to preserve VRAM for local llama-server.
            _OCR_READER = easyocr.Reader(['en'], gpu=False, verbose=False)
        except Exception as ocr_err:
            print(f"[Warning] EasyOCR failed to load: {ocr_err}", file=sys.stderr)
            _OCR_READER = None
    return _OCR_READER

sys.stdout = _original_stdout

from dot.config.paths import CONFIG_PATH, ALLOWED_APPS_PATH, LOGS_DIR

mcp = FastMCP(name="Dot OS Automation")

def load_allowed_processes():
    allowed = set()
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            procs = cfg.get("allowed_processes", [])
            if procs:
                allowed.update(p_name.lower() for p_name in procs)
        except Exception as e:
            print(f"[Warning] Failed to parse appConfig.json for allowed processes: {e}", file=sys.stderr)

    if ALLOWED_APPS_PATH.exists():
        try:
            with open(ALLOWED_APPS_PATH, "r") as f:
                config = yaml.safe_load(f)
                processes = config.get("os_automation", {}).get("allowed_processes", [])
                allowed.update(p.lower() for p in processes)
        except Exception as e:
            print(f"[Error] Failed to parse allowed_apps.yml: {e}", file=sys.stderr)

    return allowed

ALLOWED_PROCESSES = load_allowed_processes()

@mcp.tool
def os_manage_process(action: str, process_name: Optional[str] = "") -> str:
    """
    Safely manages host processes based on a strict whitelist. 
    Use this to start, stop, or list allowed applications.

    Args:
        action (str): The operation to perform. Must be 'list', 'kill', or 'start'.
        process_name (str, optional): The name of the executable (e.g., 'chrome.exe'). Required for 'kill' and 'start'.
    """
    action = action.lower() if action else ""
    process_name = process_name.lower() if process_name else ""

    # Normalize executable name when the extension is omitted.
    if process_name and not process_name.endswith(".exe"):
        exe_candidate = f"{process_name}.exe"
        if exe_candidate in ALLOWED_PROCESSES:
            process_name = exe_candidate

    if action == "list":
        running = {p.info['name'] for p in psutil.process_iter(['name']) if p.info['name']}
        
        # If the LLM passed a specific process name to check, look for it directly
        if process_name:
            if process_name not in ALLOWED_PROCESSES:
                return f"Error: '{process_name}' is not in the approved allowed_apps.yml whitelist. Status check blocked."
            is_running = any(process_name in p.lower() for p in running)
            return f"Checked system: '{process_name}' IS currently running." if is_running else f"Checked system: '{process_name}' is NOT running."
            
        # Otherwise, only return processes that are in your strict whitelist
        visible = [p for p in running if p.lower() in ALLOWED_PROCESSES]
        if visible:
            return f"Currently running tracked processes: {', '.join(visible)}"
        else:
            return "None of the tracked processes in allowed_apps.yml are currently running."

    if action in ["kill", "start"]:
        if process_name not in ALLOWED_PROCESSES:
            return f"Error: '{process_name}' is not in the approved allowed_apps.yml whitelist. Action blocked."

        if action == "kill":
            killed = False
            errors = []
            for proc in psutil.process_iter(['name']):
                if proc.info['name'].lower() == process_name:
                    try:
                        proc.kill()
                        killed = True
                    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                        errors.append(str(e))
            if killed:
                return f"Successfully killed {process_name}."
            if errors:
                return f"Failed to kill {process_name}: {'; '.join(errors)}"
            return f"{process_name} is not currently running."
        
        if action == "start":
            # If a matching application window is already running, activate it.
            clean_name = os.path.splitext(str(process_name))[0].lower()
            try:
                for w in gw.getAllWindows():
                    title = (w.title or "").lower()
                    if clean_name in title:
                        w.restore()
                        w.activate()
                        time.sleep(0.3)
                        return f"Activated existing window '{w.title}' for {process_name}."
            except Exception:
                pass

            # Start executable using native Windows file launcher.
            try:
                os.startfile(process_name)
                # Pause briefly to allow the application window to initialize.
                time.sleep(0.8)
                return f"Successfully launched {process_name}."
            except Exception as e:
                return f"Failed to start {process_name}. Make sure it is in the system PATH. Error: {str(e)}"
                
    return "Invalid action. Use 'list', 'kill', or 'start'."

@mcp.tool
def os_get_active_window():
    """
    Retrieves the title of the currently focused/active window on the desktop.
    Use this to check what application is currently in the foreground.
    """
    try:
        window = gw.getActiveWindow()
        if window:
            return f"Active window: {window.title}"
        return "No active window."
    except Exception as e:
        return f"Failed to get active window. Error: {str(e)}"

@mcp.tool
async def os_take_screenshot(ctx: Context = None, question: str = "Describe what's visible on the screen.") -> dict:
    """Capture a screenshot of the computer monitor, desktop, or active windows.
    Use this when the user asks to check, inspect, or describe their screen.
    Keywords: screen, screenshot, check screen, inspect, see, read screen, desktop.

    Returns:
        dict: A status dictionary containing a text description in 'detail' and image path in 'filepath'.
    """
    try:
        obs_dir = os.path.join(str(LOGS_DIR), "screenshots")
        os.makedirs(obs_dir, exist_ok=True)

        filename = f"desktop_snap_{int(time.time())}.png"
        filepath = os.path.join(obs_dir, filename)

        pyautogui.screenshot(filepath)
        import base64
        with open(filepath, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        image_url = f"data:image/png;base64,{encoded}"

        description = None
        try:
            from dot.core.llm import async_llm
            description = await async_llm(
                query=question,
                image_url=image_url,
                system_prompt="Describe what is visible on this desktop screen in 2-3 concise sentences.",
            )
        except Exception:
            description = None

        if not description and ctx and hasattr(ctx, "session") and ctx.session:
            try:
                from fastmcp.client.sampling import SamplingMessage
                from mcp.types import ImageContent, TextContent
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
                    system_prompt="Describe what is visible on this desktop screen in 2-3 concise sentences.",
                    max_tokens=200,
                )
                if hasattr(sample_res, "content"):
                    description = sample_res.content.text if hasattr(sample_res.content, "text") else str(sample_res.content)
            except Exception:
                pass

        if not description:
            description = f"Desktop screenshot captured and saved to {filepath}."

        return {"success": True, "detail": description, "filepath": filepath, "error": None}
    except Exception as e:
        return {"success": False, "detail": None, "filepath": None, "error": f"Failed to take screenshot: {str(e)}"}

pyautogui.FAILSAFE = True

@mcp.tool
def os_mouse_click(x: int, y: int, button: str = "left", clicks: int = 1) -> str:
    """
    Moves the mouse to the specified exact screen coordinates and performs a click.
    Failsafe: Moving the physical mouse to any corner of the screen will abort this action.

    Args:
        x (int): The absolute X pixel coordinate on the screen.
        y (int): The absolute Y pixel coordinate on the screen.
        button (str, optional): The mouse button to press ('left', 'right', or 'middle'). Defaults to 'left'.
        clicks (int, optional): The number of consecutive clicks to perform. Defaults to 1.
    """
    try:
        pyautogui.moveTo(x, y, duration=0.2)
        pyautogui.click(button=button, clicks=clicks)
        return f"Mouse clicked at ({x}, {y}) with button {button} and {clicks} clicks."
    except Exception as e:
        return f"Failed to click mouse. Error: {str(e)}"

@mcp.tool
def os_keyboard_type(text: str, target_window: Optional[str] = None) -> str:
    """Type or paste text into the active desktop window or selected cell.
    Activate the window matching target_window before typing when provided.
    Use this to type, edit, replace, update, modify, or enter text in cells, spreadsheets, forms, or editors.
    Keywords: type, edit, replace, change, rename, overwrite, paste, fill, write, cell, spreadsheet.

    Args:
        text (str): The exact string of text to type or paste.
        target_window (str, optional): Title or partial name of the target window to activate.
    """
    try:
        active_title = ""
        try:
            active_win = gw.getActiveWindow()
            if active_win and active_win.title:
                active_title = active_win.title.strip()
        except Exception:
            pass

        # If a specific target window was requested, find and activate it.
        target_found = False
        if target_window:
            target_lower = target_window.strip().lower()
            target_stem = target_lower[:-4] if target_lower.endswith(".exe") else target_lower
            try:
                for w in gw.getAllWindows():
                    w_title = (w.title or "").lower()
                    if target_lower in w_title or (target_stem and target_stem in w_title):
                        w.restore()
                        w.activate()
                        time.sleep(0.3)
                        active_title = w.title.strip()
                        target_found = True
                        break
            except Exception:
                pass

            if not target_found:
                return (
                    f"Error: Target window '{target_window}' is not open. "
                    f"Active window is '{active_title or 'Unknown'}'. "
                    "Start the target application first with "
                    "os_manage_process(action='start', process_name='<app>.exe'), "
                    "then call os_keyboard_type again."
                )

        # If no target window specified and Dot UI is active, focus top non-system desktop window.
        if not target_found and (not active_title or "dot" in active_title.lower()):
            try:
                for w in gw.getAllWindows():
                    w_title = (w.title or "").lower()
                    if w.title and not any(k in w_title for k in ("dot", "taskbar", "program manager", "shell", "input")):
                        w.restore()
                        w.activate()
                        time.sleep(0.3)
                        active_title = w.title.strip()
                        break
            except Exception:
                pass

        # For long or multi-line text, use fast clipboard paste for high fidelity.
        text_str = str(text)
        if len(text_str) > 40 or "\n" in text_str:
            import pyperclip
            prev_clipboard = None
            try:
                prev_clipboard = pyperclip.paste()
            except Exception:
                prev_clipboard = None
            try:
                pyperclip.copy(text_str)
                time.sleep(0.05)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.05)
            finally:
                if prev_clipboard is not None:
                    try:
                        pyperclip.copy(prev_clipboard)
                    except Exception:
                        pass
        else:
            pyautogui.write(text_str, interval=0.01)

        win_info = f" into active window '{active_title}'" if active_title else ""
        preview = text_str[:120] + "..." if len(text_str) > 120 else text_str
        return f"Typed text{win_info}: {preview}"
    except Exception as e:
        return f"Failed to type text. Error: {str(e)}"

@mcp.tool
def os_keyboard_press(keys: Union[List[str], str]) -> str:
    """Press a specific key or key combination simultaneously.
    Use this to press Enter, Tab, Backspace, Delete, or Ctrl+A to confirm or clear edits.
    Keywords: press, key, enter, backspace, delete, escape, shortcut, hotkey, clear, submit.

    Args:
        keys (List[str]): A list of key names to press together.
            Examples: ['enter'], ['ctrl', 'c'], ['win', 'd'], ['tab'].
    """
    try:
        if isinstance(keys, str):
            raw = keys.strip()
            if not raw:
                return "Failed to press key: keys cannot be empty."
            key_list = [k.strip() for k in raw.split("+") if k.strip()]
        else:
            key_list = [str(k).strip() for k in keys if str(k).strip()]
        if not key_list:
            return "Failed to press key: keys cannot be empty."
        pyautogui.hotkey(*key_list)
        return f"Pressed key: {key_list}"
    except Exception as e:
        return f"Failed to press key. Error: {str(e)}"

def _calculate_text_match_score(target: str, candidate: str) -> int:
    """Calculate the match quality between target text and candidate text."""
    target_clean = target.lower().strip()
    candidate_clean = candidate.lower().strip()
    if not target_clean or not candidate_clean:
        return 0
    if target_clean == candidate_clean:
        return 100
    if re.search(rf"(?<!\w){re.escape(target_clean)}(?!\w)", candidate_clean):
        return 85
    if len(target_clean) >= 4 and target_clean in candidate_clean:
        return 65
    target_words = set(w for w in target_clean.split() if len(w) >= 3)
    candidate_words = set(w for w in candidate_clean.split() if len(w) >= 3)
    overlap = target_words.intersection(candidate_words)
    if overlap and len(overlap) == len(target_words):
        return 60
    return 0


def _get_dot_window_rects() -> list[tuple[int, int, int, int]]:
    """Return screen rectangles for visible Dot overlay windows to exclude from OCR."""
    rects = []
    try:
        for w in gw.getAllWindows():
            title = (w.title or "").strip().lower()
            if title == "dot" and getattr(w, "visible", True):
                if 0 < w.width < 900 and 0 < w.height < 900:
                    rects.append((w.left, w.top, w.left + w.width, w.top + w.height))
    except Exception:
        pass
    return rects


def _point_in_rects(x: int, y: int, rects: list[tuple[int, int, int, int]]) -> bool:
    """Return True when coordinates fall inside any excluded rectangle."""
    return any(l <= x <= r and t <= y <= b for (l, t, r, b) in rects)


def _run_windows_ocr(image_path: str) -> list[tuple[int, int, str]]:
    """Run built-in Windows 10/11 WinRT OCR and return (x, y, text) word entries."""
    ps_script = f"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {{ $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' }})[0]
Function Await($WinRtTask, $ResultType) {{
    $netTask = $asTaskGeneric.MakeGenericMethod($ResultType).Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}}
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync('{image_path.replace("'", "''")}')) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
$ocrResult = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
$items = @()
foreach ($line in $ocrResult.Lines) {{
    foreach ($word in $line.Words) {{
        $r = $word.BoundingRect
        $items += [PSCustomObject]@{{
            x = [int]($r.X + ($r.Width / 2))
            y = [int]($r.Y + ($r.Height / 2))
            text = $word.Text
        }}
    }}
    if ($line.Words.Count -gt 1) {{
        $first = $line.Words[0].BoundingRect
        $last = $line.Words[$line.Words.Count - 1].BoundingRect
        $items += [PSCustomObject]@{{
            x = [int](($first.X + $last.X + $last.Width) / 2)
            y = [int]($first.Y + ($first.Height / 2))
            text = $line.Text
        }}
    }}
}}
$items | ConvertTo-Json -Compress
"""
    ps1_path = os.path.join(tempfile.gettempdir(), f"dot_ocr_{os.getpid()}.ps1")
    try:
        with open(ps1_path, "w", encoding="utf-8") as f:
            f.write(ps_script)
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", ps1_path],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        raw = (proc.stdout or "").strip()
        if proc.returncode != 0 or not raw:
            if proc.stderr:
                print(f"[WinOCR Warning] rc={proc.returncode} err={proc.stderr.strip()[:200]}", file=sys.stderr)
            return []
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            parsed = [parsed]
        return [(int(item["x"]), int(item["y"]), str(item["text"])) for item in parsed if item.get("text")]
    except Exception as e:
        print(f"[WinOCR Error] {e}", file=sys.stderr)
        return []
    finally:
        try:
            if os.path.exists(ps1_path):
                os.remove(ps1_path)
        except Exception:
            pass


def _scan_screen_words() -> list[tuple[int, int, str]]:
    """Scan desktop screenshot using native Windows OCR with downscaled EasyOCR fallback."""
    screenshot = pyautogui.screenshot()
    tmp_path = os.path.join(tempfile.gettempdir(), f"dot_ocr_{os.getpid()}.png")
    try:
        screenshot.save(tmp_path)
        win_items = _run_windows_ocr(tmp_path)
        if win_items:
            return win_items
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

    reader = _get_ocr_reader()
    if not reader:
        return []

    import cv2
    import numpy as np
    img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)
    height, width = img.shape[:2]
    scale = 1.0
    if width > 1920:
        scale = 1920.0 / float(width)
        img = cv2.resize(img, (1920, int(height * scale)), interpolation=cv2.INTER_AREA)

    results = reader.readtext(img)
    items = []
    for (bbox, recognized_text, _prob) in results:
        cx = int(((bbox[0][0] + bbox[1][0]) / 2.0) / scale)
        cy = int(((bbox[0][1] + bbox[2][1]) / 2.0) / scale)
        items.append((cx, cy, recognized_text))
    return items


def _find_text_candidates(
    target: str,
    min_score: int = 60,
    words: Optional[list[tuple[int, int, str]]] = None,
) -> tuple[list[tuple[int, int, str, int]], int, int]:
    """Return all matching OCR candidates sorted by score, plus total and excluded counts."""
    excluded = _get_dot_window_rects()
    scanned = words if words is not None else _scan_screen_words()
    excluded_count = 0
    candidates: list[tuple[int, int, str, int]] = []
    for x, y, recognized_text in scanned:
        if _point_in_rects(x, y, excluded):
            excluded_count += 1
            continue
        score = _calculate_text_match_score(target, recognized_text)
        if score >= min_score:
            candidates.append((x, y, recognized_text, score))
    candidates.sort(key=lambda item: (-item[3], item[1], item[0]))
    return candidates, len(scanned), excluded_count


def _find_best_text_match(target: str, min_score: int = 60) -> Optional[tuple[int, int, str, int]]:
    """Find the highest-scoring OCR text match outside Dot windows."""
    candidates, _, _ = _find_text_candidates(target, min_score=min_score)
    return candidates[0] if candidates else None


def _activate_window_at(x: int, y: int) -> str:
    """Activate the non-Dot desktop window at screen coordinates (x, y)."""
    try:
        for w in gw.getWindowsAt(x, y):
            title = (w.title or "").strip()
            lower = title.lower()
            if title and lower != "dot" and not any(k in lower for k in ("taskbar", "program manager")):
                try:
                    w.activate()
                    time.sleep(0.08)
                except Exception:
                    pass
                return title
    except Exception:
        pass
    return ""


def _read_active_selection_via_clipboard() -> str:
    """Copy the active cell or selection text while preserving the previous clipboard."""
    import pyperclip
    prev_clipboard = None
    try:
        prev_clipboard = pyperclip.paste()
    except Exception:
        prev_clipboard = None

    copied = ""
    try:
        pyperclip.copy("")
        time.sleep(0.03)
        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.08)
        copied = (pyperclip.paste() or "").strip()
    except Exception:
        copied = ""
    finally:
        if prev_clipboard is not None:
            try:
                pyperclip.copy(prev_clipboard)
            except Exception:
                pass
    return copied


@mcp.tool
def os_find_text_coordinates(
    text: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """Scans the current desktop screen for the specified text using fast OCR and returns its center coordinates.

    Use this before clicking to find the exact X, Y location of a button or word.

    Args:
        text (str, optional): The text or word to search for on the screen.
        title (str, optional): Alternative name for the target title or button label.
        description (str, optional): Alternative description of the target text.
    """
    target = text or title or description
    if not target:
        return "Provide target text to locate."
    try:
        match = _find_best_text_match(target, min_score=60)
        if match:
            x, y, label, _ = match
            return f"Found '{label}' at coordinates: x={x}, y={y}"
        return f"Could not find the text '{target}' on the screen."
    except Exception as e:
        return f"OCR failed: {str(e)}"


@mcp.tool
def os_click_text(
    text: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    clicks: int = 1,
    button: str = "left",
    verify_text: bool = False,
) -> str:
    """Scan the desktop screen for the specified text with fast OCR and click it.
    Use this without coordinates to select cells, buttons, links, or text on the monitor.
    Keywords: click, select, focus, cell, button, link, menu, text.

    Args:
        text (str, optional): The visible text or title to locate and click on the screen.
        title (str, optional): Alternative name for the target title or button label.
        description (str, optional): Alternative description of the target element.
        clicks (int, optional): The number of clicks to perform. Defaults to 1.
        button (str, optional): The mouse button to click. Defaults to left.
        verify_text (bool, optional): Verify the active selection text via clipboard after clicking.
    """
    target = text or title or description
    if not target:
        return "Provide target text or title to click."
    try:
        match = _find_best_text_match(target, min_score=60)
        if not match:
            return (
                f"Could not find the text '{target}' on the screen to click. "
                "Use os_take_screenshot to inspect the visible titles and labels first."
            )

        x, y, label, _ = match
        win_title = _activate_window_at(x, y)
        pyautogui.moveTo(x, y, duration=0.12)
        pyautogui.click(clicks=clicks, button=button)
        time.sleep(0.08)

        if verify_text:
            actual = _read_active_selection_via_clipboard()
            if actual and _calculate_text_match_score(target, actual) < 60:
                return (
                    f"Verification failed at ({x}, {y}): active cell/selection contains "
                    f"'{actual}', expected '{target}'."
                )

        win_info = f" in '{win_title}'" if win_title else ""
        return f"Successfully clicked on '{label}'{win_info} at screen coordinates ({x}, {y})."
    except Exception as e:
        return f"Failed to click text on screen: {str(e)}"


@mcp.tool
def os_replace_text(
    target: str,
    replacement: str,
    press_enter: bool = True,
) -> str:
    """Locate visible text on screen, verify the active selection, and replace it.
    Use this directly to edit or replace text in any desktop application or input field.
    Keywords: replace, edit, change, rename, overwrite, update, field, cell, text.

    Args:
        target (str): The existing visible text to locate and replace.
        replacement (str): The new text to enter in place of target.
        press_enter (bool, optional): Press Enter after typing to commit the edit. Defaults to True.
    """
    if not target or not target.strip():
        return "Provide target text to replace."
    try:
        candidates, total_words, excluded_count = _find_text_candidates(target, min_score=60)
        if not candidates:
            return (
                f"Could not find '{target}' on the screen "
                f"(OCR scanned {total_words} words, excluded {excluded_count})."
            )

        mismatches: list[str] = []
        for x, y, label, _ in candidates[:3]:
            win_title = _activate_window_at(x, y)
            pyautogui.moveTo(x, y, duration=0.12)
            pyautogui.click(clicks=1, button="left")
            time.sleep(0.1)

            actual = _read_active_selection_via_clipboard()
            if actual and _calculate_text_match_score(target, actual) >= 60:
                pyautogui.click(clicks=2, button="left")
                time.sleep(0.05)
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.04)
                type_res = os_keyboard_type(text=replacement, target_window=win_title or None)
                if press_enter:
                    time.sleep(0.04)
                    pyautogui.press("enter")
                return f"Verified '{actual}' at ({x}, {y}) and replaced with '{replacement}'. ({type_res})"

            mismatches.append(f"({x}, {y}) -> '{actual or '<empty>'}'")

        return (
            f"Verification failed for '{target}'. Clicked candidates did not match: "
            f"{'; '.join(mismatches)}. Aborted edit."
        )
    except Exception as e:
        return f"Failed to replace text on screen: {str(e)}"


if __name__ == "__main__":
    mcp.run(show_banner=False)