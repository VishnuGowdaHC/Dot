"""
Verification script for Dot desktop corner assistant shell.
Captures screenshots of idle badge, expanded chat states,
and settings modal dialog with full high-DPI verification.
"""

import os
from playwright.sync_api import sync_playwright
from PIL import Image

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.dirname(SCRIPT_DIR)
DIST_HTML = os.path.join(FRONTEND_DIR, "dist", "index.html")
IDLE_SCREENSHOT = os.path.join(FRONTEND_DIR, "dist", "screenshot_idle.png")
CHAT_SCREENSHOT = os.path.join(FRONTEND_DIR, "dist", "screenshot_chat.png")
SETTINGS_SCREENSHOT = os.path.join(FRONTEND_DIR, "dist", "screenshot_settings.png")


def verify_ui():
    """Render and capture the Dot shell states via headless browser."""
    print("Running Dot UI verification...")
    if not os.path.exists(DIST_HTML):
        raise FileNotFoundError(f"Missing {DIST_HTML}")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge")

        # 1. Capture Idle Shell at compact 440x184 (154px card)
        page = browser.new_page(viewport={"width": 440, "height": 184}, device_scale_factor=1)
        page.goto(f"file:///{os.path.abspath(DIST_HTML)}")
        page.wait_for_timeout(500)

        # Check card padding within window
        shell = page.locator("#corner-shell")
        shell_box = shell.bounding_box()
        print(f"Shell bounding box (idle): {shell_box}")
        assert shell_box is not None, "Corner shell not found"
        # Verify internal floating margin (should not touch outer window boundaries 0 and 440)
        assert shell_box["x"] >= 8, f"Shell left edge touches boundary: {shell_box['x']}"
        assert shell_box["x"] + shell_box["width"] <= 432, f"Shell right edge touches boundary: {shell_box['x'] + shell_box['width']}"

        # Check token bar box - ensure it is NOT cut in half
        token_bar = page.locator("#token-val")
        tb_box = token_bar.bounding_box()
        print(f"Token bar element box: {tb_box}")
        assert tb_box is not None, "Token bar not found"
        # Token bar must sit comfortably below shell top
        assert tb_box["y"] > shell_box["y"] + 15, f"Token bar is cut off at top of shell: {tb_box['y']} <= {shell_box['y'] + 15}"

        # Check orb bounding box
        orb = page.locator("#dot-orb")
        orb_box = orb.bounding_box()
        print(f"Orb bounding box: {orb_box}")
        assert orb_box is not None, "Orb element not found"
        assert orb_box["x"] + orb_box["width"] <= 440, f"Orb overflows viewport: {orb_box}"

        page.screenshot(path=IDLE_SCREENSHOT, omit_background=True)
        print(f"Captured idle screenshot: {IDLE_SCREENSHOT}")

        # 2. Inject simulated messages and test dynamic expansion at 440x510
        page.set_viewport_size({"width": 440, "height": 510})
        page.evaluate("""() => {
            state.messages.push({ role: 'user', content: 'What is Dot?' });
            state.messages.push({ role: 'dot', content: 'Dot is your local agentic desktop assistant.' });
            renderMessages();
            updateShellExpansion();
        }""")
        page.wait_for_timeout(600)
        page.screenshot(path=CHAT_SCREENSHOT, omit_background=True)
        print(f"Captured chat screenshot: {CHAT_SCREENSHOT}")

        # 3. Test Settings Modal at 440x560
        page.set_viewport_size({"width": 440, "height": 560})
        page.evaluate("""() => {
            openSettingsModal();
        }""")
        page.wait_for_timeout(500)
        page.screenshot(path=SETTINGS_SCREENSHOT, omit_background=True)
        print(f"Captured settings screenshot: {SETTINGS_SCREENSHOT}")

        # 4. Test High-DPI simulation (150% scaling)
        page_dpi = browser.new_page(viewport={"width": 440, "height": 184}, device_scale_factor=1.5)
        page_dpi.goto(f"file:///{os.path.abspath(DIST_HTML)}")
        page_dpi.wait_for_timeout(500)
        orb_dpi = page_dpi.locator("#dot-orb")
        orb_dpi_box = orb_dpi.bounding_box()
        print(f"High-DPI Orb bounding box: {orb_dpi_box}")
        assert orb_dpi_box["x"] + orb_dpi_box["width"] <= 440, f"Orb overflows under high-DPI: {orb_dpi_box}"

        browser.close()

    # Verify image dimensions
    im_idle = Image.open(IDLE_SCREENSHOT)
    im_chat = Image.open(CHAT_SCREENSHOT)
    im_settings = Image.open(SETTINGS_SCREENSHOT)
    print(f"Idle dimensions: {im_idle.size} (Expected: 440x184)")
    print(f"Chat dimensions: {im_chat.size} (Expected: 440x510)")
    print(f"Settings dimensions: {im_settings.size} (Expected: 440x560)")
    assert im_idle.size == (440, 184), f"Unexpected idle size: {im_idle.size}"
    assert im_chat.size == (440, 510), f"Unexpected chat size: {im_chat.size}"
    assert im_settings.size == (440, 560), f"Unexpected settings size: {im_settings.size}"
    print("Verification passed successfully.")


if __name__ == "__main__":
    verify_ui()
