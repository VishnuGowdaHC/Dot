"""
Unit tests for direct application opener and media playback router.
Tests direct video URL resolution and desktop app launching.
"""

import sys
from pathlib import Path

# Add backend directory to module search path.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import unittest
from unittest.mock import patch, AsyncMock
import httpx

from dot.automation.app_opener import resolve_direct_video_url, routeAppOpener


class TestAppOpener(unittest.IsolatedAsyncioTestCase):
    """Test suite for direct app launcher and video resolver."""

    @patch("httpx.AsyncClient.get")
    async def test_resolve_direct_video_url(self, mock_get):
        """Verifies parsing of YouTube search result HTML into direct video URL."""
        mock_response = httpx.Response(
            status_code=200,
            text='<html><body><a href="/watch?v=dQw4w9WgXcQ">Video</a></body></html>',
            request=httpx.Request("GET", "https://www.youtube.com")
        )
        mock_get.return_value = mock_response

        url = await resolve_direct_video_url("play never gonna give you up")
        self.assertIsNotNone(url)
        self.assertEqual(url, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    @patch("webbrowser.open")
    @patch("httpx.AsyncClient.get")
    async def test_route_app_opener_media(self, mock_get, mock_web_open):
        """Verifies media playback query routes to browser video playback."""
        mock_response = httpx.Response(
            status_code=200,
            text='<html><body><a href="/watch?v=dQw4w9WgXcQ">Video</a></body></html>',
            request=httpx.Request("GET", "https://www.youtube.com")
        )
        mock_get.return_value = mock_response

        res = await routeAppOpener("play lofi hip hop")
        self.assertEqual(res, "Task Executed")
        mock_web_open.assert_called_once_with("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    @patch("webbrowser.open")
    @patch("asyncio.to_thread")
    async def test_route_app_opener_fallback(self, mock_to_thread, mock_web_open):
        """Verifies unknown application routes to browser search fallback."""
        mock_to_thread.side_effect = Exception("App not found")

        res = await routeAppOpener("open mysterynonexistentapp")
        self.assertEqual(res, "Task Executed")
        mock_web_open.assert_called_once()
        called_url = mock_web_open.call_args[0][0]
        self.assertIn("google.com/search", called_url)


if __name__ == "__main__":
    unittest.main()
