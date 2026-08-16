from ollama import chat
from src.dot.core.prompts import systemPrompt


def llm(query, schema: dict | None = None):
    response = chat(
        model='dot-engine',
        messages=[
                    {'role': 'system', 'content': systemPrompt}, 
                    {'role': 'user', 'content': query}
                ],
        stream=False, 
        think=True,
        format=schema,
        options={"temperature": 0.4}
    )
   
    return response['message']['content']

