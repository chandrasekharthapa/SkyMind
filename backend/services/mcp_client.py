import os
from dotenv import load_dotenv
load_dotenv()

from mcp import ClientSession
from contextlib import asynccontextmanager
from mcp.client.stdio import stdio_client, StdioServerParameters
from contextlib import AsyncExitStack

# Configure the stdio server parameters for the local node process
# Launch the node executable with the node.js MCP server script
_script_path = os.path.abspath(
    os.path.normpath(
        os.path.join(
            os.path.dirname(__file__),   # backend/services
            "..", "india-flight-mcp", "src", "mcp", "stdio_server.js"
        )
    )
)
_server_params = StdioServerParameters(
    command="node",
    args=[_script_path],
    cwd=os.path.dirname(_script_path),
)

# Refactored MCP gateway: open a fresh stdio client per use.

@asynccontextmanager
async def mcp_gateway():
    """Async context manager that provides a fresh MCP ClientSession.

    Usage:
        async with mcp_gateway() as client:
            # use client for MCP calls
    The client and underlying stdio process are cleaned up automatically when
    the context exits, avoiding lingering cancel scopes.
    """
    # Open stdio client transport
    async with stdio_client(_server_params) as transport:
        # Create MCP client session
        async with ClientSession(transport[0], transport[1]) as client:
            await client.initialize()
            yield client

import asyncio

_exit_stack = None
_shared_client = None
_client_lock = asyncio.Lock()

async def get_client() -> ClientSession:
    """Return a cached/shared MCP ClientSession, keeping it alive using AsyncExitStack."""
    global _exit_stack, _shared_client
    async with _client_lock:
        if _shared_client is not None:
            return _shared_client
        
        _exit_stack = AsyncExitStack()
        try:
            transport = await _exit_stack.enter_async_context(stdio_client(_server_params))
            client = await _exit_stack.enter_async_context(ClientSession(transport[0], transport[1]))
            await client.initialize()
            _shared_client = client
            return _shared_client
        except Exception as e:
            await _exit_stack.aclose()
            _exit_stack = None
            _shared_client = None
            raise e

