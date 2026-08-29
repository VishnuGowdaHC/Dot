import os
from fastmcp import FastMCP, Context
import psutil
import pygetwindow as gw
import pyautogui
import time
from datetime import datetime
import yaml
from typing import Optional
import sys

_original_stdout = sys.stdout
sys.stdout = sys.stderr

try:
    import easyocr
    try:
        reader = easyocr.Reader(['en'], gpu=True, verbose=False)
    except Exception:
        reader = easyocr.Reader(['en'], gpu=False, verbose=False)
except Exception as ocr_err:
    print(f"[Warning] EasyOCR failed to load: {ocr_err}", file=sys.stderr)
    reader = None

sys.stdout = _original_stdout

mcp = FastMCP(name="Dot OS Automation")

def load_allowed_processes():
    config_path = os.path.join(os.path.dirname(__file__), "..",  "config", "allowed_apps.yml")

    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
           
            processes = config.get("os_automation", {}).get("allowed_processes", [])

            return {p.lower() for p in processes}
    except FileNotFoundError:
        print(f"[Warning] {config_path} not found. OS Process Manager is locked down.", file=sys.stderr)
        return set()
    except Exception as e:
        print(f"[Error] Failed to parse config.yml: {e}", file=sys.stderr)
        return set()

    return allowed_processes

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

    if action == "list":
        running = {p.info['name'] for p in psutil.process_iter(['name']) if p.info['name']}
        
        # If the LLM passed a specific process name to check, look for it directly
        if process_name:
            if process_name not in ALLOWED_PROCESSES:
                return f"Error: '{process_name}' is not in the approved config.yml whitelist. Status check blocked."
            is_running = any(process_name in p.lower() for p in running)
            return f"Checked system: '{process_name}' IS currently running." if is_running else f"Checked system: '{process_name}' is NOT running."
            
        # Otherwise, only return processes that are in your strict whitelist
        visible = [p for p in running if p.lower() in ALLOWED_PROCESSES]
        if visible:
            return f"Currently running tracked processes: {', '.join(visible)}"
        else:
            return "None of the tracked processes in config.yml are currently running."

    if action in ["kill", "start"]:
        if process_name not in ALLOWED_PROCESSES:
            return f"Error: '{process_name}' is not in the approved config.yml whitelist. Action blocked."

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
            # Very basic start wrapper (you may need to add actual path mappings later)
            try:
                os.startfile(process_name) # Works cleanly on Windows for apps in PATH
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
async def os_take_screenshot(ctx: Context, question: str = "Describe what's visible on screen."):
    """
    Use this to capture the user's actual computer screen, Windows desktop, or taskbar search
    Takes a full-screen snapshot of the current desktop and saves it to the local disk.
    
    Returns:
        str: A message containing the absolute file path of the saved screenshot image.
    """
    try:
        obs_dir = os.path.abspath(os.path.join("logs", "screenshots"))
        os.makedirs(obs_dir, exist_ok=True)

        filename = f"desktop_snap_{int(time.time())}.png"
        filepath = os.path.join(obs_dir, filename)

        pyautogui.screenshot(filepath)
        import base64
        with open(filepath, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")

        from fastmcp.client.sampling import SamplingMessage
        from mcp.types import ImageContent, TextContent

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
            system_prompt="Describe the desktop screenshot in 2-3 concise sentences.",
            max_tokens=200,
        )
        description = result.text if hasattr(result, "text") else str(result)
        return {"success": True, "detail": description, "filepath": filepath, "error": None}
    except Exception as e:
        return f"Failed to take screenshot. Error: {str(e)}"

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
def os_keyboard_type(text):
    """
    Simulates physical keystrokes to type out a continuous string of text.
    Use this to fill out forms, type URLs, or write messages.

    Args:
        text (str): The exact string of text to type.
    """
    try:
        pyautogui.write(text, interval=0.01)
        return f"Typed text: {text}"
    except Exception as e:
        return f"Failed to type text. Error: {str(e)}"

@mcp.tool
def os_keyboard_press(keys):
    """
    Presses a specific key or combination of keys simultaneously (e.g., hotkeys).
    
    Args:
        keys (List[str]): A list of key names to press together. 
            Examples: ['enter'], ['ctrl', 'c'], ['win', 'd'], ['tab'].
    """
    try:
        pyautogui.hotkey(*keys)
        return f"Pressed key: {keys}"
    except Exception as e:
        return f"Failed to press key. Error: {str(e)}"

@mcp.tool
def os_find_text_coordinates(text: str) -> str:
    """
    Scans the current desktop screen for the specified text using OCR and returns its center coordinates.
    Use this before clicking to find the exact X, Y location of a button or word.

    Args:
        text (str): The text or word to search for on the screen.
    """
    try:
        screenshot = pyautogui.screenshot()

        import numpy as np
        # Read the text bounding boxes
        results = reader.readtext(np.array(screenshot))
        
        for (bbox, recognized_text, prob) in results:
            if text.lower() in recognized_text.lower():
                # Calculate the center of the bounding box
                x = int((bbox[0][0] + bbox[1][0]) / 2)
                y = int((bbox[0][1] + bbox[2][1]) / 2)
                return f"Found '{text}' at coordinates: x={x}, y={y}"
                
        return f"Could not find the text '{text}' on the screen."
    except Exception as e:
        return f"OCR failed: {str(e)}"

    
if __name__ == "__main__":
    mcp.run()