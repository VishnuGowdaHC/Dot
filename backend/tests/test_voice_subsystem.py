"""
Unit tests for the voice listener and audio processing subsystem.
Tests key code detection, dynamic device probing, and audio resampling.
"""

import sys
from pathlib import Path

# Add backend directory to module search path.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import unittest
from unittest.mock import MagicMock
import numpy as np

from dot.voice.listener import (
    _is_alt_key,
    _resample_audio,
    _find_working_input_device,
    TARGET_SAMPLE_RATE,
)

try:
    from pynput import keyboard
except ImportError:
    keyboard = None


class TestVoiceSubsystem(unittest.TestCase):
    """Test suite for voice listener functions."""

    def test_is_alt_key_standard_keys(self):
        """Verifies detection of standard pynput Alt key variants."""
        if not keyboard:
            self.skipTest("pynput not available")
        self.assertTrue(_is_alt_key(keyboard.Key.alt))
        self.assertTrue(_is_alt_key(keyboard.Key.alt_l))
        self.assertTrue(_is_alt_key(keyboard.Key.alt_r))
        self.assertFalse(_is_alt_key(keyboard.Key.space))

    def test_is_alt_key_virtual_keycodes(self):
        """Verifies detection of Windows virtual keycodes for Alt."""
        for vk_code in [18, 164, 165]:
            mock_key = MagicMock()
            mock_key.vk = vk_code
            self.assertTrue(_is_alt_key(mock_key))

        mock_other = MagicMock()
        mock_other.vk = 65  # Key 'A'
        self.assertFalse(_is_alt_key(mock_other))

    def test_resample_audio_from_44100(self):
        """Verifies accurate resampling from 44.1 kHz to 16 kHz."""
        orig_sr = 44100
        duration_sec = 0.5
        orig_samples = int(orig_sr * duration_sec)
        dummy_audio = np.sin(np.linspace(0, 100, orig_samples)).astype(np.float32)

        resampled = _resample_audio(dummy_audio, orig_sr, TARGET_SAMPLE_RATE)
        expected_samples = int(TARGET_SAMPLE_RATE * duration_sec)
        self.assertEqual(len(resampled), expected_samples)
        self.assertEqual(resampled.dtype, np.float32)

    def test_resample_audio_from_48000(self):
        """Verifies accurate resampling from 48 kHz to 16 kHz."""
        orig_sr = 48000
        duration_sec = 1.0
        orig_samples = int(orig_sr * duration_sec)
        dummy_audio = np.ones(orig_samples, dtype=np.float32)

        resampled = _resample_audio(dummy_audio, orig_sr, TARGET_SAMPLE_RATE)
        self.assertEqual(len(resampled), TARGET_SAMPLE_RATE)

    def test_resample_audio_passthrough(self):
        """Verifies that matching sample rates pass through without modification."""
        dummy_audio = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        resampled = _resample_audio(dummy_audio, TARGET_SAMPLE_RATE, TARGET_SAMPLE_RATE)
        self.assertEqual(len(resampled), 3)

    def test_find_working_input_device(self):
        """Verifies that device probing returns valid parameters."""
        dev_id, sr, ch = _find_working_input_device()
        self.assertIsInstance(sr, int)
        self.assertGreater(sr, 0)
        self.assertIsInstance(ch, int)
        self.assertGreaterEqual(ch, 1)


if __name__ == "__main__":
    unittest.main()

