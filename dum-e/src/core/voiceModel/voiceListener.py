import sounddevice as sd
import numpy as np
from openwakeword.model import Model
from src.core.voiceModel.voiceProcess import transcribe
import time
last_trigger = 0
COOLDOWN = 3

model = Model(wakeword_models=["hey_jarvis"])

def record_command(fs=16000, silence_ms=5000, threshold=0.02):
    print("wakeup detected")
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
                print("🔇 Silence detected. Processing...")
                break

    stream.stop()
    stream.close()
    return np.array(buffer)

def startVoiceListener(on_transcription_callback=None):
    print("🟢 Listening for 'Dot'...")
    
    # We use a standard while loop instead of a callback so we can safely stop it
    stream = sd.InputStream(samplerate=16000, channels=1, dtype='int16')
    stream.start()

    model_key = list(model.models.keys())[0]
    print(f"Loaded model internal name: '{model_key}'")
    
    loop_count = 0
    
    while True:
        # openwakeword needs chunks of exactly 1280 samples
        audio_chunk, _ = stream.read(1280) 
        flat_chunk = audio_chunk.flatten()

        # Predict
        prediction = model.predict(flat_chunk)
        score = prediction[model_key]
        
       
        loop_count += 1 
        if loop_count % 12 == 0:  
            max_vol = np.max(np.abs(flat_chunk))
            print(f"  [Mic Check] Max Volume: {max_vol} | Wake word score: {score:.3f}", end="\r")
        if score > 0.5:
            # 1. CRITICAL: Stop the wake word stream so we don't crash the microphone
            stream.stop()
            stream.close()
            
            # 2. Record the user's command
            audio = record_command()
            
            # 3. Transcribe it using your function
            text = transcribe(audio)
            print(f"Transcription: {text}")
            
            # 4. 📢 Send it to the WebSocket!
            if on_transcription_callback and text:
                on_transcription_callback(text)
            
            # 5. Restart the listening stream
            print("🟢 Resuming wake word listener...")
            stream = sd.InputStream(samplerate=16000, channels=1)
            stream.start()

