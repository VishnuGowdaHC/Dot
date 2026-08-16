# quick standalone check
import asyncio
from src.dot.mcp_files.mcpClient import get_multi_server_client

async def check():
    client = get_multi_server_client()
    async with client as c:
        tools = await c.list_tools()
        for t in tools.tools if hasattr(tools, 'tools') else tools:
            print(t.name)

asyncio.run(check())