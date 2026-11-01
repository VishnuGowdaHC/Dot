"""
Audio transcription module using faster-whisper.
Loads the Whisper model lazily on first use.
"""

import os
import warnings

# Suppress harmless upstream PyTorch and HuggingFace Hub startup warnings.
warnings.filterwarnings("ignore", category=UserWarning, module="torch.ao.nn.quantized")
warnings.filterwarnings("ignore", message=".*unauthenticated requests to the HF Hub.*")
warnings.filterwarnings("ignore", message=".*quantized tensor creation functions.*")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from faster_whisper import WhisperModel
import numpy as np

# Module-level singleton instance for the Whisper model.
_WHISPER_MODEL = None


def _get_whisper_model() -> WhisperModel:
    """Loads the WhisperModel instance on the first transcription call."""
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        _WHISPER_MODEL = WhisperModel("small.en", device="cpu", compute_type="int8")
    return _WHISPER_MODEL


HALLUCINATIONS = {
    "thank you", "thank you.", "thanks for watching",
    "subscribe", "thank you for watching.", "thanks.", "thank you!",
    "thanks for watching!"
}


def transcribe(audio) -> str:
    """Transcribes an audio buffer into text using faster-whisper."""
    if audio is None or len(audio) == 0:
        return ""

    if isinstance(audio, list):
        audio = np.array(audio, dtype=np.float32)
    elif audio.dtype != np.float32:
        audio = audio.astype(np.float32)

    max_val = np.max(np.abs(audio))
    if max_val > 1.0:
        audio = audio / 32768.0

    model = _get_whisper_model()
    # Run Silero VAD to strip silence and prevent hallucinations.
    # Use greedy search (beam_size=1) for lower latency on CPU.
    segments, _ = model.transcribe(
        audio,
        beam_size=1,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=250, threshold=0.35)
    )

    text = " ".join([s.text for s in segments]).strip()

    print("In transcribe function:\n", text)
    text_norm = text.lower().strip()
    if not text_norm or text_norm in HALLUCINATIONS:
        print("[Voice] Silence or hallucination filtered out.")
        return ""

    return text

