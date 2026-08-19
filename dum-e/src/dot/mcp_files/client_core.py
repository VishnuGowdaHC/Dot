from fastmcp import Client
import traceback
import sys
from src.dot.memory.vector_store import get_all_services
from src.dot.memory.vector_store import get_full_service_tools_text

BYPASS_SERVICES = {"browser", "native", "os_tools"}
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
        print(f"\n[Server Error] Failed to fetch tools from '{server}'", file=sys.stderr)
        print(f"Error Message: {str(e)}", file=sys.stderr)
        print("-" * 40, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)  # Prints the full stack trace to the console
        print("-" * 40 + "\n", file=sys.stderr)
        return []

def add_server_tools():
    available_services = get_all_services()
    
    bypass_tools_text = "\n\n".join(
        f"<{svc.upper()}_TOOLS>\n{get_full_service_tools_text(svc)}\n</{svc.upper()}_TOOLS>"
        for svc in BYPASS_SERVICES if svc in available_services
    )
    prompt = f"""
            {bypass_tools_text}
            """

    return prompt

if __name__ == "__main__":
    print(add_server_tools())
