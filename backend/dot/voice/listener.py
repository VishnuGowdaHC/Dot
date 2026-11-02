"""
Hold-Alt voice listener module.
Records microphone audio while the user holds the Alt key.
"""

import time
import threading
from typing import Optional, Tuple
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    sd = None

try:
    from pynput import keyboard
except ImportError:
    keyboard = None

from dot.voice.transcriber import transcribe

# Hold-Alt voice mode configuration.
HOLD_DURATION_SECONDS = 0.35
TARGET_SAMPLE_RATE = 16000
MIN_SPEECH_DURATION_SECONDS = 0.35

_is_alt_down = False
_press_start_time = 0.0
_is_recording = False
_recording_thread = None
_lock = threading.Lock()
_cached_device_info: Optional[Tuple[Optional[int], int, int]] = None


def _is_alt_key(key) -> bool:
    """Verifies if the pressed key is an Alt key variant."""
    if not keyboard:
        return False
    if key in (
        keyboard.Key.alt,
        keyboard.Key.alt_l,
        keyboard.Key.alt_r,
        getattr(keyboard.Key, "alt_gr", None),
    ):
        return True
    vk = getattr(key, "vk", None)
    return vk in (18, 164, 165)


def _find_working_input_device() -> Tuple[Optional[int], int, int]:
    """Probes and returns a working audio input device index, sample rate, and channels."""
    global _cached_device_info
    if _cached_device_info is not None:
        return _cached_device_info

    if not sd:
        _cached_device_info = (None, TARGET_SAMPLE_RATE, 1)
        return _cached_device_info

    # 1. Probe the system default input device.
    try:
        def_info = sd.query_devices(kind="input")
        sr = int(def_info.get("default_samplerate", 44100))
        ch = min(1, def_info.get("max_input_channels", 1))
        idx = def_info.get("index")
        with sd.InputStream(device=idx, samplerate=sr, channels=ch, callback=lambda a, b, c, d: None):
            pass
        _cached_device_info = (idx, sr, ch)
        print(f"[Voice Mode] Using default microphone: {def_info.get('name')} (device {idx}, {sr}Hz).")
        return _cached_device_info
    except Exception:
        pass

    # 2. Iterate through all available input devices.
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if dev.get("max_input_channels", 0) > 0:
            sr = int(dev.get("default_samplerate", 44100))
            ch = 1
            try:
                with sd.InputStream(device=i, samplerate=sr, channels=ch, callback=lambda a, b, c, d: None):
                    pass
                _cached_device_info = (i, sr, ch)
                print(f"[Voice Mode] Fallback microphone selected: {dev.get('name')} (device {i}, {sr}Hz).")
                return _cached_device_info
            except Exception:
                continue

    print("[Voice Mode Warning] No verified microphone device detected. Falling back to default settings.")
    _cached_device_info = (None, TARGET_SAMPLE_RATE, 1)
    return _cached_device_info


def _resample_audio(audio: np.ndarray, orig_sr: int, target_sr: int = TARGET_SAMPLE_RATE) -> np.ndarray:
    """Resamples audio array to target sample rate using linear interpolation."""
    if orig_sr == target_sr or len(audio) == 0:
        return audio.astype(np.float32)

    num_target_samples = int(len(audio) * target_sr / orig_sr)
    x_old = np.linspace(0.0, 1.0, len(audio), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num_target_samples, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


def _record_audio_worker(on_transcription_callback, on_status_callback) -> None:
    """Records audio from the microphone until Alt key release."""
    global _is_recording

    print("\n[Voice Mode] Alt held. Recording speech. Release Alt when done.")
    if on_status_callback:
        on_status_callback("recording")

    device_id, sample_rate, channels = _find_working_input_device()
    buffer = []
    stream = None

    def audio_callback(indata, frames, time_info, status):
        """Appends captured audio chunk to buffer."""
        if _is_recording:
            buffer.extend(indata.flatten())

    try:
        stream = sd.InputStream(
            device=device_id,
            samplerate=sample_rate,
            channels=channels,
            dtype="float32",
            callback=audio_callback,
        )
        stream.start()

        max_seconds = 25.0
        start_time = time.time()
        while _is_recording and (time.time() - start_time) < max_seconds:
            time.sleep(0.04)

    except Exception as stream_err:
        print(f"[Voice Mode Error] Audio stream initialization failed: {stream_err}")
    finally:
        if stream:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    if on_status_callback:
        on_status_callback("transcribing")

    # Resample audio to 16,000 Hz for faster-whisper.
    raw_audio = np.array(buffer, dtype=np.float32)
    resampled_audio = _resample_audio(raw_audio, sample_rate, TARGET_SAMPLE_RATE)
    recorded_seconds = len(resampled_audio) / TARGET_SAMPLE_RATE

    if recorded_seconds >= MIN_SPEECH_DURATION_SECONDS:
        print(f"[Voice Mode] Recording finished ({recorded_seconds:.2f}s). Transcribing...")
        try:
            text = transcribe(resampled_audio)
            if text:
                print(f"[Voice Mode] Recognized: '{text}'")
                if on_transcription_callback:
                    on_transcription_callback(text)
                else:
                    from dot.automation.app_opener import routeAppOpener
                    import asyncio
                    asyncio.run(routeAppOpener(text))
            else:
                print("[Voice Mode] No audible speech detected in recording.")
        except Exception as trans_err:
            print(f"[Voice Mode Error] Transcription error: {trans_err}")
    else:
        print(f"[Voice Mode] Recording was too short ({recorded_seconds:.2f}s < {MIN_SPEECH_DURATION_SECONDS}s). Ignored.")

    if on_status_callback:
        on_status_callback("idle")


def _monitor_hold_trigger(on_transcription_callback, on_status_callback) -> None:
    """Monitors whether Alt key is held beyond the trigger threshold."""
    global _is_alt_down, _is_recording, _press_start_time, _recording_thread

    while True:
        with _lock:
            if not _is_alt_down:
                return
            elapsed = time.time() - _press_start_time
            if elapsed >= HOLD_DURATION_SECONDS:
                _is_recording = True
                break
        time.sleep(0.02)

    _recording_thread = threading.Thread(
        target=_record_audio_worker,
        args=(on_transcription_callback, on_status_callback),
        daemon=True,
    )
    _recording_thread.start()


def startVoiceListener(on_transcription_callback=None, on_status_callback=None) -> None:
    """Starts the global Hold-Alt keyboard listener."""
    print(f"Hold-Alt Voice Listener active. Hold 'Alt' for {HOLD_DURATION_SECONDS}s anywhere to speak.")

    def on_press(key):
        global _is_alt_down, _press_start_time
        try:
            if _is_alt_key(key):
                with _lock:
                    if not _is_alt_down:
                        _is_alt_down = True
                        _press_start_time = time.time()
                        threading.Thread(
                            target=_monitor_hold_trigger,
                            args=(on_transcription_callback, on_status_callback),
                            daemon=True,
                        ).start()
        except Exception as e:
            print(f"[Key Press Error]: {e}")

    def on_release(key):
        global _is_alt_down, _is_recording
        try:
            if _is_alt_key(key):
                with _lock:
                    _is_alt_down = False
                    if _is_recording:
                        _is_recording = False
                        print("\n[Voice Mode] Alt released. Stopping recording and processing speech...")
        except Exception as e:
            print(f"[Key Release Error]: {e}")

    if not keyboard or not sd:
        missing = []
        if not keyboard:
            missing.append("pynput")
        if not sd:
            missing.append("sounddevice")
        print(f"[Voice Mode Warning] Missing dependencies ({', '.join(missing)}). Voice hold-key listener is disabled.")
        return

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    listener.join()
