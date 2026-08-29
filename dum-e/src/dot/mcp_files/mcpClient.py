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
    # Determine candidate tool names (prefixed and unprefixed)
    raw_name = tool_name
    if tool_service and tool_name.startswith(f"{tool_service}_"):
        raw_name = tool_name[len(tool_service) + 1:]

    prefixed_name = f"{tool_service}_{raw_name}" if tool_service else tool_name
    candidates = [tool_name, raw_name, prefixed_name]
    # Remove duplicates while preserving order
    seen = set()
    unique_candidates = [c for c in candidates if not (c in seen or seen.add(c))]

    last_error = None
    result = None

    for name in unique_candidates:
        try:
            result = await active_client.call_tool(name, tool_args or {})
            break
        except Exception as err:
            last_error = err

    if result is None:
        raise RuntimeError(f"Tool '{tool_name}' failed to execute on server '{tool_service}': {last_error}")

    if hasattr(result, "content") and result.content:
        first_item = result.content[0]
        if hasattr(first_item, "text"):
            text = first_item.text
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return text
        elif hasattr(first_item, "data"):
            return f"[Binary/Image Content received: {getattr(first_item, 'mimeType', 'unknown')}]"
        return str(first_item)

    return result