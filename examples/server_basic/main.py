import os
import sys
import asyncio
import argparse
import random
from datetime import datetime

# Add project root to path if running directly
current_dir = os.path.dirname(os.path.abspath(__file__))
package_dir = os.path.abspath(os.path.join(current_dir, '../..'))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from pymcp_sse.server import BaseMCPServer
from pymcp_sse.utils import configure_logging, get_logger

# Configure logging
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
configure_logging(level=log_level)
logger = get_logger("example.server_basic")

# Create server instance
server = BaseMCPServer(server_name="Basic Example Server")

# --- Tools --- 

@server.register_tool("echo")
async def echo_tool(text: str) -> dict:
    """Echoes the provided text back to the client."""
    logger.info(f"Echoing text: {text}")
    return {"response": f"Server received: {text}"}

@server.register_tool("get_simulated_weather")
async def get_simulated_weather(location: str) -> dict:
    """Simulates fetching weather for a given location."""
    logger.info(f"Simulating weather fetch for: {location}")
    conditions = ["Sunny", "Cloudy", "Rainy", "Windy"]
    condition = random.choice(conditions)
    temperature = random.randint(5, 30) # Celsius
    humidity = random.randint(30, 90) # Percent
    
    return {
        "location": location,
        "temperature_celsius": temperature,
        "condition": condition,
        "humidity_percent": humidity,
        "timestamp": datetime.now().isoformat(),
        "source": "Basic Server Simulation"
    }

# --- Main Execution --- 

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Basic Example MCP Server.")
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Host to bind the server to (overrides MCP_HOST env var, defaults to 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None, # Let BaseMCPServer handle default and MCP_PORT
        help="Port to bind the server to (overrides MCP_PORT env var, defaults to 8000)"
    )
    args = parser.parse_args()
    
    # Use server.run() which handles host/port logic internally
    try:
        server.run(
            host=args.host, 
            port=args.port or 8101, # Default port 8101 for this server if not specified
            log_level=log_level.lower() # Pass uvicorn log level
        )
    except Exception as e:
        logger.critical(f"Server failed to run: {e}", exc_info=True)
        sys.exit(1) 