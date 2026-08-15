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

async def fetch(server, server_settings):
    try:
        client = Client({
            "mcpServers": {
                server: server_settings
            }
        })

        async with client as active_session:
            tools = await active_session.list_tools()
            tools_arr = getattr(tools, 'tools', tools)

            server_tools = []
            for tool in tools_arr:
                server_tools.append({
                    "service": server,
                    "toolName": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.inputSchema
                })

            return server_tools
    except Exception as e:
        print(e)
        return []


async def main():
    tasks = [
        fetch(server, server_settings) 
        for server, server_settings in mcp_config['mcpServers'].items()
    ]

    results = await asyncio.gather(*tasks)
    
    all_tools = [tool for tool in results]

  
        
    

asyncio.run(main())
