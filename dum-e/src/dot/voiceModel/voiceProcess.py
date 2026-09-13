import os
import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="torch.ao.nn.quantized")
warnings.filterwarnings("ignore", message=".*unauthenticated requests to the HF Hub.*")
warnings.filterwarnings("ignore", message=".*quantized tensor creation functions.*")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from faster_whisper import WhisperModel
import numpy as np

# Optimized with int8 compute on CPU
whisper = WhisperModel("small.en", device="cpu", compute_type="int8")

hallucinations = {
    "thank you", "thank you.", "thanks for watching", 
    "subscribe", "thank you for watching.", "thanks.", "thank you!",
    "thanks for watching!"
}

def transcribe(audio):
    if audio is None or len(audio) == 0:
        return ""

    if isinstance(audio, list):
        audio = np.array(audio, dtype=np.float32)
    elif audio.dtype != np.float32:
        audio = audio.astype(np.float32)

    max_val = np.max(np.abs(audio))
    if max_val > 1.0:
        audio = audio / 32768.0

    # vad_filter=True runs Silero VAD to strip silence and prevent hallucinations
    # beam_size=1 (greedy) is 4x faster on CPU than beam_size=5
    segments, _ = whisper.transcribe(
        audio,
        beam_size=1,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=250, threshold=0.35)
    )
    
    text = " ".join([s.text for s in segments]).strip()

    print("In transcribe function:\n", text)
    text_norm = text.lower().strip()
    if not text_norm or text_norm in hallucinations:
        print("[Voice] Silence/Hallucination filtered out.")
        return ""
    
    return text

    

