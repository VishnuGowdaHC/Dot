from pydantic import BaseModel
from ollama import chat

class CodeAnalysis(BaseModel):
    language: str
    complexity_score: int
    summary: str

# Ollama will force the model to output a valid JSON matching this schema
response = chat(
    model='qwen2.5-coder:3b-instruct',
    messages=[{'role': 'user', 'content': 'Analyze this: def add(a,b): return a+b'}],
    format=CodeAnalysis.model_json_schema()
)

# You can then parse the string content directly back into your object
analysis = CodeAnalysis.model_validate_json(response.message.content)
print(f"Lang: {analysis.language}, Score: {analysis.complexity_score} Summary: {analysis.summary}")