from ollama import chat
from pydantic import BaseModel


class promptAnalysis(BaseModel):
    language: str
    complexity_score: float
    summary: str
    command: str
    permission: str

def routeToLLM(text):
    response = chat(
        model='qwen2.5-coder:3b-instruct',
        messages=[{'role': 'user', 'content': text}],
        format=promptAnalysis.model_json_schema()
    )

    result = promptAnalysis.model_validate_json(response.message.content)

    print(f"Lang: {result.language}, Score: {result.complexity_score} Summary: {result.summary} Command: {result.command} Permission: {result.permission}")

    return 