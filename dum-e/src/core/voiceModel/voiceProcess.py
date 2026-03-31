from faster_whisper import WhisperModel
from src.core.intentOpener import routeAppOpener

whisper = WhisperModel("small.en", device="cpu", compute_type="int8")

hallucinations = [
                "thank you", "thank you.", "thanks for watching", 
                "subscribe", "thank you for watching.", "thanks."
            ] 

def transcribe(audio):
    
    segments, _ = whisper.transcribe(audio, beam_size=5)
    text = " ".join([s.text for s in segments])

    print("In transcribe function: \n", text)
    if not text or text in hallucinations:
        print("Hallucination detected. Routing to LLM...")
        return
    
    routeAppOpener(text)
    return text

    

