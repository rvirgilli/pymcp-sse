# pymcp-sse General Usage & Best Practices

This document provides guidance on using the `pymcp_sse` library effectively, incorporating best practices relevant to this specific implementation.

## Server (`pymcp_sse.server.BaseMCPServer`)

### Initialization

```python
from pymcp_sse.server import BaseMCPServer

server = BaseMCPServer("My Awesome Server")
```

### Tool Registration

Use the `@server.register_tool()` decorator for asynchronous functions.

```python
@server.register_tool("get_weather")
async def get_weather_tool(location: str):
    # ... tool logic ...
    return {"temp": 25, "condition": "sunny"}
```

- Ensure tool functions are `async def`.
- Type hints are recommended for automatic parameter handling (though not strictly enforced by base `pymcp_sse` yet).

### Accessing Session ID in Tools

If a tool needs to send a push notification back to the *specific* client that called it, include `server_session_id: str = None` in its signature. The `pymcp_sse` server logic automatically injects the correct session ID.

```python
import asyncio
from pymcp_sse.server import BaseMCPServer # Assume server is an instance
from pymcp_sse.server.notifications import push_notification

server = BaseMCPServer("My Job Server")

@server.register_tool("schedule_job")
async def schedule_job_tool(job_details: str, server_session_id: str = None):
    if not server_session_id:
        raise ValueError("Session ID required to report job status")

    # ... start job ...
    job_id = "job_123"

    async def report_status():
        await asyncio.sleep(10) # Simulate work
        # Use the push_notification function with the server instance and session ID
        await push_notification(
            server=server,
            server_session_id=server_session_id, 
            type_name="info", 
            message=f"Job {job_id} completed",
            data={"job_id": job_id}
        )

    asyncio.create_task(report_status())
    return {"job_id": job_id, "status": "scheduled"}
```
*(Note: The `push_notification` helper function requires the `server` instance as its first argument.)*

### Running the Server

The `BaseMCPServer` provides two main ways to run the server:

1.  **`server.run(...)` (Simple Execution):**
    - Use this method for servers that *do not* require long-running background tasks managed concurrently with the web server itself.
    - It's a straightforward wrapper around `uvicorn.run()`.
    ```python
    if __name__ == "__main__":
        # You can pass additional arguments for uvicorn.run here,
        # e.g., timeout_keep_alive=65
        server.run(host="0.0.0.0", port=8080, log_level="info")
    ```
    - For simple startup/shutdown logic (like initializing a resource), you can use FastAPI's lifespan manager within `_create_app()`, but this is not suitable for persistent background tasks.

2.  **`await server.run_with_tasks(...)` (Concurrent Execution):**
    - Use this `async` method when your server needs to run one or more persistent asynchronous tasks *alongside* the Uvicorn web server (e.g., polling an external service, running a notification scheduler loop).
    - It internally manages the Uvicorn server and your tasks using `asyncio.gather` and handles graceful shutdown.
    ```python
    import asyncio
    
    async def my_background_task():
        while True:
            print("Background task running...")
            await asyncio.sleep(10)
    
    async def my_shutdown_callback():
        print("Shutting down background task...")
        # Add cleanup logic here
    
    async def main():
        await server.run_with_tasks(
            host="0.0.0.0", 
            port=8080, 
            log_level="info",
            concurrent_tasks=[my_background_task], # Pass list of async functions/coroutines
            shutdown_callbacks=[my_shutdown_callback] # Pass list of async functions/coroutines
        )
    
    if __name__ == "__main__":
        asyncio.run(main())
    ```
    - Pass **awaitable functions** (like `async def` function names) or directly created coroutine objects to `concurrent_tasks` and `shutdown_callbacks`.
    - `run_with_tasks` handles `KeyboardInterrupt` (Ctrl+C) to trigger shutdown, runs callbacks, and cancels all tasks.
    - See `examples/server_tasks/main.py` for a practical example.

### Host and Port Configuration

Both `run()` and `run_with_tasks()` determine the host and port using the following precedence:

1.  Explicit `host`/`port` arguments passed to the method.
2.  `MCP_HOST` / `MCP_PORT` environment variables.
3.  Default values (`0.0.0.0` for host, `8000` for port).

## Client (`pymcp_sse.client.BaseMCPClient` & `MultiMCPClient`)

### Initialization

**Single Server:**
```python
from pymcp_sse.client import BaseMCPClient

# Configure timeouts for stability (read timeout > server ping interval)
client = BaseMCPClient(
    "http://server-url:8080",
    http_read_timeout=65,
    http_connect_timeout=10
)
```

**Multiple Servers:**
```python
from pymcp_sse.client import MultiMCPClient

servers = {
    "basic_server": "http://server_basic:8101",
    "tasks_server": "http://server_tasks:8102"
}
# Configure timeouts for stability (read timeout > server ping interval)
multi_client = MultiMCPClient(
    servers,
    http_read_timeout=65,
    http_connect_timeout=10
)
```

### Connection & Initialization

**Single Server:**
```python
connected = await client.connect()
if connected:
    initialized = await client.initialize()
    if initialized:
        print("Ready to call tools!")
```

**Multiple Servers:**
```python
connection_results = await multi_client.connect_all()
# connection_results is a dict: {"server_alias": True/False}
```

- `connect()` handles the health check and establishes the SSE connection.
- `initialize()` sends the MCP initialize request and processes the response.
- `connect_all()` handles both steps for all configured servers.
- The library automatically handles reconnections and reinitialization (See `http_sse_notes.md`).

### Calling Tools

**Single Server:**
```python
result = await client.call_tool("tool_name", param1="value1", param2=123)
```

**Multiple Servers:**
```python
result = await multi_client.call_tool("basic_server", "tool_name", param1="value1")
```

- Parameters are passed as keyword arguments.
- The library handles formatting the JSON-RPC request and awaiting the response via SSE.

### Handling Push Notifications

Register an asynchronous callback function to receive notifications.

**Single Server:**
```python
async def my_notification_handler(type_name: str, message: str, data: Optional[Dict], timestamp: Optional[str]):
    print(f"[{type_name}] {message} Data: {data}")

client.notification_handler = my_notification_handler
```
*(Note: Assign directly to `notification_handler`, not `add_notification_callback`)*

**Multiple Servers:**
```python
async def my_multi_notification_handler(server_alias: str, type_name: str, message: str, data: Optional[Dict], timestamp: Optional[str]):
    print(f"[{server_alias} - {type_name}] {message} Data: {data}")

multi_client.notification_handler = my_multi_notification_handler
```
*(Note: Assign directly to `notification_handler`, not `add_notification_callback`)*

- The callback receives the notification parameters (`type_name`, `message`, `data`, `timestamp`).
- For `MultiMCPClient`, the callback also receives the `server_alias` from which the notification originated.

### Closing Connections

Always close the client gracefully.

```python
await client.close()
# or
await multi_client.close()
```

- This cancels background tasks (SSE listener) and closes the HTTP client.

## Logging

Use the `pymcp_sse.utils.configure_logging` function to set the desired logging level (e.g., "INFO", "DEBUG").

```python
from pymcp_sse.utils import configure_logging

configure_logging(level="DEBUG") # Show detailed logs
``` 