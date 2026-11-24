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
    os_keyboard_type,
    os_keyboard_press,
    os_mouse_click,
    os_click_text,
    os_find_text_coordinates,
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

    @patch("dot.automation.desktop._get_ocr_reader")
    @patch("pyautogui.screenshot")
    @patch("pyautogui.moveTo")
    @patch("pyautogui.click")
    def test_os_click_text_mocked(self, mock_click, mock_move, mock_snap, mock_get_reader):
        """Verifies that os_click_text locates recognized text and clicks it."""
        mock_reader = unittest.mock.MagicMock()
        mock_reader.readtext.return_value = [
            ([[100, 200], [200, 200], [200, 250], [100, 250]], "Ramaya Music Celebration Ravana Tandav", 0.95)
        ]
        mock_get_reader.return_value = mock_reader
        mock_snap.return_value = unittest.mock.MagicMock()

        res = os_click_text(text="Ravana Tandav")
        self.assertIn("Successfully clicked on", res)
        self.assertIn("Ramaya Music Celebration Ravana Tandav", res)
        mock_move.assert_called_once_with(150, 225, duration=0.2)
        mock_click.assert_called_once_with(clicks=1, button="left")

    @patch("dot.automation.desktop._get_ocr_reader")
    @patch("pyautogui.screenshot")
    def test_os_find_text_coordinates_mocked(self, mock_snap, mock_get_reader):
        """Verifies that os_find_text_coordinates returns center coordinates."""
        mock_reader = unittest.mock.MagicMock()
        mock_reader.readtext.return_value = [
            ([[100, 200], [200, 200], [200, 250], [100, 250]], "Save Button", 0.98)
        ]
        mock_get_reader.return_value = mock_reader
        mock_snap.return_value = unittest.mock.MagicMock()

        res = os_find_text_coordinates(text="Save Button")
        self.assertIn("Found 'Save Button' at coordinates: x=150, y=225", res)

    @patch("pyautogui.hotkey")
    def test_os_keyboard_press_string_normalization(self, mock_hotkey):
        """Verifies that string hotkeys normalize into key lists before pressing."""
        res = os_keyboard_press("ctrl+c")
        self.assertIn("Pressed key", res)
        mock_hotkey.assert_called_once_with("ctrl", "c")

    @patch("pyautogui.hotkey")
    @patch("pyautogui.write")
    @patch("pygetwindow.getAllWindows")
    @patch("pygetwindow.getActiveWindow")
    def test_os_keyboard_type_missing_target_window_aborts(
        self, mock_active_win, mock_all_wins, mock_write, mock_hotkey
    ):
        """Verifies that os_keyboard_type aborts instead of pasting into the wrong window."""
        chrome_win = unittest.mock.MagicMock()
        chrome_win.title = "Google Chrome"
        mock_active_win.return_value = chrome_win
        mock_all_wins.return_value = [chrome_win]

        res = os_keyboard_type("Summary text", target_window="Notepad")
        self.assertIn("Error: Target window 'Notepad' is not open", res)
        self.assertIn("os_manage_process", res)
        mock_write.assert_not_called()
        mock_hotkey.assert_not_called()

    @patch("pyautogui.write")
    @patch("pygetwindow.getAllWindows")
    @patch("pygetwindow.getActiveWindow")
    def test_os_keyboard_type_strips_exe_suffix_for_window_match(
        self, mock_active_win, mock_all_wins, mock_write
    ):
        """Verifies that target_window='notepad.exe' matches window titled 'Untitled - Notepad'."""
        notepad_win = unittest.mock.MagicMock()
        notepad_win.title = "Untitled - Notepad"
        mock_active_win.return_value = notepad_win
        mock_all_wins.return_value = [notepad_win]

        res = os_keyboard_type("Hello", target_window="notepad.exe")
        self.assertIn("Typed text into active window 'Untitled - Notepad'", res)
        mock_write.assert_called_once_with("Hello", interval=0.01)


if __name__ == "__main__":
    unittest.main()
