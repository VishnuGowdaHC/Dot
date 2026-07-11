from faster_whisper import WhisperModel
import asyncio
from src.core.intentOpener import routeAppOpener

whisper = WhisperModel("small.en", device="cpu", compute_type="int8")

hallucinations = [
                "thank you", "thank you.", "thanks for watching", 
                "subscribe", "thank you for watching.", "thanks.","Thank you.","Thanks for watching!"
            ] 

def transcribe(audio):
    
    segments, _ = whisper.transcribe(audio, beam_size=5)
    text = " ".join([s.text for s in segments])

    print("In transcribe function: \n", text)
    text_norm = text.strip().lower()
    if not text_norm or text_norm in [h.lower() for h in hallucinations]:
        print("Hallucination detected. Routing to LLM...")
        return
    
    asyncio.run(routeAppOpener(text))
    return text

    

