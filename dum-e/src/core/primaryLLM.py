from ollama import chat
from src.core.agents.masterAgent import masterAgent
import asyncio
import json

masterPrompt ="""
You are a Router. Your only job is to break user requests into independent steps and assign them to the correct agent. Do not execute the tasks or answer the user directly.

You must output ONLY valid, minified JSON. No explanations. No markdown formatting.

AGENTS:
1 = Vision (Images, UI, OCR, visual context)
2 = System (Local files, terminal, code execution)
3 = Browser (Web search, URLs, scraping)
4 = Master (Combining results, pure text logic)

SCHEMA:
[{"s": <step_int>, "a": <agent_int>, "cmd": "<short_command>", "dep": [<step_ints>]}]

EXAMPLE 1
User: "Look at this screenshot of a graph and download the dataset from the URL mentioned in it."
Output:
[{"s":1,"a":1,"cmd":"Extract URL from screenshot","dep":[]},{"s":2,"a":2,"cmd":"Download dataset from extracted URL","dep":[1]}]

EXAMPLE 2
User: "Search the web for the latest Python version and check what version I have installed."
Output:
[{"s":1,"a":3,"cmd":"Search web for latest Python version","dep":[]},{"s":2,"a":2,"cmd":"Run python --version in terminal","dep":[]},{"s":3,"a":4,"cmd":"Compare installed version with latest version","dep":[1,2]}]
"""

async def routeToLLM(websocket, text):
    response = chat(
        model='dot-engine',
        messages=[
                    {'role': 'system', 'content': masterPrompt}, 
                    {'role': 'user', 'content': text}
                ],
        stream=False, 
        think=False
    )
    print("in routeToLLM function" )

 
    await masterAgent(websocket, response["message"]["content"]) 
    
    await asyncio.sleep(0.02)

    return await websocket.send_text(json.dumps({"type": "result", "data": "Task Executed"}))