"""
LLM interface module.
Provides asynchronous and synchronous clients for local and cloud inference.
Supports structured JSON generation and token streaming.
"""

import os
import json
from typing import AsyncGenerator, Optional, Tuple, Any
from openai import OpenAI, AsyncOpenAI
from src.dot.core.prompts import get_system_prompt, systemPrompt


def _load_clients() -> Tuple[AsyncOpenAI, OpenAI, str]:
    """Loads configuration and returns initialized OpenAI client instances."""
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "appConfig.json"),
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "appConfig.json"),
        os.path.abspath("appConfig.json"),
        os.path.abspath("../appConfig.json"),
    ]
    config_path = next((os.path.abspath(p) for p in possible_paths if os.path.exists(p)), None)
    backend = "cuda"
    cloud_cfg = {}

    if config_path and os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        backend = cfg.get("active_settings", {}).get("backend", "cuda")
        cloud_cfg = cfg.get("cloud", {})

    if backend == "cloud":
        base_url = cloud_cfg.get("base_url") or os.environ.get("DOT_CLOUD_BASE_URL", "https://api.openai.com/v1")
        api_key = cloud_cfg.get("api_key") or os.environ.get("DOT_CLOUD_API_KEY", "")
        model = cloud_cfg.get("model") or os.environ.get("DOT_CLOUD_MODEL", "gpt-4o-mini")
        async_cl = AsyncOpenAI(base_url=base_url, api_key=api_key)
        sync_cl = OpenAI(base_url=base_url, api_key=api_key)
        return async_cl, sync_cl, model

    # Local backend defaults to local llama-server endpoint.
    local_url = "http://127.0.0.1:11434/v1"
    async_cl = AsyncOpenAI(base_url=local_url, api_key="not-needed")
    sync_cl = OpenAI(base_url=local_url, api_key="not-needed")
    return async_cl, sync_cl, "dot-engine"


async_client, client, _model_name = _load_clients()


def _build_payload(query: str, schema: Optional[dict] = None, image_url: Optional[str] = None,
                   system_prompt: Optional[str] = None, stream: bool = False) -> dict:
    """Builds the request dictionary for model inference."""
    base_prompt = system_prompt if system_prompt is not None else get_system_prompt()
    system_message = f"<|think|> {base_prompt}"

    if image_url:
        user_content = [
            {"type": "text", "text": query},
            {"type": "image_url", "image_url": {"url": image_url}}
        ]
    else:
        user_content = query

    kwargs: dict[str, Any] = {
        "model": _model_name,
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.0,
        "stream": stream,
    }

    if schema and not stream:
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "dot_action_schema",
                "schema": schema,
                "strict": True
            }
        }

    return kwargs


async def async_llm(query: str, schema: Optional[dict] = None, image_url: Optional[str] = None,
                    system_prompt: Optional[str] = None) -> str:
    """Generates a non-blocking completion from the model."""
    kwargs = _build_payload(query=query, schema=schema, image_url=image_url, system_prompt=system_prompt, stream=False)
    response = await async_client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""


async def async_llm_stream(query: str, image_url: Optional[str] = None,
                           system_prompt: Optional[str] = None) -> AsyncGenerator[str, None]:
    """Streams completion tokens from the model as they arrive."""
    kwargs = _build_payload(query=query, schema=None, image_url=image_url, system_prompt=system_prompt, stream=True)
    response_stream = await async_client.chat.completions.create(**kwargs)
    async for chunk in response_stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield delta


def llm(query: str, schema: Optional[dict] = None, image_url: Optional[str] = None,
        system_prompt: Optional[str] = None) -> str:
    """Synchronous model completion call for background worker threads."""
    kwargs = _build_payload(query=query, schema=schema, image_url=image_url, system_prompt=system_prompt, stream=False)
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""
