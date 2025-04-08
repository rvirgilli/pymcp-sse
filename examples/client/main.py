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
import json
import signal # Import signal module

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
        
        # Generate and print opening statement
        print("\nGenerating opening statement...")
        opening_statement = await self.llm_agent.generate_opening_statement()
        print(f"\nAssistant: {opening_statement}\n")
        
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
            # Special handling for sensor data (from Server 2)
            if server == "server2" and "reading" in data:
                reading = data["reading"]
                sensor_type = data.get("sensor_type", "unknown")
                value = reading.get("value", "N/A")
                unit = reading.get("unit", "")
                status = reading.get("status", "unknown")
                
                logger.info(f"Sensor data from {server}: {sensor_type} = {value}{unit} ({status})")
                print(f"\n>>> Notification: Sensor data from {server}: {sensor_type} = {value}{unit} ({status})")
            # Handle data from Server 3
            elif server == "server3":
                msg = f"Data notification from {server}: {message}"
                logger.info(msg)
                print(f"\n>>> Notification: {msg}")
                if data:
                    formatted_data = json.dumps(data, indent=2)
                    print(f"  └─ Data: {formatted_data}")
            else:
                logger.info(f"Data from {server}: {message} - {data}")
                print(f"\n>>> Notification: DATA from {server}: {message} - {data}")
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
                # Get user input
                user_input = await asyncio.to_thread(input, "> ")
                
                # Check for exit command
                if user_input.lower() in ["exit", "quit"]:
                    print("Exiting CLI")
                    break
                
                # Process the input with the LLM agent
                try:
                    # response = await self.llm_agent.process_query(user_input)
                    # Instead of returning a response, handle_message processes and prints directly
                    await self.llm_agent.handle_message(user_input)
                    # print(response)
                except Exception as e:
                    logger.error(f"Error processing user input: {e}", exc_info=True)
                    print(f"Error: {e}")
                    
            except KeyboardInterrupt:
                print("\nInterrupted by user")
                break
            except Exception as e:
                logger.error(f"Error in CLI: {e}")
                print(f"Error: {e}")
                
        print("\nExiting CLI")

async def main():
    # Configure logging
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    configure_logging(level=log_level)
    
    # Server configurations (using the new server names and default ports)
    servers = {
        "server_basic": "http://localhost:8101",
        "server_tasks": "http://localhost:8102"
    }
    
    # Create and start the client application
    app = MCPClientApp(servers)
    
    # --- Signal Handling for Graceful Shutdown --- 
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def shutdown_handler(signum, frame):
        logger.info(f"Received signal {signal.Signals(signum).name}, initiating shutdown...")
        if not stop_event.is_set():
            # Use call_soon_threadsafe as signal handlers run in the main thread
            loop.call_soon_threadsafe(stop_event.set)

    # Register handlers for SIGINT (Ctrl+C) and SIGTERM
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    # --- End Signal Handling --- 

    try:
        # Start the client
        if await app.start():
            # Run the CLI until stop_event is set or CLI exits
            cli_task = asyncio.create_task(app.run_cli())
            stop_wait_task = asyncio.create_task(stop_event.wait())
            
            # Wait for either the CLI to finish or the stop event
            done, pending = await asyncio.wait(
                [cli_task, stop_wait_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # If stop_event caused completion, cancel the CLI task
            if stop_wait_task in done:
                logger.info("Stop event received, cancelling CLI task.")
                cli_task.cancel()
                try:
                    await cli_task # Allow cancellation to propagate
                except asyncio.CancelledError:
                    logger.info("CLI task cancelled successfully.")
            else:
                 logger.info("CLI task completed normally.")
            
    except Exception as e:
        logger.critical(f"Client encountered critical error: {e}", exc_info=True)
    finally:
        logger.info("Client main loop finished, closing application...")
        # Ensure close is called regardless of how we exited
        await app.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # This handles Ctrl+C directly in the client if run standalone,
        # but the signal handler is more robust for run_all.py
        logger.info("Client received KeyboardInterrupt, exiting.") 