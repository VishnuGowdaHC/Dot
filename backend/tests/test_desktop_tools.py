"""
Unit tests for OS desktop automation tools.
Tests active window inspection, process management, input validation, and security whitelists.
"""

import sys
from pathlib import Path

# Add backend directory to module search path.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import unittest
from unittest.mock import patch

from dot.automation.desktop import (
    os_get_active_window,
    os_manage_process,
    os_keyboard_press,
    os_mouse_click,
    load_allowed_processes,
)


class TestDesktopTools(unittest.TestCase):
    """Test suite for desktop OS tools."""

    def test_load_allowed_processes(self):
        """Verifies that allowed processes load from configuration."""
        allowed = load_allowed_processes()
        self.assertIsInstance(allowed, set)
        self.assertGreater(len(allowed), 0)

    def test_os_get_active_window(self):
        """Verifies that active window title returns a string."""
        res = os_get_active_window()
        self.assertIsInstance(res, str)
        self.assertTrue(len(res) > 0)

    def test_os_manage_process_list(self):
        """Verifies that listing processes returns running tracked processes."""
        res = os_manage_process(action="list")
        self.assertIsInstance(res, str)

    def test_os_manage_process_whitelist_enforcement(self):
        """Verifies that unauthorized process executions are blocked by the whitelist."""
        res = os_manage_process(action="start", process_name="unauthorized_virus.exe")
        self.assertIn("not in the approved", res)
        self.assertIn("blocked", res)

    def test_os_manage_process_invalid_action(self):
        """Verifies that invalid process actions return validation feedback."""
        res = os_manage_process(action="destroy_everything")
        self.assertIn("Invalid action", res)

    @patch("pyautogui.hotkey")
    def test_os_keyboard_press_mocked(self, mock_hotkey):
        """Verifies that os_keyboard_press calls input handler."""
        res = os_keyboard_press(["enter"])
        self.assertIn("Pressed key", res)
        mock_hotkey.assert_called_once_with("enter")

    @patch("pyautogui.moveTo")
    @patch("pyautogui.click")
    def test_os_mouse_click_mocked(self, mock_click, mock_move):
        """Verifies that os_mouse_click executes click with bounds validation."""
        res = os_mouse_click(100, 200, button="left", clicks=1)
        self.assertIn("Mouse clicked at", res)
        mock_move.assert_called_once_with(100, 200, duration=0.2)
        mock_click.assert_called_once_with(button="left", clicks=1)


if __name__ == "__main__":
    unittest.main()
