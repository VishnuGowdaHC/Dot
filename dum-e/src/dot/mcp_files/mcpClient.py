from fastmcp import Client
from fastmcp.client.sampling import SamplingMessage, SamplingParams, RequestContext
import json
from src.dot.mcp_files.registry import load_server_config
from src.dot.core.llm import llm


async def sampling_handler(
    messages: list[SamplingMessage],
    params: SamplingParams,
    context: RequestContext,
) -> str:
    text_parts = []
    image_url = None

    for m in messages:
        content = m.content
        # TextContent exposes .text ; ImageContent exposes .data + .mimeType
        if hasattr(content, "text"):
            text_parts.append(content.text)
        elif hasattr(content, "data"):
            image_url = f"data:{content.mimeType};base64,{content.data}"

    query = "\n".join(text_parts) if text_parts else "Describe the image."
    system_prompt = params.systemPrompt or "Respond in plain text only. No JSON."

    return llm(query=query, image_url=image_url, system_prompt=system_prompt)


def get_multi_server_client() -> Client:
    config = load_server_config()
    return Client(config, sampling_handler=sampling_handler)


async def execute_mcp_tool(active_client: Client, tool_service: str, tool_name: str, tool_args):
    result = await active_client.call_tool(tool_name, tool_args)

    if result.content:
        text = result.content[0].text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    return None