from openai import OpenAI
from src.dot.core.prompts import systemPrompt

# Point the standard client directly to your local llama.cpp endpoint
client = OpenAI(
    base_url="http://127.0.0.1:11434/v1",
    api_key="not-needed"
)

def llm(query: str, schema: dict | None = None, image_url: str | None = None,
        system_prompt: str | None = None) -> str:
    """
    system_prompt: overrides the default agent (Dot ReAct) system prompt.
    Pass a plain description-task prompt here for one-off calls (e.g. vision
    summarization) that shouldn't be routed through the JSON action schema.
    """
    base_prompt = system_prompt if system_prompt is not None else systemPrompt
    system_message = f"<|think|> {base_prompt}"
    
    # Use structured content block only when an image is provided
    if image_url:
        user_content = [
            {"type": "text", "text": query},
            {"type": "image_url", "image_url": {"url": image_url}}
        ]
    else:
        user_content = query
        
    kwargs = {
        "model": "dot-engine",
        "messages": [
            {"role": "system", "content": system_message}, 
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.0,
        "stream": False
    }
    
    if schema:
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "dot_action_schema",
                "schema": schema,
                "strict": True
            }
        }
        
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""


VISION_DESCRIBE_PROMPT = (
    "You are an image description assistant. Describe only what is visibly "
    "present in the screenshot, in 2-3 concise sentences. Do not output JSON, "
    "do not roleplay as any assistant persona — plain text only."
)

def describe_image(question: str, image_url: str) -> str:
    """Thin wrapper for one-off vision calls (e.g. screenshot tools) that
    keeps them out of the ReAct agent's system prompt/schema entirely."""
    return llm(query=question, image_url=image_url, system_prompt=VISION_DESCRIBE_PROMPT)