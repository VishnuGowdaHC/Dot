"""
Unit tests for Dot auto-update version parsing, release matching, and SHA256 checks.
Complies with ASD-STE100 rules.
"""

import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from dot.core.updater import (
    parse_semver,
    is_newer_version,
    extract_release_assets,
    verify_sha256_file,
    check_for_updates,
)


class TestUpdater(unittest.IsolatedAsyncioTestCase):
    """Test suite for GitHub Release update checking and verification."""

    def test_semver_comparison(self):
        """Verifies semantic version parsing and comparison logic."""
        self.assertEqual(parse_semver("v2.0.1"), (2, 0, 1))
        self.assertEqual(parse_semver("2.1"), (2, 1, 0))
        self.assertTrue(is_newer_version("v2.1.0", "2.0.1"))
        self.assertTrue(is_newer_version("2.0.2", "2.0.1"))
        self.assertFalse(is_newer_version("v2.0.1", "2.0.1"))
        self.assertFalse(is_newer_version("1.0.13", "2.0.1"))

    def test_extract_release_assets(self):
        """Verifies extraction of setup executable and sha256 asset URLs."""
        release = {
            "assets": [
                {
                    "name": "Dot-Setup-x64.exe",
                    "browser_download_url": "https://github.com/VishnuGowdaHC/Dot/releases/download/v2.1.0/Dot-Setup-x64.exe",
                    "size": 123456,
                },
                {
                    "name": "Dot-Setup-x64.exe.sha256",
                    "browser_download_url": "https://github.com/VishnuGowdaHC/Dot/releases/download/v2.1.0/Dot-Setup-x64.exe.sha256",
                    "size": 90,
                },
            ]
        }
        info = extract_release_assets(release)
        self.assertEqual(info["asset_name"], "Dot-Setup-x64.exe")
        self.assertEqual(info["asset_size"], 123456)
        self.assertTrue(info["download_url"].endswith("Dot-Setup-x64.exe"))
        self.assertTrue(info["sha256_url"].endswith("Dot-Setup-x64.exe.sha256"))

    def test_verify_sha256_file(self):
        """Verifies SHA256 digest validation on temporary files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sample = Path(tmpdir) / "sample.bin"
            sample.write_bytes(b"dot-release-binary")
            import hashlib
            digest = hashlib.sha256(b"dot-release-binary").hexdigest()

            self.assertTrue(verify_sha256_file(sample, f"{digest}  Dot-Setup-x64.exe\n"))
            self.assertFalse(verify_sha256_file(sample, "0" * 64))
            self.assertFalse(verify_sha256_file(sample, "invalid-hash"))

    @patch("dot.core.updater.get_current_version", return_value="2.0.1")
    @patch("dot.core.updater.httpx.AsyncClient")
    async def test_check_for_updates_available(self, mock_client_cls, _mock_ver):
        """Verifies update detection when GitHub returns a newer release tag."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v2.2.0",
            "body": "Bug fixes and speed improvements.",
            "html_url": "https://github.com/VishnuGowdaHC/Dot/releases/tag/v2.2.0",
            "assets": [
                {
                    "name": "Dot-Setup-x64.exe",
                    "browser_download_url": "https://github.com/VishnuGowdaHC/Dot/releases/download/v2.2.0/Dot-Setup-x64.exe",
                    "size": 5000,
                }
            ],
        }
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client
        mock_client_cls.return_value = mock_client

        result = await check_for_updates()
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["update_available"])
        self.assertEqual(result["latest_version"], "2.2.0")
        self.assertEqual(result["current_version"], "2.0.1")


if __name__ == "__main__":
    unittest.main()
