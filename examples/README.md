# pymcp-sse Examples

This directory contains example implementations of MCP servers and clients using the pymcp-sse library.

## Components

- **server1**: An example MCP server that provides weather, translation, and notification tools.
- **server2**: An example MCP server that provides calculation, database search, and sensor subscription tools.
- **client**: An example MCP client that connects to both servers and provides an LLM agent interface for interaction.

## Prerequisites

Make sure you have the required dependencies installed:

```bash
# From the root directory (containing pymcp_sse/ and examples/)
pip install -r requirements.txt # Assuming requirements.txt is in root
# Or install the package itself if building first
# pip install .
```

For using the LLM agent (which uses Anthropic Claude by default), you need an Anthropic API key. Provide it in one of two ways:

1. Environment variable: `export ANTHROPIC_API_KEY=your_key_here`
2. Create a `.env` file in the root project directory (containing `pymcp_sse/`, `examples/`) with: `ANTHROPIC_API_KEY=your_key_here`

## Running the Examples

### All Components Together

The easiest way to run all components is to use the provided launcher script from within the `examples/` directory:

```bash
# Ensure you are in the examples/ directory
cd /path/to/your/project/examples

python run_all.py
```

This will start both servers and the client, with proper handling of process lifecycle. Press `Ctrl+C` to stop all components gracefully.

### Individual Components

You can also run each component separately from within the `examples/` directory:

#### Server 1

```bash
python server1/main.py
```

This will start Server 1 on port 8101.

#### Server 2

```bash
python server2/main.py
```

This will start Server 2 on port 8002.

#### Client

```bash
python client/main.py
```

This will start the client, which connects to both servers and provides an LLM-driven conversational interface.

## Using the Client

The client example now directly routes your input to the LLM agent. There are no specific CLI commands (`help`, `info`, `call`, etc.).

Simply type your request in natural language, and the LLM agent will attempt to fulfill it, either by responding directly or by calling the appropriate tool on one of the connected servers.

Type `exit` or `quit` to stop the client.

### Example Interaction

```
Welcome to the pymcp-sse Client
Enter your message or type 'exit' to quit

> What's the weather in Paris?

Processing...

Assistant: Okay, I will check the weather in Paris for you.

--- Tool Result ---
{
  "location": "Paris",
  "temperature": 24,
  "condition": "Sunny",
  "humidity": "45%",
  "timestamp": "2025-04-04T15:45:00.123Z",
  "source": "Server 1 Weather Service (Simulated)"
}

> translate "hello world" to French

Processing...

Assistant: Sure, I can translate that for you.

--- Tool Result ---
{
  "original_text": "hello world",
  "translated_text": "bonjour world",
  "target_language": "French",
  "source": "Server 1 Translation Service (Simulated)"
}

> subscribe to humidity sensor updates

Processing...

Assistant: Okay, I will subscribe you to humidity sensor updates from server 2.

--- Tool Result ---
{
  "status": "subscribed",
  "subscription_id": "6b777205-d87c-4a38-81a2-3575d338e248_humidity_1712259910",
  "sensor_type": "humidity",
  "interval_seconds": 15,
  "message": "You are now subscribed to humidity sensor updates every 15 seconds"
}

>>> Notification: Sensor data from server2: humidity = 48.2% (normal)

```

## LLM Agent Capabilities

The LLM agent can:

1. Process natural language queries.
2. Discover available tools across all connected servers.
3. Select the appropriate tool to use based on the query.
4. Format parameters for the tool call (using instructions from the system prompt).
5. Call the tool and present the results.
6. Provide conversational responses when no tool is needed.
7. Receive and display server push notifications. 