"""
Example MCP Client using PyMCP with LLM Agent
"""
import os
import sys
import asyncio
import logging
from typing import Dict, Any
import readline
import traceback

# Add pymcp to path if running directly from examples
current_dir = os.path.dirname(os.path.abspath(__file__))
package_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from pymcp_sse.client import MultiMCPClient
from pymcp_sse.utils import get_logger, configure_logging
from pymcp_sse.common.constants import NOTIFICATION_INFO, NOTIFICATION_WARNING, NOTIFICATION_ERROR, NOTIFICATION_DATA

# Add support for local imports
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from llm_agent import LLMAgent

# Get logger
logger = get_logger("examples.client")

class MCPClientApp:
    """Example MCP client application with CLI interface."""
    
    def __init__(self, servers: Dict[str, str]):
        """
        Initialize the client application.
        
        Args:
            servers: Dictionary mapping server aliases to URLs
        """
        self.servers = servers
        self.client = MultiMCPClient(
            servers=self.servers,
            http_read_timeout=65,
            http_connect_timeout=10
        )
        self.llm_agent = None
        self.running = False
        logger.info(f"Initialized MCPClientApp with {len(servers)} servers")
        
    async def start(self):
        """Start the client application."""
        logger.info("Starting MCPClientApp")
        
        # Connect to all servers
        results = await self.client.connect_all()
        
        # Check if at least one server connected successfully
        if not any(results.values()):
            logger.error("Failed to connect to any server")
            return False
            
        # Set up notification handling
        self.client.add_notification_callback(None, self._handle_notification)
        
        # Initialize LLM agent
        self.llm_agent = LLMAgent(self.client)
        await self.llm_agent.start()
            
        self.running = True
        logger.info("MCPClientApp started successfully")
        return True
        
    async def _handle_notification(self, server: str, notification: Dict[str, Any]):
        """
        Handle notifications from servers.
        
        Args:
            server: Server alias
            notification: Notification parameters
        """
        # Extract notification information
        notif_type = notification.get("type", "unknown")
        message = notification.get("message", "No message")
        timestamp = notification.get("timestamp", "")
        data = notification.get("data", {})
        
        # Log the notification based on type
        if notif_type == NOTIFICATION_DATA:
            # Special handling for sensor data
            if "reading" in data:
                reading = data["reading"]
                sensor_type = data.get("sensor_type", "unknown")
                value = reading.get("value", "N/A")
                unit = reading.get("unit", "")
                status = reading.get("status", "unknown")
                
                logger.info(f"Sensor data from {server}: {sensor_type} = {value}{unit} ({status})")
                print(f"\n>>> Notification: Sensor data from {server}: {sensor_type} = {value}{unit} ({status})")
        else:
            # Standard notification
            if notif_type == NOTIFICATION_INFO:
                logger.info(f"INFO from {server}: {message}")
                print(f"\n>>> Notification: INFO from {server}: {message}")
            elif notif_type == NOTIFICATION_WARNING:
                logger.warning(f"WARNING from {server}: {message}")
                print(f"\n>>> Notification: WARNING from {server}: {message}")
            elif notif_type == NOTIFICATION_ERROR:
                logger.error(f"ERROR from {server}: {message}")
                print(f"\n>>> Notification: ERROR from {server}: {message}")
            else:
                logger.info(f"Notification from {server} ({notif_type}): {message}")
                print(f"\n>>> Notification from {server} ({notif_type}): {message}")
                
    async def close(self):
        """Close the client application."""
        logger.info("Closing MCPClientApp")
        
        # Stop LLM agent if it's running
        if self.llm_agent:
            await self.llm_agent.stop()
            
        # Close client connections
        await self.client.close()
        
        self.running = False
        logger.info("MCPClientApp closed")
        
    async def run_cli(self):
        """Run the interactive CLI."""
        if not self.running:
            logger.error("Cannot run CLI: client not started")
            return
            
        print("\nWelcome to the PyMCP Client")
        print("Enter your message or type 'exit' to quit")
        
        while self.running:
            try:
                # Run blocking input() in a separate thread
                user_input = await asyncio.to_thread(input, "\n> ")
                user_input = user_input.strip()
                
                if not user_input:
                    continue
                    
                if user_input.lower() in ("exit", "quit"):
                    break
                
                # Process the input with the LLM agent
                response = await self.llm_agent.process_query(user_input)
                print(response)
                    
            except KeyboardInterrupt:
                print("\nInterrupted by user")
                break
            except Exception as e:
                logger.error(f"Error in CLI: {e}")
                print(f"Error: {e}")
                
        print("\nExiting CLI")

async def main():
    # Configure logging
    configure_logging(level="INFO")
    
    # Server configurations
    servers = {
        "server1": "http://localhost:8101",
        "server2": "http://localhost:8002"
    }
    
    # Create and start the client application
    app = MCPClientApp(servers)
    
    try:
        # Start the client
        if await app.start():
            # Run the CLI
            await app.run_cli()
    finally:
        # Close the client
        await app.close()

if __name__ == "__main__":
    # Run the main async function
    asyncio.run(main()) 