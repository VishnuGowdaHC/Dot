from ollama import chat
import asyncio
import json
from src.core.prompts import systemPrompt

async def routeToLLM(websocket, text):
    response = chat(
        model='dot-engine',
        messages=[
                    {'role': 'system', 'content': systemPrompt}, 
                    {'role': 'user', 'content': text}
                ],
        stream=True, 
        think=True
    )

    
    for chunk in response:
        await websocket.send_text(json.dumps({"type": "stream", "data": chunk["message"]["content"]}))
    
    
    await asyncio.sleep(0.02)

    return await websocket.send_text(json.dumps({"type": "result", "data": "Task Executed"}))