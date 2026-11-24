"""
Unit tests for inference engine telemetry and status diagnostics.
Tests state transitions, health verification, crash reporting, and log extraction.
Complies with ASD-STE100 technical writing rules.
"""

import sys
from pathlib import Path

# Add backend directory to module search path.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from server import (
    extract_engine_diagnostics,
    get_engine_status,
    get_engine_logs,
    start_engine_endpoint,
    stop_engine_endpoint,
    app_state,
)


class TestEngineStatusTelemetry(unittest.IsolatedAsyncioTestCase):
    """Test suite for local model status and telemetry."""

    def setUp(self):
        # Reset app_state engine process before each test
        app_state["engine_process"] = None
        app_state["engine_log_file"] = None

    def test_extract_engine_diagnostics_oom(self):
        """Verifies that out of memory errors are identified correctly."""
        tmp_log = BACKEND_DIR.parent / "logs" / "test_oom.log"
        tmp_log.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(tmp_log, "w", encoding="utf-8") as f:
                f.write("llama_model_load: allocating VRAM\n")
                f.write("CUDA error: out of memory at line 412\n")

            diag = extract_engine_diagnostics(tmp_log)
            self.assertIn("GPU out of memory", diag)
        finally:
            if tmp_log.exists():
                tmp_log.unlink()

    def test_extract_engine_diagnostics_missing_model(self):
        """Verifies that missing model file errors are identified correctly."""
        tmp_log = BACKEND_DIR.parent / "logs" / "test_missing.log"
        tmp_log.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(tmp_log, "w", encoding="utf-8") as f:
                f.write("llama_load_model_from_file: failed to load model file\n")

            diag = extract_engine_diagnostics(tmp_log)
            self.assertIn("Failed to load model file", diag)
        finally:
            if tmp_log.exists():
                tmp_log.unlink()

    @patch("server.check_engine_port_open", return_value=False)
    async def test_status_stopped_when_no_process_and_port_closed(self, mock_port):
        """Verifies that status reports stopped when port is closed and no process is tracked."""
        status = await get_engine_status()
        self.assertEqual(status["state"], "stopped")
        self.assertFalse(status["running"])
        self.assertFalse(status["healthy"])
        self.assertIn("stopped", status["detail"].lower())

    @patch("server.check_engine_port_open", return_value=True)
    async def test_status_ready_when_health_endpoint_ok(self, mock_port):
        """Verifies that status reports ready when the health endpoint returns 200 OK."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            status = await get_engine_status()
            self.assertEqual(status["state"], "ready")
            self.assertTrue(status["running"])
            self.assertTrue(status["healthy"])
            self.assertIn("ready", status["detail"].lower())

    @patch("server.check_engine_port_open", return_value=True)
    async def test_status_loading_when_health_endpoint_returns_503(self, mock_port):
        """Verifies that status reports loading when the server returns HTTP 503."""
        mock_response = MagicMock()
        mock_response.status_code = 503

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            status = await get_engine_status()
            self.assertEqual(status["state"], "loading")
            self.assertTrue(status["running"])
            self.assertFalse(status["healthy"])
            self.assertIn("loading", status["detail"].lower())

    @patch("server.check_engine_port_open", return_value=False)
    async def test_status_error_when_process_exits_with_code(self, mock_port):
        """Verifies that status reports error when process terminates with non-zero exit code."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1
        mock_proc.returncode = 1
        mock_proc.pid = 9999
        app_state["engine_process"] = mock_proc

        status = await get_engine_status()
        self.assertEqual(status["state"], "error")
        self.assertFalse(status["healthy"])
        self.assertIsNotNone(status["error"])
        self.assertIn("crashed", status["detail"].lower())

    async def test_get_engine_logs_returns_list(self):
        """Verifies that get_engine_logs returns a lines list."""
        res = await get_engine_logs(lines=10)
        self.assertIn("lines", res)
        self.assertIsInstance(res["lines"], list)

    @patch("server.check_engine_port_open", return_value=True)
    async def test_start_engine_already_running(self, mock_port):
        """Verifies that start endpoint reports ok when engine is already running."""
        res = await start_engine_endpoint()
        self.assertEqual(res["status"], "ok")
        self.assertIn("already running", res["message"])

    @patch("server.check_engine_port_open", return_value=False)
    async def test_start_engine_missing_model_file(self, mock_port):
        """Verifies that start endpoint reports error when the requested model file is missing."""
        mock_req = MagicMock()
        mock_req.json = AsyncMock(return_value={"tier": "2B"})

        res = await start_engine_endpoint(request=mock_req)
        self.assertEqual(res["status"], "error")
        self.assertIn("not found in the bin directory", res["message"])

    @patch("server.check_engine_port_open", return_value=False)
    @patch("subprocess.Popen")
    async def test_start_engine_spawns_process_successfully(self, mock_popen, mock_port):
        """Verifies that start endpoint spawns llama-server when valid model exists."""
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        mock_req = MagicMock()
        mock_req.json = AsyncMock(return_value={"tier": "4B"})

        res = await start_engine_endpoint(request=mock_req)
        self.assertEqual(res["status"], "starting")
        self.assertIn("Starting engine on port", res["message"])
        self.assertIs(app_state["engine_process"], mock_proc)

    @patch("server.check_engine_port_open", return_value=False)
    @patch("subprocess.Popen", side_effect=OSError("spawn failed"))
    async def test_start_engine_closes_log_file_on_popen_failure(self, mock_popen, mock_port):
        """Verifies that start endpoint closes the log file handle if Popen fails."""
        mock_req = MagicMock()
        mock_req.json = AsyncMock(return_value={"tier": "4B"})

        mock_file = MagicMock()
        with patch("server.load_config", return_value={"active_settings": {"selected_tier": "4B"}, "models": {"4B": {"filename": "gemma-4-E4B_q4_0-it.gguf"}}}), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("builtins.open", return_value=mock_file):
            res = await start_engine_endpoint(request=mock_req)
        self.assertEqual(res["status"], "error")
        mock_file.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
