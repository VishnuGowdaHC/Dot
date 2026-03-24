from faster_whisper import WhisperModel
from src.core.intentRouter import routeIntent

whisper = WhisperModel("small.en", device="cpu", compute_type="int8")

def transcribe(audio):
    
    segments, _ = whisper.transcribe(audio, beam_size=5)
    text = " ".join([s.text for s in segments])
    print("In transcribe function: \n", text)
    routeIntent(text)
    return text

    

