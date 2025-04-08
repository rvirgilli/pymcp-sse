# pymcp-sse Examples

This directory contains example implementations of MCP servers and clients using the `pymcp-sse` library, demonstrating key features like multi-server connections, tool aggregation, and running servers with background tasks.

## Components

- **`server_basic/`**: 
    - An example MCP server providing simple tools (e.g., echo, simulated weather).
    - Demonstrates standard server startup using `server.run()`.
    - Runs on port `8101` by default.
- **`server_tasks/`**:
    - An example MCP server focused on background tasks and notifications.
    - Implements notification scheduling (immediate, delayed, periodic) using `NotificationScheduler`.
    - Demonstrates server startup with concurrent tasks using `server.run_with_tasks()`.
    - Runs on port `8102` by default.
- **`client/`**:
    - An example MCP client using `MultiMCPClient` to connect to both `server_basic` and `server_tasks`.
    - Integrates an `LLMAgent` (using Anthropic Claude by default) to provide a natural language interface.
    - The agent discovers tools from both servers and calls them as needed based on user queries.
    - Handles and displays push notifications from `server_tasks`.
- **`run_all.py`**:
    - A launcher script to conveniently start both servers and the client.
    - Performs health checks to ensure servers are ready before starting the client.
- **`notification_listener.py`**:
    - A standalone, simple client utility.
    - Connects to a *single* specified MCP server (defaults to `localhost:8000` but configurable via args).
    - Listens for and prints any notifications received from the server.
    - Useful for testing any MCP server that sends notifications (like `server_tasks`).

## Prerequisites

Make sure you have the required dependencies installed:

```bash
# From the root directory (containing pymcp_sse/ and examples/)
pip install -r requirements.txt # Assuming requirements.txt is in root
# Or install the package itself if building first
# pip install .
```

For using the LLM agent in the `client/` example (which uses Anthropic Claude by default), you need an Anthropic API key. Provide it in one of two ways:

1.  Environment variable: `export ANTHROPIC_API_KEY=your_key_here`
2.  Create a `.env` file in the root project directory (containing `pymcp_sse/`, `examples/`) with: `ANTHROPIC_API_KEY=your_key_here`

## Running the Examples

### All Components Together (Recommended)

The easiest way to run the multi-server example is using the launcher script from within the `examples/` directory:

```bash
# Ensure you are in the examples/ directory
cd /path/to/your/project/examples

python run_all.py
```

This will start `server_basic`, `server_tasks`, and the `client` application. Press `Ctrl+C` in the terminal where `run_all.py` is running to stop all components gracefully.

### Individual Components

You can also run each component separately from within the `examples/` directory:

#### Basic Server

```bash
python server_basic/main.py --port 8101 
# Or set MCP_PORT=8101
```

#### Tasks Server

```bash
python server_tasks/main.py --port 8102
# Or set MCP_PORT=8102
```

#### Client (Connects to 8101 & 8102)

```bash
python client/main.py
```

### Notification Listener Utility

To test notifications from `server_tasks` (or any other server), run the listener, specifying the server's host and port:

```bash
# Assuming server_tasks is running on port 8102
python notification_listener.py --host localhost --port 8102
```

## Using the LLM Client (`client/main.py`)

When running the `client` (either via `run_all.py` or individually), it provides an LLM-driven conversational interface. There are no specific CLI commands.

Simply type your request in natural language. The LLM agent will:
1.  Understand your request.
2.  Check the available tools from both `server_basic` (e.g., `echo`, `get_simulated_weather`) and `server_tasks` (e.g., `send_immediate_notification`, `schedule_notification`, `start_periodic_pings`, `stop_periodic_task`).
3.  If a suitable tool is found, call it with the necessary parameters.
4.  Present the tool's result or provide a conversational response.
5.  Display any push notifications received from `server_tasks`.

Type `exit` or `quit` to stop the client.

### Example Interaction

```
Welcome to the pymcp-sse Client
(Connected to server_basic, server_tasks)
Enter your message or type 'exit' to quit

> What's the weather like in Berlin?

Processing...
Assistant: Checking the simulated weather for Berlin...

--- Tool Result (server_basic.get_simulated_weather) ---
{
  "location": "Berlin",
  "temperature_celsius": 15,
  "condition": "Cloudy",
  "humidity_percent": 65,
  "timestamp": "...",
  "source": "Basic Server Simulation"
}

> Send a notification saying 'Test message' in 5 seconds

Processing...
Assistant: Okay, I will schedule a notification.

--- Tool Result (server_tasks.schedule_notification) ---
{
  "success": true,
  "scheduled_for_seconds": 5,
  "task_id": "..."
}

> start periodic pings every 10 seconds

Processing...
Assistant: Starting periodic pings...

--- Tool Result (server_tasks.start_periodic_pings) ---
{
  "success": true,
  "interval_seconds": 10,
  "task_id": "..."
}

>>> Notification: DATA from server_tasks: Periodic Server Ping - {'count': 1, 'periodic': True}
>>> Notification: INFO from server_tasks: Test message - {'scheduled': True}
>>> Notification: DATA from server_tasks: Periodic Server Ping - {'count': 2, 'periodic': True}
``` 