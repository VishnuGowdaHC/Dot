from fastmcp import FastMCP
mcp = FastMCP(name="Dot Automation")

# --- Browser (Playwright, accessibility-tree based) ---
@mcp.tool
def browser_navigate(url: str) -> str: ...

@mcp.tool
def browser_snapshot() -> str:
    """Returns pruned accessibility tree of current page."""
    ...

@mcp.tool
def browser_click(role: str, name: str) -> str:
    """Click element by accessible role + name, e.g. role='button', name='Search'"""
    ...

@mcp.tool
def browser_fill(role: str, name: str, text: str) -> str: ...

# --- Native OS UI (pywinauto, UI Automation tree) ---
@mcp.tool
def os_snapshot(window_title: str = None) -> str:
    """Returns pruned UI Automation tree for the active or named window."""
    ...

@mcp.tool
def os_click(window_title: str, control_name: str) -> str: ...

@mcp.tool
def os_type(window_title: str, control_name: str, text: str) -> str: ...

# --- Raw screen fallback (only when neither tree gives a usable target) ---
@mcp.tool
def screen_capture() -> str:
    """Returns a screenshot for vision-based targeting. Use only when
    browser_snapshot/os_snapshot don't expose the needed element."""
    ...

@mcp.tool
def screen_click_coords(x: int, y: int) -> str: ...

@mcp.tool
def screen_type(text: str) -> str: ...

if __name__ == "__main__":
    mcp.run()