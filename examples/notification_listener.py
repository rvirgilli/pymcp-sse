"""
Example client that listens for notifications from the MCP server.

This demonstrates how to:
1. Connect to an MCP server
2. Subscribe to Telegram-like updates
3. Handle different types of push notifications

Usage:
    python notification_listener.py [--host HOST] [--port PORT]
"""

import os
import sys
import asyncio
import argparse
import json
from datetime import datetime

# Add the project root to Python path if running directly
current_dir = os.path.dirname(os.path.abspath(__file__))
package_dir = os.path.abspath(os.path.join(current_dir, '..'))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from pymcp_sse.client import BaseMCPClient
from pymcp_sse.common.constants import (
    NOTIFICATION_INFO, 
    NOTIFICATION_WARNING, 
    NOTIFICATION_ERROR,
    NOTIFICATION_DATA
)
from pymcp_sse.utils.log_setup import get_logger, configure_logging

# Configure logging
configure_logging(level="INFO")
logger = get_logger("notification_listener")

class NotificationListener:
    """
    A client that connects to an MCP server and listens for notifications.
    """
    
    def __init__(self, host, port):
        """
        Initialize the notification listener.
        
        Args:
            host: Server host
            port: Server port
        """
        self.host = host
        self.port = port
        self.server_url = f"http://{host}:{port}"
        self.client = BaseMCPClient(
            server_url=self.server_url,
            http_read_timeout=120,  # Longer timeout for long-lived connections
            http_connect_timeout=10
        )
        
        # Register notification handler
        self.client.notification_handler = self.handle_notification
        
    async def connect(self):
        """Connect to the MCP server."""
        logger.info(f"Connecting to MCP server at {self.server_url}...")
        
        if await self.client.connect():
            logger.info(f"Connected to server: {self.server_url}")
            
            # Initialize the client
            if await self.client.initialize():
                logger.info("MCP session initialized")
                return True
            else:
                logger.error("Failed to initialize MCP session")
                return False
        else:
            logger.error(f"Failed to connect to server: {self.server_url}")
            return False
    
    async def subscribe_to_updates(self, update_types=None):
        """
        Subscribe to Telegram updates.
        
        Args:
            update_types: Optional list of update types to filter
        """
        try:
            result = await self.client.call_tool(
                "subscribe_to_updates",
                update_types=update_types
            )
            
            logger.info(f"Subscription result: {result}")
            return result
        except Exception as e:
            logger.error(f"Error subscribing to updates: {e}")
            return None
    
    async def handle_notification(self, type_name, message, data=None, timestamp=None):
        """
        Handle notifications from the server.
        
        Args:
            type_name: Notification type (info, warning, error, data)
            message: Notification message
            data: Optional additional data
            timestamp: Optional timestamp
        """
        time_str = datetime.now().strftime("%H:%M:%S")
        
        # Print notification based on type
        if type_name == NOTIFICATION_INFO:
            print(f"\n🔵 [{time_str}] INFO: {message}")
        elif type_name == NOTIFICATION_WARNING:
            print(f"\n🟡 [{time_str}] WARNING: {message}")
        elif type_name == NOTIFICATION_ERROR:
            print(f"\n🔴 [{time_str}] ERROR: {message}")
        elif type_name == NOTIFICATION_DATA:
            print(f"\n🟢 [{time_str}] DATA: {message}")
        else:
            print(f"\n⚪ [{time_str}] {type_name}: {message}")
        
        # Print data if available (with formatting)
        if data:
            if isinstance(data, dict):
                # Format Telegram update data
                if data.get("type") in ["message", "callback_query", "edited_message", "channel_post"]:
                    update_id = data.get("update_id", "N/A")
                    update_type = data.get("type", "unknown")
                    content = data.get("content", "")
                    
                    print(f"  └─ Telegram Update #{update_id} [{update_type}]")
                    print(f"     Content: {content}")
                    
                    # Additional metadata
                    if data.get("scheduled"):
                        print(f"     (Scheduled message)")
                    if data.get("periodic"):
                        print(f"     (Periodic update)")
                else:
                    # For other types of data, print as formatted JSON
                    formatted_data = json.dumps(data, indent=2)
                    print(f"  └─ Data: {formatted_data}")
            else:
                print(f"  └─ Data: {data}")
    
    async def run(self):
        """Run the notification listener."""
        try:
            # Connect to the server
            if not await self.connect():
                return
            
            # Subscribe to updates
            await self.subscribe_to_updates()
            
            print(f"\n🎧 Listening for notifications from {self.server_url}...")
            print("Press Ctrl+C to stop")
            
            # Keep the client running indefinitely
            while True:
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            print("\n\nNotification listener stopped")
        except Exception as e:
            logger.error(f"Error in notification listener: {e}")
        finally:
            # Clean up
            await self.client.close()

async def main():
    """Main entry point."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="MCP Notification Listener")
    parser.add_argument("--host", default="localhost", help="Server host")
    parser.add_argument("--port", type=int, default=8000, help="Server port")
    args = parser.parse_args()
    
    # Create and run the listener
    listener = NotificationListener(host=args.host, port=args.port)
    await listener.run()

if __name__ == "__main__":
    asyncio.run(main()) 