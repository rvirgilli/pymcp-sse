# pymcp-sse: Python MCP over SSE Library

A lightweight, flexible implementation of the Model Context Protocol (MCP) for Python applications, specializing in robust HTTP/SSE transport.

## Features

- **Modular Framework**: Clean implementation of `BaseMCPServer`, `BaseMCPClient`, and `MultiMCPClient` using `pymcp_sse`.
- **HTTP/SSE Transport**: Support for HTTP/SSE with automatic session management, configurable timeouts, and reconnection handling.
- **Tool Registration**: Simple decorator-based tool registration and discovery.
- **Server Push**: Built-in support for push notifications and periodic pings.
- **LLM Integration**: Includes `BaseLLMClient` abstraction for easy integration with various LLM providers (Anthropic example provided).
- **Flexible Logging**: Configurable logging via `pymcp_sse.utils`.

## Installation

To install the library locally for development:

```bash
# Navigate to the directory containing pyproject.toml
cd /path/to/your/pymcp-sse

# Install in editable mode
pip install -e .
```

(Once published, installation via `pip install pymcp-sse` will be available.)

## Basic Usage

### Creating an MCP Server

```python
from pymcp_sse.server import BaseMCPServer

# Create a server instance
server = BaseMCPServer("My Simple Server")

# Register tools using the decorator
@server.register_tool("echo")
async def echo_tool(text: str):
    return {"response": f"Echo: {text}"}

# Run the server
if __name__ == "__main__":
    # Additional kwargs are passed to uvicorn.run (e.g., timeout_keep_alive=65)
    server.run(host="0.0.0.0", port=8000)
```

### Creating a Single Client

```python
import asyncio
from pymcp_sse.client import BaseMCPClient

async def main():
    # Configure timeouts for stability (read timeout > server ping interval)
    client = BaseMCPClient(
        "http://localhost:8000",
        http_read_timeout=65, 
        http_connect_timeout=10
    )
    
    try:
        # Connect and initialize
        if await client.connect() and await client.initialize():
            # Call a tool
            result = await client.call_tool("echo", text="Hello, world!")
            print(f"Tool Result: {result}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
```

### Creating a Multi-Server Client

```python
import asyncio
from pymcp_sse.client import MultiMCPClient

async def main():
    servers = {
        "server1": "http://localhost:8001",
        "server2": "http://localhost:8002"
    }
    # Configure timeouts for stability (read timeout > server ping interval)
    client = MultiMCPClient(
        servers,
        http_read_timeout=65,
        http_connect_timeout=10
    )
    
    try:
        # Connect to all servers
        await client.connect_all()
        
        # Call a tool on a specific server
        if client.clients.get("server1") and client.clients["server1"].initialized:
            result = await client.call_tool("server1", "echo_s1", text="Hello from MultiClient!")
            print(f"Server 1 Echo Result: {result}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
```

## Documentation

For more detailed usage instructions, notes on the HTTP/SSE implementation, and guides on LLM integration, please refer to the documentation in the `docs/` directory.

## Examples

See the `examples/` directory for complete working examples, including:
- Multiple servers with different tools
- A client application with an LLM agent (`AnthropicLLMClient` example)
- A launcher script (`run_all.py`) to run all components.

## License

MIT
