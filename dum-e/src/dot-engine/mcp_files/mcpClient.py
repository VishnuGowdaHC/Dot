from fastmcp import Client
import asyncio

async def fetch_server_tools(server: str, server_settings: dict) -> list:
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
        print("In fetch_server_tools: ",e)
        return []

async def execute_mcp_tool(server_settings: dict, tool_name: str, tool_args: dict):
    async with Client({
        "mcpServers": {
            'target_server': server_settings
        }
    }) as active_session:
        
        result = await active_session.call_tool(
            name=tool_name,
            arguments=tool_args
        )

        return result.data
