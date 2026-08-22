import os
import json
from openai import OpenAI
from src.dot.core.prompts import systemPrompt


def _load_client():
    config_path = os.path.join(
        os.path.dirname(__file__),   # current file dir: Dot/dum-e/src/dot/core
        "..", "..", "..",            
        "appConfig.json"             
    )
    backend = "cuda"
    cloud_cfg = {}

    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        backend = cfg.get("active_settings", {}).get("backend", "cuda")
        cloud_cfg = cfg.get("cloud", {})

    if backend == "cloud":
        base_url = cloud_cfg.get("base_url") or os.environ.get("DOT_CLOUD_BASE_URL", "https://api.openai.com/v1")
        api_key = cloud_cfg.get("api_key") or os.environ.get("DOT_CLOUD_API_KEY", "")
        model = cloud_cfg.get("model") or os.environ.get("DOT_CLOUD_MODEL", "gpt-4o-mini")

        return OpenAI(base_url=base_url, api_key=api_key), model

    # Local (cuda / cpu) — always the same fixed local endpoint.
    return OpenAI(base_url="http://127.0.0.1:11434/v1", api_key="not-needed"), "dot-engine"

client, _model_name = _load_client()


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
        "model": _model_name,
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

