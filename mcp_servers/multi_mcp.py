
import asyncio
import sys
import shutil
from pathlib import Path
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Tool
from rich import print

class MultiMCP:
    """
    Manages multiple Model Context Protocol (MCP) servers.
    Handles starting, stopping, and routing tool calls to the appropriate server.
    """

    def __init__(self):
        """
        Initializes the MultiMCP manager.
        """
        self.exit_stack = AsyncExitStack()
        self.sessions = {}  # server_name -> session
        self.tools = {}     # server_name -> [Tool]
        self.server_configs = {
            "browser": {
                "command": "uv",
                "args": ["run", "mcp_servers/server_browser.py"],
            },
            "rag": {
                "command": "uv",
                "args": ["run", "mcp_servers/server_rag.py"],
            },
            "sandbox": {
                "command": "uv",
                "args": ["run", "mcp_servers/server_sandbox.py"],
            }
        }

    async def start(self):
        """
        Starts all configured MCP servers and initializes connections.
        Populates the available tools list from each server.
        """
        print("[bold green]🚀 Starting MCP Servers...[/bold green]")
        
        for name, config in self.server_configs.items():
            try:
                # Check if uv exists, else fallback to python
                cmd = config["command"]
                if cmd == "uv" and not shutil.which("uv"):
                    cmd = sys.executable
                    args = [config["args"][1]] # just the script path
                else:
                    args = config["args"]

                server_params = StdioServerParameters(
                    command=cmd,
                    args=args,
                    env=None 
                )
                
                # Connect
                read, write = await self.exit_stack.enter_async_context(stdio_client(server_params))
                session = await self.exit_stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                
                # List tools
                result = await session.list_tools()
                self.sessions[name] = session
                self.tools[name] = result.tools
                
                print(f"  ✅ [cyan]{name}[/cyan] connected. Tools: {len(result.tools)}")
                
            except Exception as e:
                print(f"  ❌ [red]{name}[/red] failed to start: {e}")

    async def stop(self):
        """
        Stops all running MCP servers and closes connections.
        """
        print("[bold yellow]🛑 Stopping MCP Servers...[/bold yellow]")
        await self.exit_stack.aclose()

    def get_all_tools(self) -> list:
        """
        Retrieves a combined list of all tools available across all connected servers.

        Returns:
            list: A list of Tool objects.
        """
        all_tools = []
        for tools in self.tools.values():
            all_tools.extend(tools)
        return all_tools

    async def function_wrapper(self, tool_name: str, *args):
        """
        A wrapper to execute a tool using positional arguments.
        Maps positional arguments to the tool's expected keyword arguments based on its schema.

        Args:
            tool_name (str): The name of the tool to execute.
            *args: Positional arguments for the tool.

        Returns:
            str: The output of the tool execution.
        """
        # Find tool definition
        target_tool = None
        for tools in self.tools.values():
            for tool in tools:
                if tool.name == tool_name:
                    target_tool = tool
                    break
            if target_tool: break
        
        if not target_tool:
            return f"Error: Tool {tool_name} not found"

        # Map positional args to keyword args based on schema
        arguments = {}
        schema = target_tool.inputSchema
        if schema and 'properties' in schema:
            keys = list(schema['properties'].keys())
            for i, arg in enumerate(args):
                if i < len(keys):
                    arguments[keys[i]] = arg
        
        try:
            result = await self.route_tool_call(tool_name, arguments)
            # Unpack CallToolResult
            if hasattr(result, 'content') and result.content:
                return result.content[0].text
            return str(result)
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"

    def get_tools_from_servers(self, server_names: list) -> list:
        """
        Retrieves tools only from the specified list of server names.

        Args:
            server_names (list): List of server names (e.g., ['browser', 'rag']).

        Returns:
            list: A list of Tool objects from the specified servers.
        """
        all_tools = []
        for name in server_names:
            if name in self.tools:
                all_tools.extend(self.tools[name])
        return all_tools

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict):
        """
        Calls a specific tool on a specific server.

        Args:
            server_name (str): The name of the server hosting the tool.
            tool_name (str): The name of the tool.
            arguments (dict): The arguments to pass to the tool.

        Returns:
            Any: The result of the tool call.

        Raises:
            ValueError: If the server is not connected.
        """
        if server_name not in self.sessions:
            raise ValueError(f"Server '{server_name}' not connected")
        
        return await self.sessions[server_name].call_tool(tool_name, arguments)

    # Helper to route tool call by finding which server has it
    async def route_tool_call(self, tool_name: str, arguments: dict):
        """
        Routes a tool call to the appropriate server by finding which server hosts the tool.

        Args:
            tool_name (str): The name of the tool.
            arguments (dict): The arguments for the tool.

        Returns:
            Any: The result of the tool call.

        Raises:
            ValueError: If the tool is not found on any connected server.
        """
        for name, tools in self.tools.items():
            for tool in tools:
                if tool.name == tool_name:
                    return await self.call_tool(name, tool_name, arguments)
        raise ValueError(f"Tool '{tool_name}' not found in any server")
