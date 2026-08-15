from ollama import chat
import asyncio
import json
from core.prompts import systemPrompt


def llm(query, schema: dict | None = None):
    response = chat(
        model='dot-engine',
        messages=[
                    {'role': 'system', 'content': systemPrompt}, 
                    {'role': 'user', 'content': query}
                ],
        stream=False, 
        think=True,
        format=schema
    )
   
    return response['message']['content']

