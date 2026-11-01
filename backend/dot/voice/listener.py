"""
Hold-Alt voice listener module.
Records microphone audio while the user holds the Alt key.
"""

import time
import threading
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
HOLD_DURATION_SECONDS = 1.0
SAMPLE_RATE = 16000
CHUNK_SIZE = 1024

_is_alt_down = False
_press_start_time = 0.0
_is_recording = False
_recording_thread = None
_lock = threading.Lock()


def _is_alt_key(key) -> bool:
    """Verifies if the pressed key is an Alt key variant."""
    if not keyboard:
        return False
    return key in (
        keyboard.Key.alt,
        keyboard.Key.alt_l,
        keyboard.Key.alt_r,
        getattr(keyboard.Key, "alt_gr", None),
    )


def _record_audio_worker(on_transcription_callback, on_status_callback) -> None:
    """Records audio from the microphone until Alt key release."""
    global _is_recording, _is_alt_down

    print("\n[Voice Mode] Alt held. Recording speech. Release Alt when done.")
    if on_status_callback:
        on_status_callback("recording")

    buffer = []
    stream = None
    try:
        stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32")
        stream.start()

        max_chunks = int(25.0 * (SAMPLE_RATE / CHUNK_SIZE))
        chunk_count = 0

        while _is_recording and chunk_count < max_chunks:
            audio_chunk, _ = stream.read(CHUNK_SIZE)
            buffer.extend(audio_chunk.flatten())
            chunk_count += 1

    except Exception as stream_err:
        print(f"[Voice Mode Error] Audio stream failed: {stream_err}")
    finally:
        if stream:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    if on_status_callback:
        on_status_callback("transcribing")

    # Verify minimum speech duration of 0.4 seconds.
    if len(buffer) >= int(0.4 * SAMPLE_RATE):
        audio_data = np.array(buffer, dtype=np.float32)
        print(f"[Voice Mode] Recording finished ({len(audio_data) / SAMPLE_RATE:.2f}s). Transcribing...")

        try:
            text = transcribe(audio_data)
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
        print("[Voice Mode] Recording was too short (< 0.4s). Ignored.")

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
        time.sleep(0.03)

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
        print(f"[Voice Mode Warning] Missing audio/keyboard dependencies ({', '.join(missing)}). Voice hold-key listener is disabled.")
        return

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    listener.join()

