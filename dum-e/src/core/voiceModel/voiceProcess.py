from faster_whisper import WhisperModel
from src.core.intentRouter import routeIntent

whisper = WhisperModel("base", device="cpu")

def transcribe(audio):
    
    segments, _ = whisper.transcribe(audio)
    text = " ".join([s.text for s in segments])
    routeIntent(text)

    

