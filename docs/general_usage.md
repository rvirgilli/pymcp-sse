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
from pymcp_sse.server import push_notification # Import the push helper

@server.register_tool("schedule_job")
async def schedule_job_tool(job_details: str, server_session_id: str = None):
    if not server_session_id:
        raise ValueError("Session ID required to report job status")

    # ... start job ...
    job_id = "job_123"

    async def report_status():
        await asyncio.sleep(10) # Simulate work
        await push_notification(
            server_session_id=server_session_id, 
            type="info", 
            message=f"Job {job_id} completed",
            data={"job_id": job_id}
        )

    asyncio.create_task(report_status())
    return {"job_id": job_id, "status": "scheduled"}
```

### Running the Server

```python
if __name__ == "__main__":
    # You can pass additional arguments for uvicorn.run here,
    # e.g., timeout_keep_alive=65
    server.run(host="0.0.0.0", port=8080, log_level="info")
```

- `server.run()` handles starting the Uvicorn server.
- Background tasks (like periodic notifications in the examples) should typically be added using `app.add_event_handler("startup", your_async_task)` *before* calling `server.run()`, where `app` is the FastAPI app instance inside `BaseMCPServer` (`server.app`).

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
    "main_server": "http://server1:8080",
    "aux_server": "http://server2:8081"
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
result = await multi_client.call_tool("main_server", "tool_name", param1="value1")
```

- Parameters are passed as keyword arguments.
- The library handles formatting the JSON-RPC request and awaiting the response via SSE.

### Handling Push Notifications

Register an asynchronous callback function to receive notifications.

**Single Server:**
```python
asnyc def my_notification_handler(params: dict):
    print(f"Received notification: {params}")

client.add_notification_callback(my_notification_handler)
```

**Multiple Servers:**
```python
asnyc def my_multi_notification_handler(server_alias: str, params: dict):
    print(f"Notification from {server_alias}: {params}")

multi_client.add_notification_callback(None, my_multi_notification_handler) # None = all servers
# Or for a specific server:
# multi_client.add_notification_callback("main_server", my_specific_handler)
```

- The callback receives the `params` dictionary from the JSON-RPC notification message.
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