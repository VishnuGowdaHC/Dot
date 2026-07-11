import asyncio
from fastmcp import Client
import os
from dotenv import load_dotenv

load_dotenv()
mcp_config = {
    "mcpServers": {
        "github": {
        "command": "../MCPServers/github-mcp-server.exe",
        "args": ["stdio"],
        "env": {
          "GITHUB_PERSONAL_ACCESS_TOKEN": os.getenv("GITHUB_TOKEN")
        }
      },

    }
}

client = Client(mcp_config)

async def main():

    async with client:
        tools = await client.list_tools()
        print([t.name for t in tools])

        my_profile = await client.call_tool("get_me", {})
        print(f"Profile Data: {my_profile}\n")

asyncio.run(main())
