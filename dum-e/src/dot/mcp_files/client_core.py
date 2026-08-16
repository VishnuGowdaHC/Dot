from fastmcp import Client

async def fetch_server_tools(server: str, server_settings: dict) -> list:
    print("In fetch_server_tools")
    print(server, server_settings)
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
                    "toolName": f"{server}_{tool.name}",
                    "description": tool.description,
                    "inputSchema": tool.inputSchema
                })

            return server_tools
    except Exception as e:
        print("In fetch_server_tools: ",e)
        return []
