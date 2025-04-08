# pymcp-sse: Python MCP over SSE Library

A lightweight, flexible implementation of the Model Context Protocol (MCP) for Python applications, specializing in robust HTTP/SSE transport.

## Features

- **Modular Framework**: Clean implementation of `BaseMCPServer`, `BaseMCPClient`, and `MultiMCPClient`.
- **HTTP/SSE Transport**: Robust HTTP/SSE implementation with automatic session management, configurable timeouts, and reconnection handling.
- **Concurrent Task Execution**: `BaseMCPServer.run_with_tasks()` method for easily running servers with persistent background asynchronous tasks.
- **Tool Registration & Discovery**: Simple decorator-based tool registration (`@server.register_tool()`) and a standard `describe_tools` endpoint for clients to dynamically query detailed tool capabilities (parameters, descriptions).
- **Server Push**: Built-in support for server-initiated push notifications to clients and periodic keep-alive pings. Includes `NotificationScheduler` helper class.
- **LLM Integration**: Includes `BaseLLMClient` abstraction for easy integration with various LLM providers (an Anthropic Claude example is provided).
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

### Creating an MCP Server (Simple)

```python
from pymcp_sse.server import BaseMCPServer
from pymcp_sse.utils import configure_logging

configure_logging() # Configure logging (optional)

# Create a server instance
server = BaseMCPServer("My Simple Server")

# Register tools using the decorator
# Type hints are used by describe_tools
@server.register_tool("echo")
async def echo_tool(text: str) -> dict:
    '''Echoes the provided text back.'''
    return {"response": f"Echo: {text}"}

# Run the server using the standard method
if __name__ == "__main__":
    # Additional kwargs are passed to uvicorn.run (e.g., timeout_keep_alive=65)
    server.run(host="0.0.0.0", port=8000)
```

### Creating an MCP Server (with Background Tasks)

```python
import asyncio
from pymcp_sse.server import BaseMCPServer
from pymcp_sse.utils import configure_logging

configure_logging() # Configure logging (optional)

# Create a server instance
server = BaseMCPServer("My Background Task Server")

# Define your background task
async def my_periodic_task():
    while True:
        print("Task running...")
        await asyncio.sleep(5)

# Define a shutdown callback
async def cleanup():
    print("Cleaning up...")

# Run the server using run_with_tasks
async def main():
    await server.run_with_tasks(
        host="0.0.0.0", 
        port=8001,
        concurrent_tasks=[my_periodic_task],
        shutdown_callbacks=[cleanup]
    )

if __name__ == "__main__":
    asyncio.run(main())
```

### Creating a Single Client

```python
import asyncio
from pymcp_sse.client import BaseMCPClient
from pymcp_sse.utils import configure_logging

configure_logging() # Configure logging (optional)

async def main():
    # Configure timeouts for stability (read timeout > server ping interval)
    client = BaseMCPClient(
        "http://localhost:8000", # Point to your server
        http_read_timeout=65, 
        http_connect_timeout=10
    )
    
    try:
        # Connect and initialize
        if await client.connect() and await client.initialize():
            print(f"Connected. Available tools: {client.available_tools}")
            # Call a tool
            result = await client.call_tool("echo", text="Hello, world!")
            print(f"Tool Result: {result}")
            # Assign a notification handler if needed
            # client.notification_handler = your_async_handler
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
```

### Creating a Multi-Server Client

```python
import asyncio
from pymcp_sse.client import MultiMCPClient
from pymcp_sse.utils import configure_logging

configure_logging() # Configure logging (optional)

async def main():
    # Use servers from the examples section
    servers = {
        "server_basic": "http://localhost:8101",
        "server_tasks": "http://localhost:8102"
    }
    # Configure timeouts for stability (read timeout > server ping interval)
    client = MultiMCPClient(
        servers,
        http_read_timeout=65,
        http_connect_timeout=10
    )
    
    try:
        # Connect to all servers (automatically fetches tool details if describe_tools exists)
        connection_results = await client.connect_all()
        print(f"Connection Results: {connection_results}")
        
        # Get info about connected servers (including tool details)
        server_info = client.get_server_info()
        print("\nServer Info:")
        for name, info in server_info.items():
             print(f"- {name}: Status={info['status']}, Tools={len(info.get('available_tools', []))}, Details Fetched={bool(info.get('tool_details'))}")

        # Call a tool on a specific server
        if server_info.get("server_basic", {}).get("status") == "connected":
            result = await client.call_tool("server_basic", "echo", text="Hello from MultiClient!")
            print(f"\nServer Basic Echo Result: {result}")
    except Exception as e:
        print(f"An error occurred: {e}")    
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
```

## Documentation

For more detailed usage instructions, notes on the HTTP/SSE implementation, guides on LLM integration, and the protocol specification, please refer to the documentation in the `docs/` directory.

## Examples

See the `examples/` directory for complete working examples, including:
- **`server_basic`**: Demonstrates a simple server using `server.run()`.
- **`server_tasks`**: Demonstrates a server with background tasks (notification scheduler) using `server.run_with_tasks()`.
- **`client`**: A multi-server client using `MultiMCPClient` and an `LLMAgent` to interact with both servers via natural language. Requires an API key (set `ANTHROPIC_API_KEY` in a `.env` file in the project root).
- **`run_all.py`**: A launcher script to easily start `server_basic`, `server_tasks`, and the `client` simultaneously.
- **`notification_listener.py`**: A simple standalone client for receiving push notifications from any compatible server.

## License

MIT
