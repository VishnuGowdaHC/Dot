import sounddevice as sd
import numpy as np
from openwakeword.model import Model
from src.core.voiceModel.voiceProcess import transcribe
import time
last_trigger = 0
COOLDOWN = 3

model = Model(wakeword_models=["./dot.onnx"])

def record_command(fs=16000, silence_ms=1000, threshold=0.5):
    buffer = []
    silence_samples = int((silence_ms / 1000) * fs)

    stream = sd.InputStream(samplerate=fs, channels=1)
    stream.start()

    while True:
        audio_chunk, _ = stream.read(1024)  # grab small slices
        buffer.extend(audio_chunk.flatten())

        # check last N samples for silence
        if len(buffer) > silence_samples:
            recent = np.abs(buffer[-silence_samples:])
            if np.max(recent) < threshold:
                break

    stream.stop()
    return np.array(buffer)


def callback(indata, frames, status):
    global last_trigger

    if time.time() - last_trigger < COOLDOWN:
        return
    
    last_trigger = time.time()

    audio = indata[:, 0]
    prediction = model.predict(audio)

    score = prediction["dot"]

    if score > 0.5:
        print("Wake word detected!")
        audio = record_command()
        transcribe(audio)

def startVoiceListener():
    with sd.InputStream(channels=1, samplerate=16000, callback=callback):
        print("Listening...")
    
    while True:
        pass